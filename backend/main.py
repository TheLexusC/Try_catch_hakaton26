"""Точка входа FastAPI.

Запуск: uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .data import MAP, apply_action, connect, initialize, read_state
from .metrics import calculate_metrics
from .schemas import Credentials, Decision, Preview, Proposal, Registration

DATABASE = os.environ.get(
    'OBNINSK_DB',
    str(Path(__file__).parent / 'instance' / 'city.sqlite3'),
)
COOKIE = 'obninsk_session'
SESSION_TTL = 7 * 24 * 3600          # сессия живёт неделю

MAX_BODY_SIZE = 16 * 1024            # лимит тела запроса, байт
WRITE_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}
DEFAULT_ORIGINS = (
    'http://localhost:5173,http://127.0.0.1:5173,'
    'http://localhost:8000,http://127.0.0.1:8000'
)

ATTEMPT_WINDOW = 15 * 60             # окно для лимита попыток входа, сек
MAX_ATTEMPTS_PER_IP = 60
MAX_ATTEMPTS_PER_EMAIL = 12
MAX_PENDING_PROPOSALS = 20

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
}


# --- мелкие помощники ---

def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()
    return f'scrypt${salt}${hashed}'


def verify_password(password, stored):
    try:
        _, salt, _ = stored.split('$')
        return hmac.compare_digest(hash_password(password, salt), stored)
    except (ValueError, TypeError):
        return False


# Хеш для несуществующих пользователей: пароль проверяется в любом случае,
# и по времени ответа нельзя понять, есть ли такой email в базе.
DUMMY_HASH = hash_password('not-a-real-account-password')


def public_user(row):
    return {key: row[key] for key in ('id', 'email', 'name', 'role')}


def allowed_origins():
    return set(os.environ.get('OBNINSK_ORIGINS', DEFAULT_ORIGINS).split(','))


async def check_write_request(request):
    """Проверяет запросы, которые что-то меняют.

    Возвращает ответ с ошибкой или None, если всё в порядке.
    """
    origin = request.headers.get('origin')
    if origin and origin not in allowed_origins():
        return JSONResponse({'detail': 'Недопустимый источник запроса'}, status_code=403)

    content_type = request.headers.get('content-type', '').lower()
    if not content_type.startswith('application/json'):
        return JSONResponse({'detail': 'Требуется application/json'}, status_code=415)

    # Размер считаем по факту, а не по заголовку: так ловятся и chunked-запросы.
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_SIZE:
            return JSONResponse({'detail': 'Слишком большой запрос'}, status_code=413)
        chunks.append(chunk)
    request._body = b''.join(chunks)
    return None


def create_app(db_path=DATABASE):

    @asynccontextmanager
    async def lifespan(application):
        initialize(db_path)
        yield

    app = FastAPI(title='Обнинск 2040', version='2.0.0', lifespan=lifespan)
    app.state.db_path = str(db_path)

    @app.middleware('http')
    async def request_policy(request: Request, call_next):
        is_api = request.url.path.startswith('/api/')

        if is_api and request.method in WRITE_METHODS:
            error = await check_write_request(request)
            if error is not None:
                return error

        response = await call_next(request)
        if is_api:
            response.headers['Cache-Control'] = 'no-store'
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    # --- вспомогательные функции, которым нужен db_path ---

    def load_state():
        with connect(db_path) as db:
            return read_state(db)

    def throttle(request, email):
        """Ограничивает число попыток входа по IP и по email за 15 минут.

        В базе лежат только хеши, сам email и IP не хранятся.
        """
        stamp = time.time()
        ip = request.client.host if request.client else 'local'
        limits = [
            ('ip:' + digest(ip), MAX_ATTEMPTS_PER_IP),
            ('email:' + digest(email), MAX_ATTEMPTS_PER_EMAIL),
        ]

        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute(
                'DELETE FROM auth_attempts WHERE attempted_at < ?',
                (stamp - ATTEMPT_WINDOW,),
            )
            for key, limit in limits:
                count = db.execute(
                    'SELECT count(*) FROM auth_attempts WHERE key=?', (key,)
                ).fetchone()[0]
                if count >= limit:
                    raise HTTPException(
                        429,
                        'Слишком много попыток. Повторите через 15 минут.',
                        headers={'Retry-After': str(ATTEMPT_WINDOW)},
                    )
            db.executemany(
                'INSERT INTO auth_attempts VALUES(?,?)',
                [(key, stamp) for key, _ in limits],
            )

    def new_session(db, user, response):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)

        db.execute('DELETE FROM sessions WHERE expires_at < ?', (time.time(),))
        db.execute(
            'INSERT INTO sessions VALUES(?,?,?,?)',
            (digest(token), user['id'], csrf, time.time() + SESSION_TTL),
        )
        response.set_cookie(
            COOKIE, token,
            max_age=SESSION_TTL,
            httponly=True,
            secure=os.environ.get('OBNINSK_SECURE_COOKIE') == '1',
            samesite='strict',
            path='/',
        )
        return {'user': public_user(user), 'csrf_token': csrf}

    def current_session(request: Request):
        token = request.cookies.get(COOKIE, '')
        with connect(db_path) as db:
            user = db.execute(
                '''SELECT users.*, sessions.csrf_token
                   FROM sessions JOIN users ON users.id = sessions.user_id
                   WHERE token_hash=? AND expires_at>?''',
                (digest(token), time.time()),
            ).fetchone()

        if user is None:
            raise HTTPException(401, 'Войдите в аккаунт')

        # для всего, кроме GET, нужен CSRF-токен
        if request.method != 'GET':
            sent_csrf = request.headers.get('x-csrf-token', '')
            if not hmac.compare_digest(sent_csrf, user['csrf_token']):
                raise HTTPException(
                    403, 'Сессия устарела. Обновите страницу и попробуйте снова.'
                )
        return dict(user)

    def moderator(user=Depends(current_session)):
        if user['role'] != 'moderator':
            raise HTTPException(403, 'Доступно только модератору')
        return user

    def checked_change(state, payload):
        """Применяет действие к копии состояния, если карта не успела измениться."""
        if state['version'] != payload.base_version:
            raise HTTPException(
                409, 'Карта обновилась. Обновите карту и создайте новое предложение.'
            )
        try:
            return apply_action(state, payload.action.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def serialize_proposal(row):
        result = dict(row)
        result['action'] = json.loads(result['action'])
        return result

    # --- служебное ---

    @app.get('/api/health')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1')
        return {'status': 'ok'}

    # --- аккаунты ---

    @app.post('/api/auth/register', status_code=201)
    def register(payload: Registration, response: Response, request: Request):
        throttle(request, str(payload.email))

        user = {
            'id': str(uuid.uuid4()),
            'email': str(payload.email),
            'name': payload.name,
            'role': 'user',
            'password_hash': hash_password(payload.password),
            'created_at': now(),
        }
        try:
            with connect(db_path) as db:
                db.execute(
                    '''INSERT INTO users(id, email, name, role, password_hash, created_at)
                       VALUES(:id, :email, :name, :role, :password_hash, :created_at)''',
                    user,
                )
                return new_session(db, user, response)
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, 'Этот email уже зарегистрирован') from error

    @app.post('/api/auth/login')
    def login(payload: Credentials, response: Response, request: Request):
        throttle(request, str(payload.email))

        with connect(db_path) as db:
            user = db.execute(
                'SELECT * FROM users WHERE email=?', (str(payload.email),)
            ).fetchone()

            stored_hash = user['password_hash'] if user else DUMMY_HASH
            password_ok = verify_password(payload.password, stored_hash)
            if not user or not password_ok:
                raise HTTPException(401, 'Неверный email или пароль')

            # старую сессию (если была) закрываем
            old_token = request.cookies.get(COOKIE)
            if old_token:
                db.execute(
                    'DELETE FROM sessions WHERE token_hash=?', (digest(old_token),)
                )
            return new_session(db, user, response)

    @app.get('/api/auth/me')
    def me(user=Depends(current_session)):
        return {'user': public_user(user), 'csrf_token': user['csrf_token']}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, user=Depends(current_session)):
        token = request.cookies.get(COOKIE, '')
        with connect(db_path) as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(token),))
        response.delete_cookie(COOKIE, path='/', httponly=True, samesite='strict')
        return {'ok': True}

    # --- город ---

    @app.get('/api/city')
    def city():
        state = load_state()
        return {'map': MAP, 'state': state, 'metrics': calculate_metrics(state)}

    @app.post('/api/preview')
    def preview(payload: Preview, user=Depends(current_session)):
        state = load_state()
        after = checked_change(state, payload)
        return {
            'before': calculate_metrics(state),
            'after': calculate_metrics(after),
            'state': after,
        }

    # --- заявки ---

    @app.post('/api/proposals', status_code=201)
    def submit(payload: Proposal, user=Depends(current_session)):
        proposal_id = str(uuid.uuid4())

        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            state = read_state(db)
            checked_change(state, payload)   # только проверка, результат не нужен

            action = json.dumps(
                payload.action.model_dump(), sort_keys=True, ensure_ascii=False
            )

            duplicate = db.execute(
                "SELECT id FROM proposals "
                "WHERE author_id=? AND action=? AND status='pending'",
                (user['id'], action),
            ).fetchone()
            if duplicate:
                raise HTTPException(409, 'Такое предложение уже ожидает модерации')

            pending = db.execute(
                "SELECT count(*) FROM proposals WHERE author_id=? AND status='pending'",
                (user['id'],),
            ).fetchone()[0]
            if pending >= MAX_PENDING_PROPOSALS:
                raise HTTPException(
                    429,
                    f'У вас уже {MAX_PENDING_PROPOSALS} заявок на модерации. '
                    'Дождитесь решения.',
                )

            db.execute(
                '''INSERT INTO proposals(id, author_id, action, reason, base_version, created_at)
                   VALUES(?,?,?,?,?,?)''',
                (proposal_id, user['id'], action, payload.reason,
                 payload.base_version, now()),
            )

        return {
            'id': proposal_id,
            'status': 'pending',
            'message': 'Отправлено на модерацию. Изменение ещё не применено.',
        }

    @app.get('/api/proposals')
    def list_proposals(user=Depends(current_session)):
        query = '''SELECT proposals.*, author.name AS author_name, reviewer.name AS reviewer_name
                   FROM proposals
                   JOIN users author ON author.id = proposals.author_id
                   LEFT JOIN users reviewer ON reviewer.id = proposals.reviewer_id'''
        args = ()

        # обычный пользователь видит только свои заявки, модератор все
        if user['role'] != 'moderator':
            query += ' WHERE proposals.author_id=?'
            args = (user['id'],)
        query += ' ORDER BY proposals.created_at DESC'

        with connect(db_path) as db:
            rows = db.execute(query, args).fetchall()
        return {'items': [serialize_proposal(row) for row in rows]}

    @app.get('/api/proposals/{proposal_id}/preview')
    def preview_proposal(proposal_id: str, user=Depends(moderator)):
        with connect(db_path) as db:
            row = db.execute(
                'SELECT * FROM proposals WHERE id=?', (proposal_id,)
            ).fetchone()
            state = read_state(db)

        if row is None:
            raise HTTPException(404, 'Заявка не найдена')
        if row['status'] != 'pending':
            raise HTTPException(409, 'Заявка уже закрыта')

        change = Preview(action=json.loads(row['action']), base_version=row['base_version'])
        after = checked_change(state, change)
        return {
            'before': calculate_metrics(state),
            'after': calculate_metrics(after),
            'state': after,
        }

    @app.post('/api/proposals/{proposal_id}/decision')
    def decide(proposal_id: str, payload: Decision, user=Depends(moderator)):
        # Всё в одной транзакции, чтобы две одновременные заявки
        # не применились к одной и той же версии карты.
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')

            row = db.execute(
                'SELECT * FROM proposals WHERE id=?', (proposal_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, 'Заявка не найдена')
            if row['status'] != 'pending':
                raise HTTPException(
                    409, 'Заявка уже закрыта. Повторное решение невозможно.'
                )
            if row['author_id'] == user['id']:
                raise HTTPException(
                    403, 'Собственную заявку должен рассмотреть другой модератор'
                )

            applied_version = None
            if payload.decision == 'approved':
                state = read_state(db)
                change = Preview(
                    action=json.loads(row['action']), base_version=row['base_version']
                )
                after = checked_change(state, change)
                after['version'] += 1
                applied_version = after['version']
                db.execute(
                    'UPDATE city SET state=? WHERE id=1',
                    (json.dumps(after, ensure_ascii=False),),
                )

            closed_at = now()
            db.execute(
                '''UPDATE proposals
                   SET status=?, closed_at=?, reviewer_id=?, comment=?, applied_version=?
                   WHERE id=?''',
                (payload.decision, closed_at, user['id'], payload.comment,
                 applied_version, proposal_id),
            )

        return {
            'id': proposal_id,
            'status': payload.decision,
            'closed_at': closed_at,
            'applied_version': applied_version,
        }

    # Собранный React-фронтенд отдаём с того же адреса, что и API.
    dist = Path(__file__).parent.parent / 'frontend' / 'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    else:
        @app.get('/')
        def build_hint():
            return {
                'message': 'Соберите frontend: cd frontend && npm ci && npm run build. '
                           'Затем перезапустите backend.'
            }

    return app


app = create_app()


def main():
    """Консольная команда: python -m backend.main promote user@example.com"""
    parser = argparse.ArgumentParser(description='Управление локальным проектом Обнинск 2040')
    parser.add_argument('command', choices=['promote'])
    parser.add_argument('email', help='Email уже зарегистрированного пользователя')
    args = parser.parse_args()

    initialize(DATABASE)
    with connect(DATABASE) as db:
        result = db.execute(
            "UPDATE users SET role='moderator' WHERE email=?",
            (args.email.strip().lower(),),
        )
        if result.rowcount != 1:
            parser.exit(1, 'Пользователь не найден. Сначала зарегистрируйте его на сайте.\n')

    print('Роль модератора назначена. Обновите страницу сайта.')


if __name__ == '__main__':
    main()
