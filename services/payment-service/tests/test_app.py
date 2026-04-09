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
    assert r.get_json()["service"] == "payment-service"


def test_get_all_payments(client):
    r = client.get("/payments")
    assert r.status_code == 200
    assert "payments" in r.get_json()


def test_get_payment_by_id(client):
    r = client.get("/payments/1")
    assert r.status_code == 200
    assert r.get_json()["id"] == 1


def test_payment_not_found(client):
    r = client.get("/payments/9999")
    assert r.status_code == 404


def test_process_payment_card(client):
    r = client.post("/payments", json={
        "order_id": 3, "user_id": 1,
        "amount": 6999, "method": "credit_card"
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data["status"] == "success"
    assert data["transaction_id"].startswith("TXN")


def test_process_payment_cod(client):
    r = client.post("/payments", json={
        "order_id": 4, "user_id": 2,
        "amount": 2499, "method": "cod"
    })
    assert r.status_code == 201
    assert r.get_json()["status"] == "pending"


def test_process_payment_invalid_method(client):
    r = client.post("/payments", json={
        "order_id": 5, "user_id": 1,
        "amount": 999, "method": "bitcoin"
    })
    assert r.status_code == 400


def test_process_payment_zero_amount(client):
    r = client.post("/payments", json={
        "order_id": 6, "user_id": 1,
        "amount": 0, "method": "upi"
    })
    assert r.status_code == 400


def test_process_payment_missing_field(client):
    r = client.post("/payments", json={"order_id": 7, "user_id": 1})
    assert r.status_code == 400


def test_refund_payment(client):
    # Create a successful payment first
    create = client.post("/payments", json={
        "order_id": 10, "user_id": 1,
        "amount": 8999, "method": "debit_card"
    })
    pid = create.get_json()["id"]
    r = client.put(f"/payments/{pid}/refund")
    assert r.status_code == 200
    assert r.get_json()["status"] == "refunded"


def test_refund_non_success_payment(client):
    # COD payment is pending — cannot refund
    create = client.post("/payments", json={
        "order_id": 11, "user_id": 2,
        "amount": 1299, "method": "cod"
    })
    pid = create.get_json()["id"]
    r = client.put(f"/payments/{pid}/refund")
    assert r.status_code == 400


def test_payment_summary(client):
    r = client.get("/payments/summary")
    assert r.status_code == 200
    data = r.get_json()
    assert "total_revenue" in data
    assert "total_transactions" in data


def test_filter_payments_by_order(client):
    r = client.get("/payments?order_id=1")
    assert r.status_code == 200
    for p in r.get_json()["payments"]:
        assert p["order_id"] == 1
