from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)

payments = [
    {"id": 1, "order_id": 1, "user_id": 1, "amount": 99999,
     "method": "credit_card", "status": "success",
     "transaction_id": "TXN001ABC", "created_at": "2024-01-15T10:31:00"},
    {"id": 2, "order_id": 2, "user_id": 2, "amount": 17998,
     "method": "upi", "status": "success",
     "transaction_id": "TXN002DEF", "created_at": "2024-01-20T14:01:00"},
]

next_id = len(payments) + 1
VALID_METHODS  = ["credit_card", "debit_card", "upi", "net_banking", "wallet", "cod"]
VALID_STATUSES = ["pending", "success", "failed", "refunded"]


def _generate_txn():
    import random, string
    return "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "payment-service"}), 200


@app.route("/payments", methods=["GET"])
def get_payments():
    user_id  = request.args.get("user_id", type=int)
    order_id = request.args.get("order_id", type=int)
    result   = payments
    if user_id:
        result = [p for p in result if p["user_id"] == user_id]
    if order_id:
        result = [p for p in result if p["order_id"] == order_id]
    return jsonify({"payments": result, "total": len(result)}), 200


@app.route("/payments/<int:payment_id>", methods=["GET"])
def get_payment(payment_id):
    payment = next((p for p in payments if p["id"] == payment_id), None)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404
    return jsonify(payment), 200


@app.route("/payments", methods=["POST"])
def process_payment():
    global next_id
    data = request.get_json()
    required = ["order_id", "user_id", "amount", "method"]
    for field in required:
        if not data or field not in data:
            return jsonify({"error": f"{field} is required"}), 400
    if data["method"] not in VALID_METHODS:
        return jsonify({"error": f"method must be one of {VALID_METHODS}"}), 400
    if data["amount"] <= 0:
        return jsonify({"error": "amount must be greater than 0"}), 400

    # Simulate payment — COD is always pending, others succeed
    status = "pending" if data["method"] == "cod" else "success"
    payment = {
        "id": next_id,
        "order_id": data["order_id"],
        "user_id": data["user_id"],
        "amount": data["amount"],
        "method": data["method"],
        "status": status,
        "transaction_id": _generate_txn(),
        "created_at": datetime.utcnow().isoformat(),
    }
    payments.append(payment)
    next_id += 1
    return jsonify(payment), 201


@app.route("/payments/<int:payment_id>/refund", methods=["PUT"])
def refund_payment(payment_id):
    payment = next((p for p in payments if p["id"] == payment_id), None)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404
    if payment["status"] != "success":
        return jsonify({"error": "Only successful payments can be refunded"}), 400
    payment["status"] = "refunded"
    payment["refunded_at"] = datetime.utcnow().isoformat()
    return jsonify(payment), 200


@app.route("/payments/summary", methods=["GET"])
def payment_summary():
    total_revenue = sum(p["amount"] for p in payments if p["status"] == "success")
    total_refunds = sum(p["amount"] for p in payments if p["status"] == "refunded")
    return jsonify({
        "total_transactions": len(payments),
        "successful": len([p for p in payments if p["status"] == "success"]),
        "failed": len([p for p in payments if p["status"] == "failed"]),
        "refunded": len([p for p in payments if p["status"] == "refunded"]),
        "total_revenue": total_revenue,
        "total_refunds": total_refunds,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
