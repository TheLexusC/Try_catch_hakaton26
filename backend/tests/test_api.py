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
