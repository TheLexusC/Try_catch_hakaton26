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

def test_stale_approval_and_submission_use_current_map(env):
    app,c,path=env;register(c);one=proposal(c,0).json()['id'];two=proposal(c,1).json()['id'];mod=moderator(app,path)
    assert decide(mod,one).status_code==200
    assert mod.get(f'/api/proposals/{two}/preview').status_code==200
    assert decide(mod,two).status_code==200
    assert proposal(c,2,0).status_code==201
    assert c.get('/api/city').json()['state']['version']==2
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
    assert c.post('/api/auth/logout',json={},headers={'Origin':'https://untrusted.example'}).status_code==200
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
    dict(entity='object',operation='add',id='fake',values={'name':'Fake','kind':'home','x':50,'y':50,'capacity':999}),
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
    with connect(dsn) as db:
        db.execute("UPDATE objects SET geom=%s WHERE id='h1'",(Jsonb(geom),))
        db.execute("UPDATE districts SET demolition_limit=100000000")
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


def batch_payload():
    return dict(actions=[dict(entity='object',operation='add',id='batch-park',values=dict(name='Сквер набора',kind='park',x=500,y=500)),
                         dict(entity='object',operation='update',id='s1',values=dict(x=700,y=600))],base_version=0)


def test_batch_combines_metrics_without_global_spending(env):
    from backend.data import apply_action
    from backend.metrics import calculate_metrics
    app,c,dsn=env;register(c);before=c.get('/api/city').json()['state'];payload=batch_payload()
    p=c.post('/api/preview',json=payload);assert p.status_code==200,p.text
    expected=before
    for action in payload['actions']:expected=apply_action(expected,action)
    assert p.json()['after']==calculate_metrics(expected)
    assert p.json()['estimate']['total']==2_150_000
    assert c.get('/api/city').json()['state']==before
    submitted=c.post('/api/proposals',json=dict(payload,reason='Совместно перенести остановку и создать сквер.'));assert submitted.status_code==201,submitted.text
    mod=moderator(app,dsn);pid=submitted.json()['id']
    assert 'budget' not in c.get('/api/city').json()['state']
    assert mod.get(f'/api/proposals/{pid}/preview').json()['after']==p.json()['after']
    assert decide(mod,pid).status_code==200
    actual=c.get('/api/city').json()
    assert actual['state']['demolition_policy']==before['demolition_policy'] and actual['state']['version']==1
    assert actual['metrics']==p.json()['after']
    assert decide(mod,pid).status_code==409
    assert c.get('/api/city').json()['state']['demolition_policy']==before['demolition_policy']
    assert c.get('/api/proposals').json()['items'][0]['actions']==payload['actions']
    mod.close()


def test_demolition_threshold_checked_at_submission_and_approval(env):
    app,c,dsn=env;register(c);mod=moderator(app,dsn)
    city=c.get('/api/city').json();cost=city['demolition_costs']['h1']['amount']
    payload=dict(action=dict(entity='object',operation='delete',id='h1',values={}),base_version=0)
    assert c.post('/api/demolition-policy',json={'limit':cost}).status_code==403
    assert mod.post('/api/demolition-policy',json={'limit':cost}).status_code==200
    p=c.post('/api/proposals',json=dict(payload,reason='Цена равна порогу для одного дома.'));assert p.status_code==201,p.text
    assert mod.post('/api/demolition-policy',json={'limit':cost-1}).status_code==200
    preview=c.post('/api/preview',json=payload).json()
    assert not preview['estimate']['can_submit'] and preview['estimate']['blocked'][0]['amount']==cost
    r=c.post('/api/proposals',json=dict(payload,reason='Цена дома выше нового порога.'))
    assert r.status_code==422 and 'из-за цены' in r.json()['detail']
    assert decide(mod,p.json()['id']).status_code==409
    assert any(o['id']=='h1' for o in c.get('/api/city').json()['state']['objects'])
    assert mod.post('/api/demolition-policy',json={'limit':cost}).status_code==200
    assert decide(mod,p.json()['id']).status_code==200
    assert c.get('/api/city').json()['state']['demolition_policy']['limit']==cost
    assert mod.post('/api/demolition-policy',json={'limit':0}).status_code==200
    with connect(dsn) as db:assert db.execute('SELECT count(*) FROM demolition_policy_history').fetchone()['count']==4
    mod.close()


def test_invalid_batch_has_no_partial_effect_and_remains_private(env):
    app,c,dsn=env;register(c);before=c.get('/api/city').json()['state']
    p=batch_payload();p['actions'].append(dict(entity='object',operation='delete',id='missing',values={}))
    assert c.post('/api/proposals',json=dict(p,reason='Некорректный набор не должен применяться частично.')).status_code==422
    assert c.get('/api/city').json()['state']==before
    p=batch_payload();p['actions'].append(p['actions'][0])
    assert c.post('/api/preview',json=p).status_code==422
    pid=c.post('/api/proposals',json=dict(batch_payload(),reason='Приватный набор изменений одного жителя.')).json()['id']
    other=TestClient(app);register(other,'other-batch@example.com')
    assert other.get('/api/proposals').json()['items']==[]
    assert other.get(f'/api/proposals/{pid}/preview').status_code==403
    mod=moderator(app,dsn);assert decide(mod,pid,'rejected').status_code==200
    assert c.get('/api/city').json()['state']==before
    mod.close();other.close()


def test_batch_contract_limits_and_client_cannot_set_price(env):
    _,c,_=env;register(c)
    p=batch_payload()
    for bad in [dict(actions=[],base_version=0),dict(p,action=p['actions'][0]),dict(actions=p['actions']*11,base_version=0),dict(p,estimated_cost=0)]:
        assert c.post('/api/preview',json=bad).status_code==422


def test_registration_accepts_same_local_origin_at_any_launch_port(env):
    app,_,_=env
    for host in ['127.0.0.1:8123','localhost:8467']:
        with TestClient(app,base_url='http://'+host) as c:
            response=c.post('/api/auth/register',json=dict(email=host.replace(':','-')+'@obninsk.test',password=PASSWORD,name='Локальный житель'),headers={'Origin':'http://'+host})
            assert response.status_code==201,response.text
            c.headers['X-CSRF-Token']=response.json()['csrf_token']
            assert c.post('/api/auth/logout',json={},headers={'Origin':'http://'+host}).status_code==200
    with TestClient(app,base_url='http://127.0.0.1:8123') as c:
        assert c.post('/api/auth/register',json=dict(email='different-port@obninsk.test',password=PASSWORD,name='Other'),headers={'Origin':'http://127.0.0.1:8124'}).status_code==201
        assert c.post('/api/auth/register',json=dict(email='different-origin@obninsk.test',password=PASSWORD,name='Other'),headers={'Origin':'https://evil.example'}).status_code==201


def test_admin_can_login_and_moderate_and_budget_but_cannot_self_register_role(env):
    from backend.main import create_admin
    app,c,dsn=env
    account=create_admin('admin@obninsk.test',PASSWORD,dsn)
    assert account['role']=='admin'
    response=c.post('/api/auth/login',json=dict(email='admin@obninsk.test',password=PASSWORD))
    assert response.status_code==200 and response.json()['user']['role']=='admin'
    c.headers['X-CSRF-Token']=response.json()['csrf_token']
    assert c.post('/api/budget',json={'limit':11_000_000}).status_code==200
    resident=TestClient(app);register(resident,'resident-admin-test@obninsk.test')
    pid=proposal(resident).json()['id']
    assert any(p['id']==pid for p in c.get('/api/proposals').json()['items'])
    assert decide(c,pid).status_code==200
    assert resident.post('/api/auth/register',json=dict(email='fake-admin@obninsk.test',password=PASSWORD,name='Other',role='admin')).status_code==422
    with connect(dsn) as db:
        row=db.execute('SELECT password_hash FROM users WHERE id=%s',(account['id'],)).fetchone()
        assert row['password_hash']!=PASSWORD and verify_password(PASSWORD,row['password_hash'])
    resident.close()


def test_registration_errors_are_readable_without_password_echo(env):
    _,c,_=env
    password='short'
    r=c.post('/api/auth/register',json=dict(email='not-an-email',password=password,name='Я'))
    assert r.status_code==422
    assert isinstance(r.json()['detail'],str) and 'Email' in r.json()['detail']
    assert password not in r.text and 'Email' in r.json()['detail']


@pytest.mark.parametrize('name,password',[('',''),('Я','1'),('Очень длинное имя '*10,'любой пароль')])
def test_registration_only_checks_email_format(env,name,password):
    _,c,_=env
    payload=dict(email='name@mail.ru',name=name,password=password)
    response=c.post('/api/auth/register',json=payload,headers={'Origin':'http://localhost:9999'})
    assert response.status_code==201,response.text
    c.headers['X-CSRF-Token']=response.json()['csrf_token']
    assert c.post('/api/auth/logout',json={}).status_code==200
    assert c.post('/api/auth/login',json=dict(email='name@mail.ru',password=password)).status_code==200
    assert c.post('/api/auth/register',json=dict(payload,email='wrong')).status_code==422


@pytest.mark.parametrize('reason',[None,'','Да'])
def test_submission_does_not_require_long_explanation(env,reason):
    _,c,_=env;register(c)
    payload=dict(action=dict(entity='edge',operation='update',id='e1',values=dict(closed=True)),base_version=0)
    if reason is not None:payload['reason']=reason
    r=c.post('/api/proposals',json=payload)
    assert r.status_code==201,r.text
    items=c.get('/api/proposals').json()['items']
    assert items[0]['id']==r.json()['id'] and items[0]['status']=='pending'
    assert items[0]['reason']==(reason or 'Предложение изменений городской инфраструктуры.')


def test_multiple_homes_each_below_limit_are_allowed_even_when_sum_exceeds(env):
    app,c,dsn=env;register(c);mod=moderator(app,dsn)
    costs=c.get('/api/city').json()['demolition_costs']
    limit=max(costs['h1']['amount'],costs['h2']['amount'])
    assert mod.post('/api/demolition-policy',json={'limit':limit}).status_code==200
    actions=[dict(entity='object',operation='delete',id=i,values={}) for i in ['h1','h2']]
    payload=dict(actions=actions,base_version=0)
    preview=c.post('/api/preview',json=payload).json()
    assert preview['estimate']['total']>limit and preview['estimate']['can_submit']
    r=c.post('/api/proposals',json=payload);assert r.status_code==201,r.text
    assert decide(mod,r.json()['id']).status_code==200
    city=c.get('/api/city').json()
    assert city['state']['demolition_policy']['limit']==limit and 'budget' not in city['state']
    assert not any(o['id'] in ['h1','h2'] for o in city['state']['objects'])
    mod.close()


def test_demolition_limit_does_not_limit_parks_or_stop_relocation(env):
    app,c,dsn=env;register(c);mod=moderator(app,dsn)
    assert mod.post('/api/demolition-policy',json={'limit':0}).status_code==200
    payload=batch_payload()
    quote=c.post('/api/preview',json=payload).json()['estimate']
    assert quote['total']==2150000 and quote['can_submit']
    r=c.post('/api/proposals',json=payload);assert r.status_code==201
    assert decide(mod,r.json()['id']).status_code==200
    mod.close()



def home_action(oid='new-home'):
    return dict(entity='object',operation='add',id=oid,values=dict(name='Проектный дом',kind='home',x=500,y=500,width=20,height=30,residents=250))


def test_new_home_and_area_are_moderated_persist_and_change_population(env):
    app,c,dsn=env;register(c);before=c.get('/api/city').json()
    area=dict(entity='area',operation='add',id='new-area',values=dict(name='Новый район',x=500,y=500,width=600,height=600))
    payload=dict(actions=[area,home_action()],base_version=0)
    preview=c.post('/api/preview',json=payload);assert preview.status_code==200,preview.text
    assert preview.json()['after']['total_residents']==before['metrics']['total_residents']+250
    assert preview.json()['after']['home_count']==before['metrics']['home_count']+1
    assert preview.json()['state']['areas'][0]['name']=='Новый район'
    assert c.get('/api/city').json()['state']==before['state']
    r=c.post('/api/proposals',json=payload);assert r.status_code==201,r.text
    mod=moderator(app,dsn);assert decide(mod,r.json()['id']).status_code==200
    actual=c.get('/api/city').json()
    obj=next(o for o in actual['state']['objects'] if o['id']=='new-home')
    assert obj['geom']['type']=='Polygon' and obj['residents']==250 and obj['source']=='proposal'
    assert actual['metrics']==preview.json()['after']
    assert actual['state']['areas']==preview.json()['state']['areas']
    with connect(dsn) as db:
        assert db.execute("SELECT geom FROM objects WHERE id='new-home'").fetchone()['geom']==obj['geom']
        assert db.execute("SELECT name FROM planning_areas WHERE id='new-area'").fetchone()['name']=='Новый район'
    mod.close()


def test_admin_can_approve_own_request(env):
    _,c,dsn=env;register(c,'single-admin@obninsk.test')
    with connect(dsn) as db:db.execute("UPDATE users SET role='admin' WHERE email='single-admin@obninsk.test'")
    pid=proposal(c).json()['id']
    r=c.post(f'/api/proposals/{pid}/decision',json={'decision':'approved'})
    assert r.status_code==200,r.text
    item=c.get('/api/proposals').json()['items'][0]
    assert item['status']=='approved' and item['author_id']==item['reviewer_id']


def test_scenarios_are_private_persistent_and_compare_on_same_city(env):
    app,c,dsn=env;register(c)
    actions=[dict(entity='object',operation='add',id='scenario-stop',values=dict(name='Остановка сценария',kind='stop',x=700,y=700))]
    a=c.post('/api/scenarios',json=dict(name='Остановка',actions=actions,base_version=0));assert a.status_code==201,a.text
    b=c.post('/api/scenarios',json=dict(name='Парк',actions=[dict(entity='object',operation='add',id='scenario-park',values=dict(name='Парк сценария',kind='park',x=800,y=700))],base_version=0));assert b.status_code==201
    ids=[a.json()['id'],b.json()['id']]
    before=c.get('/api/city').json()['state']
    payload=dict(ids=ids,target='transport_access',threshold=0,park_radius=200,park_radii=[100,200,500])
    r=c.post('/api/scenarios/compare',json=payload);assert r.status_code==200,r.text
    assert r.json()['recommended_id']==ids[0]
    assert all(i['meets_target'] for i in r.json()['items'])
    assert c.get('/api/city').json()['state']==before
    evaluated=c.post(f'/api/scenarios/{ids[0]}/evaluate',json=dict(park_radius=200,park_radii=[100,200]))
    assert evaluated.status_code==200 and evaluated.json()['after']['radius']==200
    assert evaluated.json()['actions']==actions
    other=TestClient(app);register(other,'scenario-other@obninsk.test')
    assert other.get('/api/scenarios').json()['items']==[]
    assert other.post('/api/scenarios/compare',json=payload).status_code==404
    assert other.post(f'/api/scenarios/{ids[0]}/evaluate',json={}).status_code==404
    with TestClient(create_app(dsn)) as reopened:
        reopened.cookies.set('obninsk_session',c.cookies.get('obninsk_session'))
        assert len(reopened.get('/api/scenarios').json()['items'])==2
    other.close()


def test_scenario_invalid_geometry_and_targets_are_rejected(env):
    _,c,_=env;register(c)
    bad=home_action();bad['values']['x']=2
    assert c.post('/api/preview',json=dict(action=bad,base_version=0)).status_code==422
    assert c.post('/api/scenarios',json=dict(name='Неверно',action=bad,base_version=0)).status_code==422
    assert c.post('/api/scenarios/compare',json=dict(ids=['x'],park_radii=[-1])).status_code==422


def test_parking_greenery_moderation_and_names_survive_deletion(env):
    app,c,path=env;register(c)
    with connect(path) as db:db.execute("UPDATE users SET role='admin'")
    actions=[{'entity':'object','operation':'add','id':'new-'+kind,'values':{'kind':kind,'name':name,'x':500,'y':400}} for kind,name in [('parking','Парковка у дома'),('greenery','Озеленение двора')]]
    r=c.post('/api/proposals',json={'actions':actions,'base_version':0});assert r.status_code==201,r.text
    assert decide(c,r.json()['id']).status_code==200
    city=c.get('/api/city').json();assert {p['kind'] for p in city['metrics']['provision']} >= {'parking','greenery'}
    actions=[{'entity':'object','operation':'delete','id':a['id'],'values':{}} for a in actions]
    r=c.post('/api/proposals',json={'actions':actions,'base_version':1});assert r.status_code==201,r.text
    assert decide(c,r.json()['id']).status_code==200
    item=c.get('/api/proposals').json()['items'][0]
    assert item['status']=='approved' and item['action_names']=={'new-parking':'Парковка у дома','new-greenery':'Озеленение двора'}


def test_admin_demo_reset_and_undo_preserve_accounts(env):
    app,c,path=env;register(c)
    assert c.post('/api/admin/demo-reset',json={'action':'reset_all'}).status_code==403
    mod=moderator(app,path)
    assert mod.post('/api/admin/demo-reset',json={'action':'clear_proposals'}).status_code==403
    with connect(path) as db:db.execute("UPDATE users SET role='admin' WHERE email='resident@example.com'")
    p=proposal(c);assert p.status_code==201;assert decide(c,p.json()['id']).status_code==200
    before=c.get('/api/city').json()['state']
    assert c.post('/api/admin/demo-reset',json={'action':'reset_all'}).status_code==200
    after=c.get('/api/city').json()['state'];assert after['version']>before['version']
    assert not c.get('/api/proposals').json()['items'] and c.get('/api/auth/me').status_code==200
    assert not next(e for e in after['edges'] if e['id']==MAP['edges'][0]['id'])['closed']
    assert c.post('/api/admin/demo-reset',json={'action':'undo'}).status_code==200
    restored=c.get('/api/city').json()['state'];assert restored['objects']==before['objects'] and restored['edges']==before['edges']
    assert c.get('/api/proposals').json()['items'][0]['status']=='approved'
    assert c.post('/api/admin/demo-reset',json={'action':'undo'}).status_code==409


def test_clear_proposals_does_not_change_map_and_can_undo(env):
    _,c,path=env;register(c)
    with connect(path) as db:db.execute("UPDATE users SET role='admin'")
    assert proposal(c).status_code==201
    before=c.get('/api/city').json()['state']
    assert c.post('/api/admin/demo-reset',json={'action':'clear_proposals'}).status_code==200
    assert c.get('/api/city').json()['state']==before
    assert not c.get('/api/proposals').json()['items']
    assert c.post('/api/admin/demo-reset',json={'action':'undo'}).status_code==200
    assert len(c.get('/api/proposals').json()['items'])==1


def test_polygon_district_houses_and_roads_moderate_as_one_project(env):
    _,c,path=env;register(c)
    with connect(path) as db:db.execute("UPDATE users SET role='admin'")
    actions=[{'entity':'area','operation':'add','id':'polygon-area','values':{'name':'Район у леса','points':[{'x':100,'y':100},{'x':700,'y':100},{'x':650,'y':700},{'x':100,'y':600}]}},
             {'entity':'road','operation':'add','id':'project-road','values':{'name':'Новая дорожка','points':[{'x':200,'y':200},{'x':350,'y':400},{'x':600,'y':600}]}},
             {'entity':'object','operation':'add','id':'project-house','values':{'name':'Дом у дорожки','kind':'home','x':350,'y':410,'width':20,'height':30,'residents':150}}]
    before=c.get('/api/city').json()['state']
    payload={'actions':actions,'base_version':0}
    preview=c.post('/api/preview',json=payload);assert preview.status_code==200,preview.text
    assert c.get('/api/city').json()['state']==before
    r=c.post('/api/proposals',json=payload);assert r.status_code==201,r.text
    assert decide(c,r.json()['id']).status_code==200
    result=c.get('/api/city').json();assert result['metrics']==preview.json()['after']
    assert next(a for a in result['state']['areas'] if a['id']=='polygon-area')['geom']['type']=='Polygon'
    assert len([e for e in result['state']['edges'] if e['id'].startswith('project-road_e')])==4
    house=next(o for o in result['state']['objects'] if o['id']=='project-house')
    assert house['node_id'].startswith('project-road_n')


def test_invalid_polygon_and_road_do_not_mutate_city(env):
    _,c,_=env;register(c);before=c.get('/api/city').json()['state']
    for entity,points in [('area',[{'x':0,'y':0},{'x':200,'y':200},{'x':0,'y':200},{'x':200,'y':0}]),('road',[{'x':200,'y':200},{'x':200,'y':200}])]:
        r=c.post('/api/proposals',json={'action':{'entity':entity,'operation':'add','id':'invalid-shape','values':{'name':'Проверка','points':points}},'base_version':0})
        assert r.status_code==422,r.text
    assert c.get('/api/city').json()['state']==before


def test_fitted_home_outline_persists_through_approval(env):
    _,c,path=env;register(c)
    with connect(path) as db:db.execute("UPDATE users SET role='admin'")
    specs=[dict(id='fit-home-one',name='Первый дом',x=600,y=600,width=200,height=100,residents=100),dict(id='fit-home-two',name='Второй дом',x=900,y=600,width=100,height=100,residents=100)]
    r=c.post('/api/layout/fit',json={'houses':specs});assert r.status_code==200,r.text
    fitted=r.json()['houses'];assert len(fitted)==2
    actions=[{'entity':'object','operation':'add','id':h['id'],'values':{k:h[k] for k in ['name','kind','x','y','width','height','residents','points','rotation']}} for h in fitted]
    p=c.post('/api/proposals',json={'actions':actions,'base_version':0});assert p.status_code==201,p.text
    assert decide(c,p.json()['id']).status_code==200
    state=c.get('/api/city').json()['state']
    for h in fitted:assert next(o for o in state['objects'] if o['id']==h['id'])['geom']==h['geom']
    r=c.post('/api/layout/fit',json={'houses':[{**specs[0],'width':201}]});assert r.status_code==422


def test_district_stop_and_paths_are_included_in_total_preview_and_approval(env):
    _,c,path=env;register(c)
    with connect(path) as db:db.execute("UPDATE users SET role='admin'")
    base=[{'entity':'area','operation':'add','id':'stop-area','values':{'name':'Новый район','points':[{'x':100,'y':100},{'x':1000,'y':100},{'x':1000,'y':850},{'x':100,'y':850}]}},
          {'entity':'road','operation':'add','id':'stop-road','values':{'name':'Дорожка','points':[{'x':100,'y':700},{'x':1000,'y':700}]}},
          {'entity':'object','operation':'add','id':'stop-home','values':{'name':'Дом','kind':'home','x':800,'y':710,'width':20,'height':20,'residents':300}}]
    stop={'entity':'object','operation':'add','id':'district-stop','values':{'name':'Остановка района','kind':'stop','x':820,'y':710}}
    without=c.post('/api/preview',json={'actions':base,'base_version':0});assert without.status_code==200,without.text
    actions=[*base,stop]
    preview=c.post('/api/preview',json={'actions':actions,'base_version':0});assert preview.status_code==200,preview.text
    house=next(h for h in preview.json()['after']['rows'] if h['id']=='stop-home')
    assert house['stop_distance']==40
    assert house['stop_distance']<next(h for h in without.json()['after']['rows'] if h['id']=='stop-home')['stop_distance']
    p=c.post('/api/proposals',json={'actions':actions,'base_version':0});assert p.status_code==201,p.text
    assert decide(c,p.json()['id']).status_code==200
    assert c.get('/api/city').json()['metrics']==preview.json()['after']


def test_population_recalibration_preserves_proposals_and_project_residents(env,monkeypatch):
    import backend.data as data
    _,c,path=env;register(c);assert proposal(c).status_code==201
    with connect(path) as db:
        db.execute("UPDATE objects SET source='osm' WHERE id='h1'")
        db.execute("UPDATE objects SET source='proposal',residents=45 WHERE id='h2'")
    monkeypatch.setattr(data,'DATABASE',path)
    monkeypatch.setattr(data,'seed_state',lambda:{'objects':[{'id':'h1','kind':'home','residents':133000}]})
    data.initialize(path)
    with connect(path) as db:
        assert db.execute("SELECT residents FROM objects WHERE id='h1'").fetchone()['residents']==133000
        assert db.execute("SELECT residents FROM objects WHERE id='h2'").fetchone()['residents']==45
        assert db.execute('SELECT count(*) FROM proposals').fetchone()['count']==1
        assert db.execute('SELECT count(*) FROM users').fetchone()['count']==1
    monkeypatch.setattr(data,'seed_state',lambda:{'objects':[{'id':'h1','kind':'home','residents':1}]})
    data.initialize(path)
    with connect(path) as db:assert db.execute("SELECT residents FROM objects WHERE id='h1'").fetchone()['residents']==133000


def test_work_limits_persist_sum_by_type_and_apply_on_approval(env):
    app,c,dsn=env;register(c);mod=moderator(app,dsn)
    actions=[dict(entity='object',operation='add',id='budget-park-'+str(i),values=dict(name='Сквер',kind='park',x=800+i*20,y=700)) for i in range(2)]
    payload=dict(actions=actions,base_version=900)
    assert c.post('/api/work-limits',json={'limits':{'add_park':3_000_000}}).status_code==403
    assert mod.post('/api/work-limits',json={'limits':{'add_park':3_000_000,'move_stop':100_000}}).status_code==200
    assert c.get('/api/city').json()['state']['work_limits']['add_park']==3_000_000
    estimate=c.post('/api/preview',json=payload).json()['estimate']
    assert estimate['total']==4_000_000 and not estimate['can_submit']
    assert c.post('/api/proposals',json=payload).status_code==422
    assert mod.post('/api/work-limits',json={'limits':{'add_park':4_000_000}}).status_code==200
    r=c.post('/api/proposals',json=payload);assert r.status_code==201,r.text
    pid=r.json()['id']
    mod.post('/api/work-limits',json={'limits':{'add_park':0}})
    assert decide(mod,pid).status_code==409
    mod.post('/api/work-limits',json={'limits':{'add_park':None}})
    assert decide(mod,pid).status_code==200
    stop=dict(action=dict(entity='object',operation='update',id='s1',values=dict(x=700,y=600)),base_version=0)
    assert not c.post('/api/preview',json=stop).json()['estimate']['can_submit']
    for limits in ({'oops':5},{'add_park':-1},{'add_park':True},{'add_park':1.5}):
        assert mod.post('/api/work-limits',json={'limits':limits}).status_code==422
    mod.close()


def test_facility_import_is_additive_and_runs_only_once(env,monkeypatch):
    from backend.data import install_amenities
    from backend.seed import DISTRICT
    app,c,dsn=env;register(c);pid=proposal(c).json()['id']
    before=c.get('/api/city').json()['state']
    obj=dict(before['objects'][0],id='osm_parking_wtest',name='Парковка',kind='parking',residents=0,geom=None,source='osm')
    monkeypatch.setattr('backend.data.amenities_objects',lambda nodes:[obj])
    with connect(dsn) as db:assert install_amenities(db)==1
    after=c.get('/api/city').json()['state']
    assert len(after['objects'])==len(before['objects'])+1
    assert after['demolition_policy']==before['demolition_policy']
    assert c.get('/api/proposals').json()['items'][0]['id']==pid
    with connect(dsn) as db:
        db.execute('DELETE FROM objects WHERE id=%s',(obj['id'],))
        assert install_amenities(db)==0
    assert len(c.get('/api/city').json()['state']['objects'])==len(before['objects'])
