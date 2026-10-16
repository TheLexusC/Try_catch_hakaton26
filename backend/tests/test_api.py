import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app, verify_password
from backend.data import MAP, connect

PASSWORD='Local test password 2040!'

@pytest.fixture
def env(tmp_path):
    path=tmp_path/'test.sqlite3';app=create_app(str(path))
    with TestClient(app) as client:yield app,client,path

def register(client,email='resident@example.com'):
    r=client.post('/api/auth/register',json={'email':email,'password':PASSWORD,'name':'Тестовый житель'})
    assert r.status_code==201,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf_token']
    return r

def moderator(app,path,email='moderator@example.com'):
    c=TestClient(app);register(c,email)
    with connect(path) as db:db.execute("UPDATE users SET role='moderator' WHERE email=?",(email,))
    return c

def proposal(c,index=0,version=0):
    return c.post('/api/proposals',json={'action':{'type':'close_edge','target_id':MAP['edges'][index]['id']},'base_version':version,'reason':'Проверить безопасность этого пешеходного участка.'})

def decide(c,pid,decision='approved'):
    return c.post(f'/api/proposals/{pid}/decision',json={'decision':decision,'comment':'Рассмотрено в рамках учебного сценария.'})

def test_registration_hashes_cookie_and_permissions(env):
    _,c,path=env;r=register(c,'Resident@example.com')
    assert r.json()['user']['role']=='user'
    assert 'HttpOnly' in r.headers['set-cookie'] and 'samesite=strict' in r.headers['set-cookie'].lower()
    with connect(path) as db:
        stored=db.execute('SELECT password_hash FROM users').fetchone()[0]
        assert stored!=PASSWORD and verify_password(PASSWORD,stored)
        assert db.execute('SELECT token_hash FROM sessions').fetchone()[0]!=c.cookies.get('obninsk_session')
    payload={'email':'resident@example.com','password':PASSWORD,'name':'Other'}
    assert c.post('/api/auth/register',json=payload).status_code==409
    assert c.post('/api/auth/register',json={**payload,'role':'moderator'}).status_code==422

def test_logout_login_expiry_csrf(env):
    _,c,path=env;register(c);assert c.get('/api/auth/me').status_code==200
    csrf=c.headers.pop('X-CSRF-Token');assert c.post('/api/auth/logout',json={}).status_code==403
    c.headers['X-CSRF-Token']=csrf;assert c.post('/api/auth/logout',json={}).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert c.post('/api/auth/login',json={'email':'resident@example.com','password':PASSWORD}).status_code==200
    with connect(path) as db:db.execute('UPDATE sessions SET expires_at=?',(time.time()-1,))
    assert c.get('/api/auth/me').status_code==401

def test_password_spaces(env):
    _,c,path=env;pw='  my exact password  '
    assert c.post('/api/auth/register',json={'email':'space@example.com','password':pw,'name':' Spaces '}).status_code==201
    with connect(path) as db:stored=db.execute('SELECT password_hash FROM users').fetchone()[0]
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
    city=c.get('/api/city').json();assert city['state']['version']==1 and MAP['edges'][0]['id'] in city['state']['closed_edges']
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
    for a in [{'type':'close_edge','target_id':'unknown'},{'type':'move_stop','target_id':MAP['nodes'][0]['id']},{'type':'grant_admin','target_id':'me'},{'type':'open_edge','target_id':MAP['edges'][0]['id']}]:
        assert c.post('/api/preview',json={'action':a,'base_version':0}).status_code==422

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
