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
    assert r.get_json()["service"] == "user-service"


def test_get_all_users(client):
    r = client.get("/users")
    assert r.status_code == 200
    data = r.get_json()
    assert "users" in data
    assert data["total"] >= 2


def test_get_user_by_id(client):
    r = client.get("/users/1")
    assert r.status_code == 200
    assert r.get_json()["name"] == "Vivek Singh"


def test_password_not_exposed(client):
    r = client.get("/users/1")
    assert "password" not in r.get_json()


def test_user_not_found(client):
    r = client.get("/users/9999")
    assert r.status_code == 404


def test_register_user(client):
    r = client.post("/users/register", json={
        "name": "Rahul Gupta",
        "email": "rahul@example.com",
        "password": "securepass",
        "phone": "9000000001"
    })
    assert r.status_code == 201
    assert r.get_json()["email"] == "rahul@example.com"


def test_register_duplicate_email(client):
    client.post("/users/register", json={
        "name": "Dup User", "email": "dup@example.com", "password": "abc"
    })
    r = client.post("/users/register", json={
        "name": "Dup User2", "email": "dup@example.com", "password": "xyz"
    })
    assert r.status_code == 409


def test_register_missing_field(client):
    r = client.post("/users/register", json={"name": "No Email"})
    assert r.status_code == 400


def test_login_success(client):
    r = client.post("/users/login", json={
        "email": "vivek@example.com", "password": "pass123"
    })
    assert r.status_code == 200
    assert "user" in r.get_json()


def test_login_wrong_password(client):
    r = client.post("/users/login", json={
        "email": "vivek@example.com", "password": "wrongpass"
    })
    assert r.status_code == 401


def test_update_user(client):
    r = client.put("/users/1", json={"phone": "9999999999"})
    assert r.status_code == 200
    assert r.get_json()["phone"] == "9999999999"


def test_delete_user(client):
    r = client.delete("/users/2")
    assert r.status_code == 200
