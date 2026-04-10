import pytest, os, sqlite3

# Use a named shared-memory SQLite URI so all connections within the same
# process share the same in-memory database (fixes "no such table" errors).
_DB_URI = 'file:productmem?mode=memory&cache=shared'
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
        cx.execute('DELETE FROM products')
        cx.execute('DELETE FROM reviews')
        cx.commit()

def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'

def test_get_products(client):
    r = client.get('/products')
    assert r.status_code == 200
    data = r.get_json()
    assert 'products' in data
    assert len(data['products']) > 0

def test_get_product_by_id(client):
    r = client.get('/products/1')
    assert r.status_code == 200
    p = r.get_json()
    assert p['id'] == 1
    assert 'reviews' in p

def test_product_not_found(client):
    r = client.get('/products/9999')
    assert r.status_code == 404

def test_get_categories(client):
    r = client.get('/products/categories')
    assert r.status_code == 200
    assert 'categories' in r.get_json()

def test_get_brands(client):
    r = client.get('/products/brands')
    assert r.status_code == 200
    assert 'brands' in r.get_json()

def test_create_product(client):
    r = client.post('/products', json={"name":"Test Product","category":"Electronics","brand":"TestBrand","price":999,"original_price":1499,"stock":10})
    assert r.status_code == 201
    assert r.get_json()['name'] == 'Test Product'

def test_create_product_missing_name(client):
    r = client.post('/products', json={"price":100})
    assert r.status_code == 400

def test_update_product(client):
    r = client.put('/products/1', json={"price":99999})
    assert r.status_code == 200
    assert r.get_json()['price'] == 99999

def test_delete_product(client):
    r = client.delete('/products/1')
    assert r.status_code == 200

def test_add_review(client):
    r = client.post('/products/2/reviews', json={"user_name":"Tester","rating":5,"comment":"Great!"})
    assert r.status_code == 201

def test_stats(client):
    r = client.get('/products/stats')
    assert r.status_code == 200
    assert 'total_products' in r.get_json()

def test_search(client):
    r = client.get('/products?q=iPhone')
    assert r.status_code == 200

def test_filter_by_category(client):
    r = client.get('/products?category=Electronics')
    assert r.status_code == 200
    data = r.get_json()
    for p in data['products']:
        assert p['category'] == 'Electronics'
