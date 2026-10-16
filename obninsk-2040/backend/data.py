"""OSM snapshot and SQLite persistence; no passwords or seed admin in source."""
import json
import os
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP = json.loads((ROOT / 'map_data.json').read_text())
NODE_IDS = {n['id'] for n in MAP['nodes']}
EDGE_IDS = {e['id'] for e in MAP['edges']}


def initial_state():
    return {'version': 0, 'closed_edges': [], 'facilities': deepcopy(MAP['facilities'])}


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
        db.executescript('''
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
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
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
        ''')
        db.execute('INSERT OR IGNORE INTO city(id,state) VALUES(1,?)', (json.dumps(initial_state()),))
    # Local DB contains password hashes and session hashes; do not world-read it.
    if os.name != 'nt':
        Path(path).chmod(0o600)


def read_state(db):
    return json.loads(db.execute('SELECT state FROM city WHERE id=1').fetchone()['state'])


def apply_action(state, action):
    """Pure mutation on a copy. Used identically for preview and approval."""
    result = deepcopy(state)
    kind, target = action['type'], action['target_id']
    fid = action.get('facility_id')
    if kind in {'close_edge', 'open_edge'}:
        if fid is not None or target not in EDGE_IDS:
            raise ValueError('Неизвестная дорожка или лишний идентификатор объекта')
        closed = set(result['closed_edges'])
        if kind == 'close_edge':
            if target in closed:
                raise ValueError('Дорожка уже закрыта')
            closed.add(target)
        else:
            if target not in closed:
                raise ValueError('Дорожка уже открыта')
            closed.remove(target)
        result['closed_edges'] = sorted(closed)
    elif kind == 'move_stop':
        stop = next((f for f in result['facilities'] if f['id'] == fid and f['kind'] == 'stop'), None)
        if stop is None or target not in NODE_IDS:
            raise ValueError('Выберите существующую остановку и узел')
        if stop['node'] == target:
            raise ValueError('Остановка уже находится в этом узле')
        node = next(n for n in MAP['nodes'] if n['id'] == target)
        stop.update(node=target, lat=node['lat'], lon=node['lon'], source='Одобренное изменение модели')
    elif kind == 'add_park':
        if fid is not None or target not in NODE_IDS:
            raise ValueError('Неизвестный узел или лишний идентификатор объекта')
        if any(f['kind'] == 'park' and f['node'] == target for f in result['facilities']):
            raise ValueError('Зелёная зона уже существует в этом узле')
        node = next(n for n in MAP['nodes'] if n['id'] == target)
        result['facilities'].append({'id': 'park-' + target, 'node': target, 'name': 'Новая зелёная зона', 'kind': 'park', 'lat': node['lat'], 'lon': node['lon'], 'source': 'Одобренное изменение модели'})
    elif kind == 'remove_park':
        if fid is not None or not any(f['id'] == target and f['kind'] == 'park' for f in result['facilities']):
            raise ValueError('Зелёная зона не найдена')
        result['facilities'] = [f for f in result['facilities'] if f['id'] != target]
    else:
        raise ValueError('Неизвестное действие')
    return result
