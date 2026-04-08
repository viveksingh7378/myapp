import pytest
from app.app import app, get_initial_items


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.items = get_initial_items() # Reset items for each test to ensure isolation
    with app.test_client() as client:
        yield client


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_get_all_items(client):
    response = client.get("/items")
    assert response.status_code == 200
    data = response.get_json()
    assert "items" in data
    assert len(data["items"]) == 2


def test_get_single_item(client):
    response = client.get("/items/1")
    assert response.status_code == 200
    assert response.get_json()["name"] == "item-one"


def test_item_not_found(client):
    response = client.get("/items/999")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_create_item(client):
    response = client.post("/items", json={"name": "item-three"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["name"] == "item-three"
    assert "id" in data


def test_create_item_missing_name(client):
    response = client.post("/items", json={})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_delete_item(client):
    response = client.delete("/items/1")
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


def test_delete_item_not_found(client):
    response = client.delete("/items/999")
    assert response.status_code == 404
    assert "error" in response.get_json()