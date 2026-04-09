from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)

orders = [
    {"id": 1, "user_id": 1, "items": [{"product_id": 1, "name": "iPhone 15 Pro", "qty": 1, "price": 99999}],
     "total": 99999, "status": "delivered", "address": "123 MG Road, Mumbai",
     "created_at": "2024-01-15T10:30:00", "payment_id": 1},
    {"id": 2, "user_id": 2, "items": [{"product_id": 3, "name": "Nike Air Max 270", "qty": 2, "price": 8999}],
     "total": 17998, "status": "shipped", "address": "456 Brigade Road, Bangalore",
     "created_at": "2024-01-20T14:00:00", "payment_id": 2},
]

next_id = len(orders) + 1
VALID_STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"]


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "order-service"}), 200


@app.route("/orders", methods=["GET"])
def get_orders():
    user_id = request.args.get("user_id", type=int)
    status  = request.args.get("status")
    result  = orders
    if user_id:
        result = [o for o in result if o["user_id"] == user_id]
    if status:
        result = [o for o in result if o["status"] == status]
    return jsonify({"orders": result, "total": len(result)}), 200


@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(order), 200


@app.route("/orders", methods=["POST"])
def create_order():
    global next_id
    data = request.get_json()
    if not data or "user_id" not in data or "items" not in data:
        return jsonify({"error": "user_id and items are required"}), 400
    if not data["items"]:
        return jsonify({"error": "Order must have at least one item"}), 400
    total = sum(item.get("price", 0) * item.get("qty", 1) for item in data["items"])
    order = {
        "id": next_id,
        "user_id": data["user_id"],
        "items": data["items"],
        "total": total,
        "status": "pending",
        "address": data.get("address", ""),
        "created_at": datetime.utcnow().isoformat(),
        "payment_id": None,
    }
    orders.append(order)
    next_id += 1
    return jsonify(order), 201


@app.route("/orders/<int:order_id>/status", methods=["PUT"])
def update_status(order_id):
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    data = request.get_json() or {}
    new_status = data.get("status")
    if not new_status or new_status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400
    order["status"] = new_status
    return jsonify(order), 200


@app.route("/orders/<int:order_id>", methods=["DELETE"])
def cancel_order(order_id):
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] == "delivered":
        return jsonify({"error": "Cannot cancel a delivered order"}), 400
    order["status"] = "cancelled"
    return jsonify({"message": "Order cancelled", "order_id": order_id}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
