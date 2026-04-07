from flask import Flask, jsonify, request, send_from_directory
import os

app = Flask(__name__)

# serve blog.html from the project root (one level up from app/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

items = [
    {"id": 1, "name": "item-one"},
    {"id": 2, "name": "item-two"},
]


@app.route("/blog")
def blog():
    return send_from_directory(PROJECT_ROOT, "blog.html")


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "Myapp API is running",
        "endpoints": ["/health", "/items", "/items/<id>"]
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/items", methods=["GET"])
def get_items():
    return jsonify({"items": items}), 200


@app.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(item), 200


@app.route("/items", methods=["POST"])
def create_item():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 400
    new_id = max(i["id"] for i in items) + 1 if items else 1
    new_item = {"id": new_id, "name": data["name"]}
    items.append(new_item)
    return jsonify(new_item), 201


@app.route("/items/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    global items
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return jsonify({"error": "not found"}), 404
    items = [i for i in items if i["id"] != item_id]
    return jsonify({"deleted": item_id}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)