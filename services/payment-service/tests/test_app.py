import pytest, os, sqlite3

# Use a named shared-memory SQLite URI so all connections within the same
# process share the same in-memory database (fixes "no such table" errors).
_DB_URI = 'file:paymentmem?mode=memory&cache=shared'
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
        cx.execute('DELETE FROM payments')
        # Reset AUTOINCREMENT counters so IDs start from 1 each test
        cx.execute("DELETE FROM sqlite_sequence WHERE name='payments'")
        cx.commit()

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200

def test_process_payment_cod(client):
    r = client.post('/payments', json={"order_id":1,"user_id":1,"amount":1500,"method":"cod"})
    assert r.status_code == 201
    assert r.get_json()['status'] == 'pending'

def test_process_payment_upi(client):
    r = client.post('/payments', json={"order_id":2,"user_id":1,"amount":2500,"method":"upi","upi_id":"test@paytm"})
    assert r.status_code == 201
    assert r.get_json()['status'] in ['success','failed']

def test_process_payment_card(client):
    r = client.post('/payments', json={"order_id":3,"user_id":1,"amount":5000,"method":"credit_card","card_last4":"4242"})
    assert r.status_code == 201

def test_process_payment_missing_fields(client):
    r = client.post('/payments', json={"order_id":1})
    assert r.status_code == 400

def test_process_payment_invalid_method(client):
    r = client.post('/payments', json={"order_id":1,"amount":100,"method":"bitcoin"})
    assert r.status_code == 400

def test_get_payment(client):
    r = client.post('/payments', json={"order_id":1,"amount":1000,"method":"cod"})
    pid = r.get_json()['id']
    r2 = client.get(f'/payments/{pid}')
    assert r2.status_code == 200

def test_payment_not_found(client):
    r = client.get('/payments/9999')
    assert r.status_code == 404

def test_refund(client):
    r = client.post('/payments', json={"order_id":1,"amount":1000,"method":"cod"})
    pid = r.get_json()['id']
    r2 = client.put(f'/payments/{pid}/refund')
    assert r2.status_code == 200
    assert r2.get_json()['status'] == 'refunded'

def test_get_payments_by_order(client):
    client.post('/payments', json={"order_id":99,"amount":100,"method":"cod"})
    r = client.get('/payments?order_id=99')
    assert r.status_code == 200
    assert r.get_json()['total'] >= 1

def test_payment_summary(client):
    r = client.get('/payments/summary')
    assert r.status_code == 200
    assert 'total_revenue' in r.get_json()

def test_net_banking(client):
    r = client.post('/payments', json={"order_id":5,"amount":3000,"method":"net_banking","bank_name":"SBI"})
    assert r.status_code == 201

def test_wallet(client):
    r = client.post('/payments', json={"order_id":6,"amount":500,"method":"wallet"})
    assert r.status_code == 201
