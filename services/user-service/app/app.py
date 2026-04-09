from flask import Flask, jsonify, request
from datetime import datetime
import hashlib

app = Flask(__name__)

users = [
    {"id": 1, "name": "Vivek Singh", "email": "vivek@example.com",
     "phone": "9876543210", "password": hashlib.sha256("pass123".encode()).hexdigest(),
     "address": "123 MG Road, Mumbai", "role": "customer",
     "joined_at": "2023-06-01T00:00:00", "orders_count": 5},
    {"id": 2, "name": "Priya Sharma", "email": "priya@example.com",
     "phone": "9123456789", "password": hashlib.sha256("pass456".encode()).hexdigest(),
     "address": "456 Brigade Road, Bangalore", "role": "customer",
     "joined_at": "2023-08-15T00:00:00", "orders_count": 3},
]

next_id = len(users) + 1


def _safe_user(u):
    """Return user without password field."""
    return {k: v for k, v in u.items() if k != "password"}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "user-service"}), 200


@app.route("/users", methods=["GET"])
def get_users():
    return jsonify({"users": [_safe_user(u) for u in users], "total": len(users)}), 200


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(_safe_user(user)), 200


@app.route("/users/register", methods=["POST"])
def register():
    global next_id
    data = request.get_json()
    required = ["name", "email", "password"]
    for field in required:
        if not data or field not in data:
            return jsonify({"error": f"{field} is required"}), 400
    if any(u["email"] == data["email"] for u in users):
        return jsonify({"error": "Email already registered"}), 409
    user = {
        "id": next_id,
        "name": data["name"],
        "email": data["email"],
        "phone": data.get("phone", ""),
        "password": hashlib.sha256(data["password"].encode()).hexdigest(),
        "address": data.get("address", ""),
        "role": "customer",
        "joined_at": datetime.utcnow().isoformat(),
        "orders_count": 0,
    }
    users.append(user)
    next_id += 1
    return jsonify(_safe_user(user)), 201


@app.route("/users/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or "email" not in data or "password" not in data:
        return jsonify({"error": "email and password are required"}), 400
    hashed = hashlib.sha256(data["password"].encode()).hexdigest()
    user = next((u for u in users
                 if u["email"] == data["email"] and u["password"] == hashed), None)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    return jsonify({"message": "Login successful", "user": _safe_user(user)}), 200


@app.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json() or {}
    for key in ["name", "phone", "address"]:
        if key in data:
            user[key] = data[key]
    return jsonify(_safe_user(user)), 200


@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    global users
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return jsonify({"error": "User not found"}), 404
    users = [u for u in users if u["id"] != user_id]
    return jsonify({"message": "User deleted", "user_id": user_id}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
