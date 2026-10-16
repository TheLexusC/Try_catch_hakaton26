import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app, verify_password
from backend.data import connect, DATABASE
from backend.demo_seed import seed_state
from psycopg import sql
from psycopg.conninfo import make_conninfo
import os, uuid
MAP=seed_state()

PASSWORD='Local test password 2040!'

@pytest.fixture
def env(monkeypatch):
    import backend.data as data
    def fixture_seed():
        state=seed_state()
        for obj in state["objects"]:obj.update(source="test",geom=None,node_id=None,approach=None)
        return state
    monkeypatch.setattr(data,"seed_state",fixture_seed)
    base=os.getenv('OBNINSK_TEST_DATABASE_URL')
    if not base:pytest.skip('Set OBNINSK_TEST_DATABASE_URL to a disposable PostgreSQL database')
    schema='test_'+uuid.uuid4().hex
    with connect(base) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    dsn=make_conninfo(base, options='-c search_path='+schema)
    try:
        app=create_app(dsn)
        with TestClient(app) as client:yield app,client,dsn
    finally:
        with connect(base) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def register(client,email='resident@example.com'):
    r=client.post('/api/auth/register',json={'email':email,'password':PASSWORD,'name':'Тестовый житель'})
    assert r.status_code==201,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf_token']
    return r

def moderator(app,path,email='moderator@example.com'):
    c=TestClient(app);register(c,email)
    with connect(path) as db:db.execute("UPDATE users SET role='moderator' WHERE email=%s",(email,))
    return c

def proposal(c,index=0,version=0):
    return c.post('/api/proposals',json={'action':{'entity':'edge','operation':'update','id':MAP['edges'][index]['id'],'values':{'closed':True}},'base_version':version,'reason':'Проверить безопасность этого пешеходного участка.'})

def decide(c,pid,decision='approved'):
    return c.post(f'/api/proposals/{pid}/decision',json={'decision':decision,'comment':'Рассмотрено в рамках учебного сценария.'})

def test_registration_hashes_cookie_and_permissions(env):
    _,c,path=env;r=register(c,'Resident@example.com')
    assert r.json()['user']['role']=='user'
    assert 'HttpOnly' in r.headers['set-cookie'] and 'samesite=strict' in r.headers['set-cookie'].lower()
    with connect(path) as db:
        stored=db.execute('SELECT password_hash FROM users').fetchone()['password_hash']
        assert stored!=PASSWORD and verify_password(PASSWORD,stored)
        assert db.execute('SELECT token_hash FROM sessions').fetchone()['token_hash']!=c.cookies.get('obninsk_session')
    payload={'email':'resident@example.com','password':PASSWORD,'name':'Other'}
    assert c.post('/api/auth/register',json=payload).status_code==409
    assert c.post('/api/auth/register',json={**payload,'role':'moderator'}).status_code==422

def test_logout_login_expiry_csrf(env):
    _,c,path=env;register(c);assert c.get('/api/auth/me').status_code==200
    csrf=c.headers.pop('X-CSRF-Token');assert c.post('/api/auth/logout',json={}).status_code==403
    c.headers['X-CSRF-Token']=csrf;assert c.post('/api/auth/logout',json={}).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/login',json={'email':'resident@example.com','password':PASSWORD}).status_code==200
    with connect(path) as db:db.execute('UPDATE sessions SET expires_at=%s',(time.time()-1,))
    assert c.get('/api/auth/me').status_code==401

def test_password_spaces(env):
    _,c,path=env;pw='  my exact password  '
    assert c.post('/api/auth/register',json={'email':'space@example.com','password':pw,'name':' Spaces '}).status_code==201
    with connect(path) as db:stored=db.execute('SELECT password_hash FROM users').fetchone()['password_hash']
    assert verify_password(pw,stored) and not verify_password(pw.strip(),stored)

def test_guest_read_only(env):
    _,c,_=env
    assert c.get('/api/city').status_code==200
    assert proposal(c).status_code==401 and c.get('/api/proposals').status_code==401

def test_approval_lifecycle(env):
    app,c,path=env;register(c);before=c.get('/api/city').json()
    p=proposal(c);assert p.status_code==201;pid=p.json()['id']
    assert c.get('/api/city').json()['state']==before['state']
    assert decide(c,pid).status_code==403
    mod=moderator(app,path);preview=mod.get(f'/api/proposals/{pid}/preview');assert preview.status_code==200
    assert decide(mod,pid).status_code==200
    city=c.get('/api/city').json();assert city['state']['version']==1 and next(e for e in city['state']['edges'] if e['id']==MAP['edges'][0]['id'])['closed']
    assert city['metrics']==preview.json()['after']
    item=c.get('/api/proposals').json()['items'][0]
    assert item['status']=='approved' and item['closed_at'] and item['reviewer_id'] and item['applied_version']==1
    assert decide(mod,pid).status_code==409 and decide(mod,pid,'rejected').status_code==409
    assert c.get('/api/city').json()['state']['version']==1
    mod.close()

def test_rejection(env):
    app,c,path=env;register(c);before=c.get('/api/city').json()['state'];pid=proposal(c).json()['id'];mod=moderator(app,path)
    assert decide(mod,pid,'rejected').status_code==200
    assert c.get('/api/city').json()['state']==before
    item=c.get('/api/proposals').json()['items'][0]
    assert item['status']=='rejected' and item['closed_at']
    mod.close()

def test_private_requests_and_self_review(env):
    app,c,path=env;register(c);pid=proposal(c).json()['id'];other=TestClient(app);register(other,'other@example.com')
    assert other.get('/api/proposals').json()['items']==[]
    assert other.get(f'/api/proposals/{pid}/preview').status_code==403
    with connect(path) as db:db.execute("UPDATE users SET role='moderator' WHERE email='resident@example.com'")
    assert decide(c,pid).status_code==403
    other.close()

def test_stale_approval_and_submission(env):
    app,c,path=env;register(c);one=proposal(c,0).json()['id'];two=proposal(c,1).json()['id'];mod=moderator(app,path)
    assert decide(mod,one).status_code==200
    assert decide(mod,two).status_code==409
    assert proposal(c,2,0).status_code==409
    assert mod.get(f'/api/proposals/{two}/preview').status_code==409
    assert decide(mod,two,'rejected').status_code==200
    assert c.get('/api/city').json()['state']['version']==1
    mod.close()

def test_duplicate_and_invalid_actions(env):
    _,c,_=env;register(c);assert proposal(c).status_code==201 and proposal(c).status_code==409
    for action in [dict(entity='object',operation='delete',id='missing',values={}),
                   dict(entity='object',operation='update',id='h1',values={'x':-10}),
                   dict(entity='object',operation='add',id='bad',values={'name':'Bad','kind':'park'}),
                   dict(entity='edge',operation='update',id='missing',values={'closed':True})]:
        assert c.post('/api/preview',json={'action':action,'base_version':0}).status_code==422

def test_restart_persistence(env):
    _,c,path=env;register(c);pid=proposal(c).json()['id'];cookie=c.cookies.get('obninsk_session')
    with TestClient(create_app(str(path))) as other:
        other.cookies.set('obninsk_session',cookie)
        assert other.get('/api/auth/me').status_code==200 and other.get('/api/proposals').json()['items'][0]['id']==pid

def test_origin_and_size_limits(env):
    _,c,_=env;register(c)
    assert c.post('/api/auth/logout',json={},headers={'Origin':'https://untrusted.example'}).status_code==403
    assert c.post('/api/auth/login',content='x'*20000,headers={'Content-Type':'application/json'}).status_code==413
    assert c.post('/api/auth/login',content='abc',headers={'Content-Type':'text/plain'}).status_code==415

def test_login_rate_limit(env):
    _,c,_=env
    for _ in range(12):assert c.post('/api/auth/login',json={'email':'unknown@example.com','password':PASSWORD}).status_code==401
    assert c.post('/api/auth/login',json={'email':'unknown@example.com','password':PASSWORD}).status_code==429

def test_concurrent_moderators(env):
    app,c,path=env;register(c);pid=proposal(c).json()['id'];m1=moderator(app,path);m2=moderator(app,path,'mod2@example.com')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda mod:decide(mod,pid).status_code,[m1,m2]))
    assert sorted(results)==[200,409] and c.get('/api/city').json()['state']['version']==1
    m1.close();m2.close()

@pytest.mark.parametrize('action',[
    dict(entity='object',operation='add',id='newstop',values=dict(name='Новая остановка',kind='stop',x=50,y=50)),
    dict(entity='object',operation='add',id='newpark',values=dict(name='Новый парк',kind='park',x=500,y=500)),
    dict(entity='object',operation='delete',id='h1',values={}),
    dict(entity='object',operation='delete',id='p1',values={}),
    dict(entity='object',operation='update',id='s1',values={'x':900,'y':800}),
    dict(entity='edge',operation='update',id='e1',values={'closed':True}),
])
def test_all_mutations_preview_and_approval(env,action):
    app,c,dsn=env;register(c)
    before=c.get('/api/city').json()['state']
    payload=dict(action=action,base_version=0)
    preview=c.post('/api/preview',json=payload)
    assert preview.status_code==200,preview.text
    assert c.get('/api/city').json()['state']==before
    proposal=c.post('/api/proposals',json=dict(payload,reason='Изменение инфраструктуры по запросу жителей.'))
    assert proposal.status_code==201,proposal.text
    mod=moderator(app,dsn)
    assert decide(mod,proposal.json()['id']).status_code==200
    actual=c.get('/api/city').json()
    assert actual['state']['version']==1 and actual['metrics']==preview.json()['after']
    table={'object':'objects','node':'nodes','edge':'edges'}[action['entity']]
    with connect(dsn) as db:
        row=db.execute(sql.SQL('SELECT * FROM {} WHERE id=%s').format(sql.Identifier(table)),(action['id'],)).fetchone()
    assert (row is None)==(action['operation']=='delete')
    mod.close()


def test_direct_postgres_load_is_visible_in_api(env):
    _,c,dsn=env
    with connect(dsn) as db:db.execute("UPDATE objects SET load=999 WHERE id='cl1'")
    city=c.get('/api/city').json()
    assert next(o for o in city['state']['objects'] if o['id']=='cl1')['load']==999
    assert city['metrics']['overloaded']>=1


@pytest.mark.parametrize('action',[
    dict(entity='object',operation='update',id='h1',values={'x':50}),
    dict(entity='object',operation='update',id='h1',values={'residents':1}),
    dict(entity='object',operation='add',id='fake',values={'name':'Fake','kind':'home','x':50,'y':50}),
    dict(entity='object',operation='add',id='fake',values={'name':'Fake','kind':'park','x':50,'y':50,'load':10}),
    dict(entity='node',operation='update',id='n1',values={'x':50}),
    dict(entity='edge',operation='delete',id='e1',values={}),
])
def test_resident_cannot_bypass_permissions(env,action):
    _,client,_=env;register(client)
    payload=dict(action=action,base_version=0)
    assert client.post('/api/preview',json=payload).status_code==403
    assert client.post('/api/proposals',json=dict(payload,reason='Попытка изменить неизменяемый объект.')).status_code==403


def test_context_api_is_public_geojson(env):
    _,client,_=env
    response=client.get('/api/map/context')
    assert response.status_code==200 and response.json()['type']=='FeatureCollection'


def test_demolition_keeps_map_marker_and_cannot_repeat(env):
    from psycopg.types.json import Jsonb
    app,client,dsn=env;register(client)
    geom={'type':'Polygon','coordinates':[[[36.61,55.10],[36.611,55.10],[36.611,55.101],[36.61,55.10]]]}
    with connect(dsn) as db:db.execute("UPDATE objects SET geom=%s WHERE id='h1'",(Jsonb(geom),))
    payload=dict(action=dict(entity='object',operation='delete',id='h1',values={}),base_version=0)
    preview=client.post('/api/preview',json=payload)
    assert preview.status_code==200 and preview.json()['state']['demolished'][0]['id']=='h1'
    proposal=client.post('/api/proposals',json=dict(payload,reason='Предложение сноса существующего дома.'))
    mod=moderator(app,dsn)
    assert decide(mod,proposal.json()['id']).status_code==200
    assert client.get('/api/city').json()['state']['demolished'][0]['geom']==geom
    assert client.post('/api/proposals',json=dict(payload,base_version=1,reason='Повторное предложение сноса.')).status_code==422
    mod.close()


def test_stop_relocation_preserves_identity_and_reanchors_after_approval(env):
    from backend.geo import NodeIndex
    app,c,dsn=env;register(c)
    before=c.get('/api/city').json()['state'];stop=next(o for o in before['objects'] if o['kind']=='stop')
    payload=dict(action=dict(entity='object',operation='update',id=stop['id'],values=dict(x=900,y=800)),base_version=0)
    preview=c.post('/api/preview',json=payload);assert preview.status_code==200,preview.text
    assert c.get('/api/city').json()['state']==before
    moved=next(o for o in preview.json()['state']['objects'] if o['id']==stop['id'])
    assert moved['name']==stop['name'] and moved['kind']=='stop' and moved['x']==900 and moved['y']==800
    anchor,approach=NodeIndex(before['nodes']).nearest(900,800)
    assert moved['node_id']==anchor and moved['approach']==round(approach,2)
    p=c.post('/api/proposals',json=dict(payload,reason='Перенести остановку ближе к жилым домам.'));assert p.status_code==201
    assert c.get('/api/city').json()['state']==before
    mod=moderator(app,dsn);assert decide(mod,p.json()['id']).status_code==200
    actual=c.get('/api/city').json()
    assert next(o for o in actual['state']['objects'] if o['id']==stop['id'])==moved
    assert actual['metrics']==preview.json()['after']
    mod.close()


@pytest.mark.parametrize('values',[{'x':900},{'x':900,'y':800,'name':'Переименование'},{'x':900,'y':800,'capacity':900}])
def test_stop_relocation_rejects_other_edits(env,values):
    _,c,_=env;register(c)
    stop=next(o for o in c.get('/api/city').json()['state']['objects'] if o['kind']=='stop')
    assert c.post('/api/preview',json=dict(action=dict(entity='object',operation='update',id=stop['id'],values=values),base_version=0)).status_code==403
