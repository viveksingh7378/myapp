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
    assert r.get_json()["service"] == "order-service"


def test_get_all_orders(client):
    r = client.get("/orders")
    assert r.status_code == 200
    assert "orders" in r.get_json()


def test_get_order_by_id(client):
    r = client.get("/orders/1")
    assert r.status_code == 200
    assert r.get_json()["id"] == 1


def test_order_not_found(client):
    r = client.get("/orders/9999")
    assert r.status_code == 404


def test_create_order(client):
    r = client.post("/orders", json={
        "user_id": 3,
        "items": [{"product_id": 5, "name": "Instant Pot", "qty": 1, "price": 6999}],
        "address": "789 Park Street, Delhi"
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data["status"] == "pending"
    assert data["total"] == 6999


def test_create_order_missing_fields(client):
    r = client.post("/orders", json={"user_id": 1})
    assert r.status_code == 400


def test_create_order_empty_items(client):
    r = client.post("/orders", json={"user_id": 1, "items": []})
    assert r.status_code == 400


def test_update_order_status(client):
    r = client.put("/orders/2/status", json={"status": "delivered"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "delivered"


def test_update_invalid_status(client):
    r = client.put("/orders/1/status", json={"status": "flying"})
    assert r.status_code == 400


def test_cancel_order(client):
    # Create a new order first so we can cancel it
    create = client.post("/orders", json={
        "user_id": 1,
        "items": [{"product_id": 1, "name": "iPhone", "qty": 1, "price": 99999}],
        "address": "Test Address"
    })
    order_id = create.get_json()["id"]
    r = client.delete(f"/orders/{order_id}")
    assert r.status_code == 200


def test_filter_orders_by_user(client):
    r = client.get("/orders?user_id=1")
    assert r.status_code == 200
    orders = r.get_json()["orders"]
    assert all(o["user_id"] == 1 for o in orders)
