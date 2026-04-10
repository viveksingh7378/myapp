import pytest, os, sqlite3

# Use a named shared-memory SQLite URI so all connections within the same
# process share the same in-memory database (fixes "no such table" errors).
_DB_URI = 'file:ordermem?mode=memory&cache=shared'
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
        cx.execute('DELETE FROM orders')
        # Reset AUTOINCREMENT counters so IDs start from 1 each test
        cx.execute("DELETE FROM sqlite_sequence WHERE name='orders'")
        cx.commit()

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200

def test_get_orders_empty(client):
    r = client.get('/orders')
    assert r.status_code == 200
    assert r.get_json()['total'] == 0

def test_create_order(client):
    r = client.post('/orders', json={
        "user_id":1,"user_email":"test@test.com","user_name":"Test User",
        "items":[{"product_id":1,"product_name":"iPhone","price":119999,"quantity":1}],
        "address":{"name":"Test User","city":"Mumbai","state":"Maharashtra"}
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d['status'] == 'pending'
    assert d['total'] > 0

def test_create_order_no_items(client):
    r = client.post('/orders', json={"user_id":1})
    assert r.status_code == 400

def test_get_order_by_id(client):
    r = client.post('/orders', json={"user_id":1,"items":[{"product_id":1,"price":1000,"quantity":2}]})
    oid = r.get_json()['id']
    r2 = client.get(f'/orders/{oid}')
    assert r2.status_code == 200

def test_order_not_found(client):
    r = client.get('/orders/9999')
    assert r.status_code == 404

def test_update_status(client):
    r = client.post('/orders', json={"user_id":1,"items":[{"product_id":1,"price":500,"quantity":1}]})
    oid = r.get_json()['id']
    r2 = client.put(f'/orders/{oid}/status', json={"status":"confirmed"})
    assert r2.status_code == 200
    assert r2.get_json()['status'] == 'confirmed'

def test_invalid_status(client):
    r = client.post('/orders', json={"user_id":1,"items":[{"price":100,"quantity":1}]})
    oid = r.get_json()['id']
    r2 = client.put(f'/orders/{oid}/status', json={"status":"flying"})
    assert r2.status_code == 400

def test_cancel_order(client):
    r = client.post('/orders', json={"user_id":1,"items":[{"price":100,"quantity":1}]})
    oid = r.get_json()['id']
    r2 = client.delete(f'/orders/{oid}')
    assert r2.status_code == 200

def test_order_stats(client):
    r = client.get('/orders/stats')
    assert r.status_code == 200
    assert 'total_orders' in r.get_json()

def test_filter_by_user(client):
    client.post('/orders', json={"user_id":42,"items":[{"price":100,"quantity":1}]})
    r = client.get('/orders?user_id=42')
    assert r.status_code == 200
    assert r.get_json()['total'] >= 1
