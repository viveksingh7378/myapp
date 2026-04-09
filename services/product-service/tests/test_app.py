import pytest
from app.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "product-service"


def test_get_all_products(client):
    r = client.get("/products")
    assert r.status_code == 200
    data = r.get_json()
    assert "products" in data
    assert data["total"] >= 10


def test_get_product_by_id(client):
    r = client.get("/products/1")
    assert r.status_code == 200
    assert r.get_json()["name"] == "iPhone 15 Pro"


def test_product_not_found(client):
    r = client.get("/products/9999")
    assert r.status_code == 404


def test_filter_by_category(client):
    r = client.get("/products?category=Electronics")
    assert r.status_code == 200
    products = r.get_json()["products"]
    assert all(p["category"] == "Electronics" for p in products)


def test_search_products(client):
    r = client.get("/products?q=iphone")
    assert r.status_code == 200
    assert r.get_json()["total"] >= 1


def test_create_product(client):
    r = client.post("/products", json={
        "name": "Test Product", "category": "Electronics",
        "price": 999, "stock": 10
    })
    assert r.status_code == 201
    assert r.get_json()["name"] == "Test Product"


def test_create_product_missing_field(client):
    r = client.post("/products", json={"name": "No Price"})
    assert r.status_code == 400


def test_update_product(client):
    r = client.put("/products/1", json={"price": 89999})
    assert r.status_code == 200
    assert r.get_json()["price"] == 89999


def test_delete_product(client):
    r = client.delete("/products/2")
    assert r.status_code == 200
    assert r.get_json()["deleted"] == 2


def test_get_categories(client):
    r = client.get("/products/categories")
    assert r.status_code == 200
    assert "categories" in r.get_json()
