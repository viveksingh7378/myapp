from flask import Flask, jsonify

app = Flask(__name__)

# Simple in-memory "database" for demo purposes
items = [
    {"id": 1, "name": "item-one"},
    {"id": 2, "name": "item-two"},
]


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "Myapp API is running",
        "endpoints": ["/health", "/items", "/items/<id>"]
    }), 200


@app.route("/items", methods=["GET"])
def get_items():
    return jsonify({"items": items}), 200


@app.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(item), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)