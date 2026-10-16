"""Карта города (снимок OSM) и работа с базой SQLite."""
import json
import os
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP = json.loads((ROOT / 'map_data.json').read_text(encoding='utf-8'))

NODES = {n['id']: n for n in MAP['nodes']}
NODE_IDS = set(NODES)
EDGE_IDS = {e['id'] for e in MAP['edges']}

CHANGE_SOURCE = 'Одобренное изменение модели'

SCHEMA = '''
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','moderator')),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf_token TEXT NOT NULL,
        expires_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS city (
        id INTEGER PRIMARY KEY CHECK(id=1),
        state TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS proposals (
        id TEXT PRIMARY KEY,
        author_id TEXT NOT NULL REFERENCES users(id),
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        base_version INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected')),
        created_at TEXT NOT NULL,
        closed_at TEXT,
        reviewer_id TEXT REFERENCES users(id),
        comment TEXT,
        applied_version INTEGER,
        CHECK((status='pending' AND closed_at IS NULL) OR
              (status!='pending' AND closed_at IS NOT NULL AND reviewer_id IS NOT NULL))
    );
    CREATE INDEX IF NOT EXISTS proposals_author ON proposals(author_id);

    CREATE TABLE IF NOT EXISTS auth_attempts (
        key TEXT NOT NULL,
        attempted_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS attempts_key_time ON auth_attempts(key, attempted_at);
'''


def initial_state():
    return {
        'version': 0,
        'closed_edges': [],
        'facilities': deepcopy(MAP['facilities']),
    }


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with connect(path) as db:
        db.executescript(SCHEMA)
        db.execute(
            'INSERT OR IGNORE INTO city(id, state) VALUES(1, ?)',
            (json.dumps(initial_state()),),
        )

    # в базе лежат хеши паролей и сессий, поэтому закрываем её для других
    # пользователей (на Windows chmod не работает, там пропускаем)
    if os.name != 'nt':
        Path(path).chmod(0o600)


def read_state(db):
    row = db.execute('SELECT state FROM city WHERE id=1').fetchone()
    return json.loads(row['state'])


# --- изменения города ---
# Каждая функция правит переданную копию состояния и кидает ValueError,
# если действие не имеет смысла.

def change_edge(state, kind, edge_id, facility_id):
    if facility_id is not None or edge_id not in EDGE_IDS:
        raise ValueError('Неизвестная дорожка или лишний идентификатор объекта')

    closed = set(state['closed_edges'])

    if kind == 'close_edge':
        if edge_id in closed:
            raise ValueError('Дорожка уже закрыта')
        closed.add(edge_id)
    else:
        if edge_id not in closed:
            raise ValueError('Дорожка уже открыта')
        closed.remove(edge_id)

    state['closed_edges'] = sorted(closed)


def move_stop(state, node_id, stop_id):
    stop = None
    for f in state['facilities']:
        if f['id'] == stop_id and f['kind'] == 'stop':
            stop = f
            break

    if stop is None or node_id not in NODES:
        raise ValueError('Выберите существующую остановку и узел')
    if stop['node'] == node_id:
        raise ValueError('Остановка уже находится в этом узле')

    node = NODES[node_id]
    stop['node'] = node_id
    stop['lat'] = node['lat']
    stop['lon'] = node['lon']
    stop['source'] = CHANGE_SOURCE


def add_park(state, node_id, facility_id):
    if facility_id is not None or node_id not in NODES:
        raise ValueError('Неизвестный узел или лишний идентификатор объекта')

    for f in state['facilities']:
        if f['kind'] == 'park' and f['node'] == node_id:
            raise ValueError('Зелёная зона уже существует в этом узле')

    node = NODES[node_id]
    state['facilities'].append({
        'id': 'park-' + node_id,
        'node': node_id,
        'name': 'Новая зелёная зона',
        'kind': 'park',
        'lat': node['lat'],
        'lon': node['lon'],
        'source': CHANGE_SOURCE,
    })


def remove_park(state, park_id, facility_id):
    is_park = any(f['id'] == park_id and f['kind'] == 'park' for f in state['facilities'])
    if facility_id is not None or not is_park:
        raise ValueError('Зелёная зона не найдена')

    state['facilities'] = [f for f in state['facilities'] if f['id'] != park_id]


def apply_action(state, action):
    """Возвращает новое состояние, исходное не трогает.

    Одна и та же функция используется и для предпросмотра, и при одобрении
    заявки, поэтому результаты всегда совпадают.
    """
    result = deepcopy(state)
    kind = action['type']
    target = action['target_id']
    facility_id = action.get('facility_id')

    if kind in ('close_edge', 'open_edge'):
        change_edge(result, kind, target, facility_id)
    elif kind == 'move_stop':
        move_stop(result, target, facility_id)
    elif kind == 'add_park':
        add_park(result, target, facility_id)
    elif kind == 'remove_park':
        remove_park(result, target, facility_id)
    else:
        raise ValueError('Неизвестное действие')

    return result
