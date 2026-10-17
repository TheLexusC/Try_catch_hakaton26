"""FastAPI entry point: uvicorn backend.main:app --host 127.0.0.1 --port 8000."""
import argparse
import getpass
import hashlib
import hmac
import os
import secrets
import psycopg
from psycopg.types.json import Jsonb
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .data import DATABASE, METADATA, apply_action, connect, initialize, read_state, write_state, save_change
from .seed import DISTRICT
from .metrics import calculate_metrics
from .planning import plan_changes, PRICES, LABELS, annotate_costs, blocking_reason
from .schemas import Credentials, Decision, Preview, Proposal, Registration, BudgetUpdate, ScenarioSave, ScenarioCompare, AnalysisOptions, DemoReset, HomeLayout

SESSION_TTL = 7 * 24 * 3600
COOKIE = 'obninsk_session'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scryptsalt{hashed}'


def verify_password(password, stored):
    try:
        _, salt, _ = stored.split('$')
        return hmac.compare_digest(hash_password(password, salt), stored)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password('not-a-real-account-password')


def public_user(row):
    return {key: row[key] for key in ['id', 'email', 'name', 'role']}


def create_app(db_path=DATABASE):
    @asynccontextmanager
    async def lifespan(application):
        initialize(db_path)
        yield

    app = FastAPI(title='Обнинск 2040', version='3.0.0', lifespan=lifespan)
    app.state.db_path = str(db_path)
    app.add_middleware(GZipMiddleware,minimum_size=1000)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        labels={'email':'Email','password':'Пароль','name':'Имя'}
        messages=[]
        for item in error.errors():
            field=item['loc'][-1];kind=item['type'];message=item['msg']
            if kind=='string_too_short':message=f"минимум {item.get('ctx',{}).get('min_length')} символов"
            elif kind=='string_too_long':message=f"максимум {item.get('ctx',{}).get('max_length')} символов"
            elif kind=='missing':message='заполните обязательное поле'
            elif kind=='extra_forbidden':message='недопустимое поле'
            elif kind=='value_error':message=message.removeprefix('Value error, ')
            messages.append(f"{labels.get(field,field)}: {message}")
        return JSONResponse({'detail':'; '.join(messages)},status_code=422)

    @app.middleware('http')
    async def request_policy(request: Request, call_next):
        if request.url.path.startswith('/api/'):
            if request.method in {'POST', 'PUT', 'DELETE', 'PATCH'}:
                if not request.headers.get('content-type', '').lower().startswith('application/json'):
                    return JSONResponse({'detail': 'Требуется application/json'}, status_code=415)
                # Enforce the actual size as well as the declared length, including chunked requests.
                size = 0
                chunks = []
                async for chunk in request.stream():
                    size += len(chunk)
                    # ИСПРАВЛЕНО: Увеличен лимит до 5 Мегабайт
                    if size > 5242880:
                        return JSONResponse({'detail': 'Слишком большой запрос'}, status_code=413)
                    chunks.append(chunk)
                request._body = b''.join(chunks)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
        else:
            response = await call_next(request)
        if not request.url.path.startswith('/api/') and (request.url.path=='/' or request.url.path.endswith('.html')):
            response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    def throttle(request, email):
        """Persistent 15-minute limits; no password or raw email in attempt keys."""
        stamp = time.time()
        ip = request.client.host if request.client else 'local'
        keys = [('ip:' + digest(ip), 60), ('email:' + digest(email), 12)]
        with connect(db_path) as db:
            db.execute('SELECT pg_advisory_xact_lock(204027)')
            db.execute('DELETE FROM auth_attempts WHERE attempted_at < %s', (stamp - 900,))
            for key, limit in keys:
                count = db.execute('SELECT count(*) FROM auth_attempts WHERE key=%s', (key,)).fetchone()['count']
                if count >= limit:
                    raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут.', headers={'Retry-After': '900'})
            for key, _ in keys:
                db.execute('INSERT INTO auth_attempts VALUES(%s,%s)', (key, stamp))

    def new_session(db, user, response):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at < %s', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(%s,%s,%s,%s)', (digest(token), user['id'], csrf, time.time() + SESSION_TTL))
        response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True,
                            secure=os.environ.get('OBNINSK_SECURE_COOKIE') == '1', samesite='strict', path='/')
        return {'user': public_user(user), 'csrf_token': csrf}

    def current_session(request: Request):
        token = request.cookies.get(COOKIE, '')
        with connect(db_path) as db:
            user = db.execute('''SELECT users.*, sessions.csrf_token FROM sessions JOIN users
                ON users.id=sessions.user_id WHERE token_hash=%s AND expires_at>%s''', (digest(token), time.time())).fetchone()
        if user is None:
            raise HTTPException(401, 'Войдите в аккаунт')
        if request.method != 'GET' and not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf_token']):
            raise HTTPException(403, 'Сессия устарела. Обновите страницу и попробуйте снова.')
        return dict(user)

    def moderator(user=Depends(current_session)):
        if user['role'] not in {'moderator','admin'}:
            raise HTTPException(403, 'Доступно только модератору')
        return user

    def checked_change(state, payload):
        if state['version'] != payload.base_version:
            raise HTTPException(409, 'Карта обновилась. Обновите карту и создайте новое предложение.')
        try:
            return plan_changes(state, payload.changes())
        except PermissionError as error:
            raise HTTPException(403,str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    def serialize_proposal(row):
        result = dict(row)
        result['actions']=row['action'].get('actions',[row['action']])
        result['action_names']=row.get('action_names') or {}
        missing=[a['id'] for a in result['actions'] if a['id'] not in result['action_names'] and a['entity']=='object']
        if missing:
            with connect(db_path) as db:
                names=db.execute('SELECT id,name FROM objects WHERE district_id=%s AND id=ANY(%s) UNION SELECT id,name FROM demolitions WHERE district_id=%s AND id=ANY(%s)',(DISTRICT,missing,DISTRICT,missing)).fetchall()
            result['action_names']={**{n['id']:n['name'] for n in names},**result['action_names']}
        if len(result['actions'])==1 and row.get('target_name'):
            result['action_names'].setdefault(result['actions'][0]['id'],row['target_name'])
        return result

    @app.get('/api/health')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1')
        return {'status': 'ok', 'database': 'PostgreSQL'}

    @app.post('/api/auth/register', status_code=201)
    def register(payload: Registration, response: Response, request: Request):
        throttle(request, str(payload.email))
        user = {'id': str(uuid.uuid4()), 'email': str(payload.email), 'name': payload.name,
                'role': 'user', 'password_hash': hash_password(payload.password), 'created_at': now()}
        try:
            with connect(db_path) as db:
                db.execute('INSERT INTO users(id,email,name,role,password_hash,created_at) VALUES(%(id)s,%(email)s,%(name)s,%(role)s,%(password_hash)s,%(created_at)s)', user)
                return new_session(db, user, response)
        except psycopg.errors.UniqueViolation as error:
            raise HTTPException(409, 'Этот email уже зарегистрирован') from error

    @app.post('/api/auth/login')
    def login(payload: Credentials, response: Response, request: Request):
        throttle(request, str(payload.email))
        with connect(db_path) as db:
            user = db.execute('SELECT * FROM users WHERE email=%s', (str(payload.email),)).fetchone()
            valid = verify_password(payload.password, user['password_hash'] if user else DUMMY_HASH)
            if not user or not valid:
                raise HTTPException(401, 'Неверный email или пароль')
            old_token = request.cookies.get(COOKIE)
            if old_token:
                db.execute('DELETE FROM sessions WHERE token_hash=%s', (digest(old_token),))
            return new_session(db, user, response)

    @app.get('/api/auth/me')
    def me(user=Depends(current_session)):
        return {'user': public_user(user), 'csrf_token': user['csrf_token']}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, user=Depends(current_session)):
        with connect(db_path) as db:
            db.execute('DELETE FROM sessions WHERE token_hash=%s', (digest(request.cookies.get(COOKIE, '')),))
        response.delete_cookie(COOKIE, path='/', httponly=True, samesite='strict')
        return {'ok': True}

    @app.get('/api/map/context')
    def map_context():
        with connect(db_path) as db:
            rows=db.execute('SELECT id,kind,name,geometry FROM map_context WHERE district_id=%s',(DISTRICT,)).fetchall()
        return {'type':'FeatureCollection','features':[{'type':'Feature','geometry':r['geometry'],'properties':{'id':r['id'],'kind':r['kind'],'name':r['name']}} for r in rows]}

    @app.get('/api/city')
    def city():
        with connect(db_path) as db:
            state = read_state(db)
        return {'map': METADATA, 'state': state, 'metrics': calculate_metrics(state),'demolition_costs':annotate_costs(state)}

    @app.get('/api/budget', include_in_schema=False)
    @app.get('/api/demolition-policy')
    def get_demolition_policy():
        with connect(db_path) as db:policy=read_state(db)['demolition_policy']
        return {**policy,'mode':'per_building','note':'Порог стоимости сноса одного здания. Общего бюджета нет.'}

    @app.post('/api/budget', include_in_schema=False)
    @app.post('/api/demolition-policy')
    def change_demolition_policy(payload: BudgetUpdate, user=Depends(moderator)):
        with connect(db_path) as db:
            state=read_state(db,write=True);old=state['demolition_policy']['limit']
            db.execute('UPDATE districts SET demolition_limit=%s WHERE id=%s',(payload.limit,DISTRICT))
            db.execute('INSERT INTO demolition_policy_history(district_id,moderator_id,old_limit,new_limit,created_at) VALUES(%s,%s,%s,%s,%s)',
                       (DISTRICT,user['id'],old,payload.limit,now()))
        return {'limit':payload.limit,'mode':'per_building'}

    @app.post('/api/layout/fit')
    def layout_fit(payload: HomeLayout,user=Depends(current_session)):
        from .layout import fit_layout
        with connect(db_path) as db:
            state=read_state(db)
            context=[dict(r) for r in db.execute("SELECT kind,geometry FROM map_context WHERE district_id=%s AND kind IN ('road','water')",(DISTRICT,)).fetchall()]
        try:
            houses=fit_layout(state,[h.model_dump() for h in payload.houses],[p.model_dump() for p in payload.boundary],[[p.model_dump() for p in road] for road in payload.roads],context)
            return {'houses':houses}
        except (ValueError,TypeError) as error:raise HTTPException(422,str(error)) from error

    @app.post('/api/preview')
    def preview(payload: Preview, user=Depends(current_session)):
        with connect(db_path) as db:state = read_state(db)
        after,estimate = checked_change(state, payload)
        return {'before': calculate_metrics(state), 'after': calculate_metrics(after), 'state': after,'estimate':estimate}

    @app.post('/api/proposals', status_code=201)
    def submit(payload: Proposal, user=Depends(current_session)):
        proposal_id = str(uuid.uuid4())
        with connect(db_path) as db:
            db.execute('SELECT pg_advisory_xact_lock(204027)')
            state = read_state(db, write=True)
            after,estimate=checked_change(state, payload)
            if not estimate['can_submit']:
                raise HTTPException(422,blocking_reason(estimate))
            action = Jsonb(payload.stored_action())
            duplicate = db.execute("SELECT id FROM proposals WHERE author_id=%s AND district_id=%s AND action=%s AND status='pending'", (user['id'], DISTRICT, action)).fetchone()
            if duplicate:raise HTTPException(409, 'Такое предложение уже ожидает модерации')
            pending = db.execute("SELECT count(*) FROM proposals WHERE author_id=%s AND status='pending'", (user['id'],)).fetchone()['count']
            if pending >= 20:raise HTTPException(429, 'У вас уже 20 заявок на модерации. Дождитесь решения.')
            target_name=estimate['lines'][0]['name'] if len(estimate['lines'])==1 else f"Набор из {len(estimate['lines'])} изменений"
            db.execute('''INSERT INTO proposals(id,district_id,author_id,action,reason,base_version,created_at,target_name,estimated_cost,action_names)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (proposal_id, DISTRICT, user['id'], action, payload.reason.strip() or 'Предложение изменений городской инфраструктуры.', payload.base_version, now(), target_name,estimate['total'],Jsonb({line['id']:line['name'] for line in estimate['lines']})))
        return {'id': proposal_id, 'status': 'pending', 'message': 'Набор отправлен на модерацию. Изменения ещё не применены.'}

    @app.get('/api/proposals')
    def list_proposals(user=Depends(current_session)):
        query = '''SELECT proposals.*, author.name AS author_name, reviewer.name AS reviewer_name
            FROM proposals JOIN users author ON author.id=proposals.author_id
            LEFT JOIN users reviewer ON reviewer.id=proposals.reviewer_id'''
        query += ' WHERE proposals.district_id=%s'
        args = (DISTRICT,)
        if user['role'] not in {'moderator','admin'}:
            query += ' AND proposals.author_id=%s'
            args += (user['id'],)
        query += ' ORDER BY proposals.created_at DESC'
        with connect(db_path) as db:
            rows = db.execute(query, args).fetchall()
        return {'items': [serialize_proposal(row) for row in rows]}

    @app.get('/api/proposals/{proposal_id}/preview')
    def preview_proposal(proposal_id: str, user=Depends(moderator)):
        with connect(db_path) as db:
            row = db.execute('SELECT * FROM proposals WHERE id=%s AND district_id=%s', (proposal_id, DISTRICT)).fetchone()
            state = read_state(db)
        if row is None:
            raise HTTPException(404, 'Заявка не найдена')
        if row['status'] != 'pending':
            raise HTTPException(409, 'Заявка уже закрыта')
        payload = Preview(**({'actions':row['action']['actions']} if 'actions' in row['action'] else {'action':row['action']}),base_version=row['base_version'])
        after,estimate = checked_change(state, payload)
        return {'before': calculate_metrics(state), 'after': calculate_metrics(after), 'state': after,'estimate':estimate}

    @app.post('/api/proposals/{proposal_id}/decision')
    def decide(proposal_id: str, payload: Decision, user=Depends(moderator)):
        with connect(db_path) as db:
            db.execute('SELECT pg_advisory_xact_lock(204027)')
            row = db.execute('SELECT * FROM proposals WHERE id=%s AND district_id=%s', (proposal_id, DISTRICT)).fetchone()
            if row is None:
                raise HTTPException(404, 'Заявка не найдена')
            if row['status'] != 'pending':
                raise HTTPException(409, 'Заявка уже закрыта. Повторное решение невозможно.')
            if row['author_id'] == user['id'] and user['role']!='admin':
                raise HTTPException(403, 'Собственную заявку должен рассмотреть другой модератор')
            applied_version = None
            if payload.decision == 'approved':
                state = read_state(db, write=True)
                change = Preview(**({'actions':row['action']['actions']} if 'actions' in row['action'] else {'action':row['action']}),base_version=row['base_version'])
                after,estimate = checked_change(state, change)
                if not estimate['can_submit']:raise HTTPException(409,blocking_reason(estimate))
                after['version'] += 1
                applied_version = after['version']
                for action in change.changes():save_change(db, after, action)
                db.execute('UPDATE proposals SET estimated_cost=%s WHERE id=%s',(estimate['total'],proposal_id))
            closed_at = now()
            db.execute('''UPDATE proposals SET status=%s,closed_at=%s,reviewer_id=%s,comment=%s,applied_version=%s
                WHERE id=%s''', (payload.decision, closed_at, user['id'], payload.comment, applied_version, proposal_id))
        return {'id': proposal_id, 'status': payload.decision, 'closed_at': closed_at, 'applied_version': applied_version}

    @app.post('/api/admin/demo-reset')
    def demo_reset(payload: DemoReset,user=Depends(current_session)):
        if user['role']!='admin':raise HTTPException(403,'Доступно только администратору')
        with connect(db_path) as db:
            db.execute('SELECT pg_advisory_xact_lock(204027)')
            state=read_state(db,write=True)
            if payload.action=='undo':
                backup=db.execute('SELECT * FROM demo_backups WHERE district_id=%s ORDER BY id DESC LIMIT 1 FOR UPDATE',(DISTRICT,)).fetchone()
                if not backup:raise HTTPException(409,'Нет резервной копии для восстановления')
                saved=backup['payload'];original_version=saved['state']['version'];restored=saved['state'];restored['version']=state['version']+1
                write_state(db,restored)
                for area in restored.get('areas',[]):
                    db.execute('INSERT INTO planning_areas(id,district_id,name,x,y,width,height,geom) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(area['id'],DISTRICT,area['name'],area['x'],area['y'],area['width'],area['height'],Jsonb(area['geom'])))
                for item in restored.get('demolished',[]):
                    db.execute('INSERT INTO demolitions(district_id,id,name,geom) VALUES(%s,%s,%s,%s)',(DISTRICT,item['id'],item['name'],Jsonb(item['geom'])))
                for table in ('proposals','scenarios'):
                    db.execute(f'DELETE FROM {table} WHERE district_id=%s',(DISTRICT,))
                    for row in saved[table]:
                        if table=='proposals' and row['status']=='pending' and row['base_version']==original_version:
                            row['base_version']=restored['version']
                        cols=list(row);values=[Jsonb(row[k]) if k in {'action','actions','action_names'} else row[k] for k in cols]
                        db.execute(f'INSERT INTO {table}({",".join(cols)}) VALUES({",".join(["%s"]*len(cols))})',values)
                db.execute('DELETE FROM demo_backups WHERE id=%s',(backup['id'],))
            else:
                state['context']=[dict(r) for r in db.execute('SELECT id,kind,name,geometry FROM map_context WHERE district_id=%s',(DISTRICT,)).fetchall()]
                saved={'state':state,**{table:[dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE district_id=%s',(DISTRICT,)).fetchall()] for table in ('proposals','scenarios')}}
                db.execute('INSERT INTO demo_backups(district_id,payload,created_at) VALUES(%s,%s,%s)',(DISTRICT,Jsonb(saved),now()))
                db.execute('DELETE FROM proposals WHERE district_id=%s',(DISTRICT,))
                if payload.action=='reset_all':
                    from .data import seed_state
                    initial=seed_state();initial['version']=state['version']+1
                    write_state(db,initial)
                    db.execute('DELETE FROM scenarios WHERE district_id=%s',(DISTRICT,))
        return {'ok':True,'action':payload.action}

    @app.get('/api/scenarios')
    def list_scenarios(user=Depends(current_session)):
        with connect(db_path) as db:
            rows=db.execute('SELECT id,name,actions,base_version,created_at FROM scenarios WHERE author_id=%s AND district_id=%s ORDER BY created_at DESC',(user['id'],DISTRICT)).fetchall()
        return {'items':[dict(r) for r in rows]}

    @app.post('/api/scenarios',status_code=201)
    def save_scenario(payload: ScenarioSave,user=Depends(current_session)):
        with connect(db_path) as db:
            db.execute('SELECT pg_advisory_xact_lock(204027)')
            state=read_state(db);checked_change(state,payload)
            if db.execute('SELECT count(*) FROM scenarios WHERE author_id=%s',(user['id'],)).fetchone()['count']>=50:
                raise HTTPException(429,'Можно сохранить до 50 сценариев')
            sid=str(uuid.uuid4())
            db.execute('INSERT INTO scenarios(id,district_id,author_id,name,actions,base_version,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(sid,DISTRICT,user['id'],payload.name,Jsonb(payload.changes()),payload.base_version,now()))
        return {'id':sid,'name':payload.name}

    def owned_scenario(db,sid,user):
        row=db.execute('SELECT * FROM scenarios WHERE id=%s AND author_id=%s AND district_id=%s',(sid,user['id'],DISTRICT)).fetchone()
        if not row:raise HTTPException(404,'Сценарий не найден')
        return row

    @app.post('/api/scenarios/compare')
    def compare_scenarios(payload: ScenarioCompare,user=Depends(current_session)):
        with connect(db_path) as db:
            state=read_state(db);saved=[owned_scenario(db,sid,user) for sid in dict.fromkeys(payload.ids)]
        items=[]
        for row in saved:
            item=dict(id=row['id'],name=row['name'],rebased=row['base_version']!=state['version'])
            try:
                after,estimate=plan_changes(state,row['actions'])
                metrics=calculate_metrics(after,payload.park_radius,payload.park_radii)
                summary={k:metrics[k] for k in ['park_percent','transport_access','facility_provision','average_stop','total_residents','home_count']}
                value=summary[payload.target]
                meets=value is not None and (value<=payload.threshold if payload.target=='average_stop' else value>=payload.threshold)
                item.update(metrics=summary,total=estimate['total'],can_submit=estimate['can_submit'],meets_target=meets,error='')
            except (ValueError,PermissionError) as error:item.update(error=str(error),can_submit=False,meets_target=False)
            items.append(item)
        suitable=[i for i in items if i['can_submit'] and i['meets_target']]
        recommended=min(suitable,key=lambda i:(i['total'],i['id']))['id'] if suitable else None
        return {'items':items,'recommended_id':recommended,'evaluated_version':state['version'],'message':'Среди достигших цели выбран вариант с минимальной справочной стоимостью.' if recommended else 'Ни один доступный сценарий не достиг цели.'}

    @app.post('/api/scenarios/{sid}/evaluate')
    def evaluate_scenario(sid:str,payload:AnalysisOptions,user=Depends(current_session)):
        with connect(db_path) as db:
            row=owned_scenario(db,sid,user);state=read_state(db)
        try:after,estimate=plan_changes(state,row['actions'])
        except (ValueError,PermissionError) as error:raise HTTPException(409,str(error)) from error
        return {'before':calculate_metrics(state,payload.park_radius,payload.park_radii),'after':calculate_metrics(after,payload.park_radius,payload.park_radii),
                'state':after,'estimate':estimate,'actions':row['actions'],'base_version':state['version'],'rebased':row['base_version']!=state['version'],'name':row['name']}

    dist = Path(__file__).parent.parent / 'frontend' / 'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    else:
        @app.get('/')
        def build_hint():
            return {'message': 'Соберите frontend: cd frontend && npm ci && npm run build. Затем перезапустите backend.'}
    return app


app = create_app()


def create_admin(email, password, db_path=DATABASE):
    account=Registration(email=email,password=password,name='Администратор Обнинск 2040')
    user={'id':str(uuid.uuid4()),'email':account.email,'name':account.name,'role':'admin',
          'password_hash':hash_password(account.password),'created_at':now()}
    with connect(db_path) as db:
        db.execute('INSERT INTO users(id,email,name,role,password_hash,created_at) VALUES(%(id)s,%(email)s,%(name)s,%(role)s,%(password_hash)s,%(created_at)s)',user)
    return public_user(user)


def main():
    parser = argparse.ArgumentParser(description='Управление локальным проектом Обнинск 2040')
    parser.add_argument('command', choices=['promote','create-admin'])
    parser.add_argument('email', help='Email уже зарегистрированного пользователя')
    args = parser.parse_args()
    initialize(DATABASE)
    if args.command=='create-admin':
        password=getpass.getpass('Пароль администратора: ')
        if password!=getpass.getpass('Повторите пароль: '):parser.exit(1,'Пароли не совпадают.\n')
        try:create_admin(args.email,password)
        except psycopg.errors.UniqueViolation:parser.exit(1,'Этот email уже занят. Аккаунт не изменён.\n')
        print('Администратор создан. Войдите на сайте.');return
    with connect(DATABASE) as db:
        result = db.execute("UPDATE users SET role='moderator' WHERE email=%s", (args.email.strip().lower(),))
        if result.rowcount != 1:
            parser.exit(1, 'Пользователь не найден. Сначала зарегистрируйте его на сайте.\n')
    print('Роль модератора назначена. Обновите страницу сайта.')


if __name__ == '__main__':
    main()
