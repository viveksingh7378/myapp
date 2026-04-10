import pytest, os, sqlite3

# Use a named shared-memory SQLite URI so all connections within the same
# process share the same in-memory database (fixes "no such table" errors).
_DB_URI = 'file:usermem?mode=memory&cache=shared'
os.environ['DB_PATH'] = _DB_URI

from app.app import app, init_db

# Module-level keeper connection: keeps the shared in-memory DB alive for the
# entire test session.  Without this, the DB is destroyed between connections.
_keeper = sqlite3.connect(_DB_URI, uri=True)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.app_context():
        init_db()
    with app.test_client() as c:
        yield c
    # Wipe data between tests so tests stay independent
    with sqlite3.connect(_DB_URI, uri=True) as cx:
        cx.execute('DELETE FROM users')
        # Reset AUTOINCREMENT counters so IDs start from 1 each test
        cx.execute("DELETE FROM sqlite_sequence WHERE name='users'")
        cx.commit()

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200

def test_register(client):
    r = client.post('/users/register', json={"name":"Vivek Singh","email":"vivek@test.com","password":"pass123"})
    assert r.status_code == 201
    d = r.get_json()
    assert 'token' in d
    assert 'user_id' in d

def test_register_missing_fields(client):
    r = client.post('/users/register', json={"email":"x@x.com"})
    assert r.status_code == 400

def test_register_duplicate_email(client):
    client.post('/users/register', json={"name":"User1","email":"dup@test.com","password":"pass"})
    r = client.post('/users/register', json={"name":"User2","email":"dup@test.com","password":"pass"})
    assert r.status_code == 409

def test_login(client):
    client.post('/users/register', json={"name":"Login User","email":"login@test.com","password":"secret"})
    r = client.post('/users/login', json={"email":"login@test.com","password":"secret"})
    assert r.status_code == 200
    assert 'token' in r.get_json()

def test_login_wrong_password(client):
    client.post('/users/register', json={"name":"User","email":"wp@test.com","password":"correct"})
    r = client.post('/users/login', json={"email":"wp@test.com","password":"wrong"})
    assert r.status_code == 401

def test_get_user(client):
    r = client.post('/users/register', json={"name":"GetUser","email":"get@test.com","password":"pass"})
    uid = r.get_json()['user_id']
    r2 = client.get(f'/users/{uid}')
    assert r2.status_code == 200
    assert 'password_hash' not in r2.get_json()
    assert 'token' not in r2.get_json()

def test_user_not_found(client):
    r = client.get('/users/9999')
    assert r.status_code == 404

def test_update_user(client):
    r = client.post('/users/register', json={"name":"OldName","email":"update@test.com","password":"pass"})
    uid = r.get_json()['user_id']
    r2 = client.put(f'/users/{uid}', json={"name":"NewName","phone":"9876543210"})
    assert r2.status_code == 200
    assert r2.get_json()['name'] == 'NewName'

def test_delete_user(client):
    r = client.post('/users/register', json={"name":"ToDelete","email":"del@test.com","password":"pass"})
    uid = r.get_json()['user_id']
    r2 = client.delete(f'/users/{uid}')
    assert r2.status_code == 200

def test_get_all_users(client):
    r = client.get('/users')
    assert r.status_code == 200
    assert 'users' in r.get_json()

def test_user_stats(client):
    r = client.get('/users/stats')
    assert r.status_code == 200
    assert 'total_users' in r.get_json()
