import pytest
from app.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
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