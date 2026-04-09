from flask import Flask, jsonify, request
import os

app = Flask(__name__)

# In-memory product catalog
products = [
    {"id": 1, "name": "iPhone 15 Pro", "category": "Electronics",
     "price": 99999, "stock": 50, "rating": 4.8, "brand": "Apple",
     "description": "Latest Apple flagship with A17 Pro chip", "image": "📱"},
    {"id": 2, "name": "Samsung 65\" 4K TV", "category": "Electronics",
     "price": 74999, "stock": 20, "rating": 4.6, "brand": "Samsung",
     "description": "Crystal clear 4K QLED display", "image": "📺"},
    {"id": 3, "name": "Nike Air Max 270", "category": "Fashion",
     "price": 8999, "stock": 100, "rating": 4.5, "brand": "Nike",
     "description": "Comfortable running shoes with Max Air unit", "image": "👟"},
    {"id": 4, "name": "Levi's 501 Jeans", "category": "Fashion",
     "price": 3499, "stock": 200, "rating": 4.3, "brand": "Levi's",
     "description": "Classic straight fit denim jeans", "image": "👖"},
    {"id": 5, "name": "Instant Pot Duo 7-in-1", "category": "Home",
     "price": 6999, "stock": 75, "rating": 4.7, "brand": "Instant Pot",
     "description": "Multi-use pressure cooker", "image": "🍲"},
    {"id": 6, "name": "Dyson V15 Vacuum", "category": "Home",
     "price": 39999, "stock": 30, "rating": 4.9, "brand": "Dyson",
     "description": "Powerful cordless vacuum cleaner", "image": "🧹"},
    {"id": 7, "name": "The Alchemist", "category": "Books",
     "price": 299, "stock": 500, "rating": 4.8, "brand": "Paulo Coelho",
     "description": "International bestselling novel", "image": "📚"},
    {"id": 8, "name": "Whey Protein 2kg", "category": "Sports",
     "price": 2499, "stock": 150, "rating": 4.4, "brand": "MuscleBlaze",
     "description": "25g protein per serving, chocolate flavour", "image": "💪"},
    {"id": 9, "name": "MacBook Air M2", "category": "Electronics",
     "price": 114999, "stock": 25, "rating": 4.9, "brand": "Apple",
     "description": "Ultra-thin laptop with M2 chip", "image": "💻"},
    {"id": 10, "name": "Sony WH-1000XM5", "category": "Electronics",
     "price": 24999, "stock": 60, "rating": 4.7, "brand": "Sony",
     "description": "Industry-leading noise cancelling headphones", "image": "🎧"},
]

next_id = len(products) + 1


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "product-service"}), 200


@app.route("/products", methods=["GET"])
def get_products():
    category = request.args.get("category")
    search   = request.args.get("q", "").lower()
    result   = products
    if category:
        result = [p for p in result if p["category"].lower() == category.lower()]
    if search:
        result = [p for p in result
                  if search in p["name"].lower() or search in p["description"].lower()]
    return jsonify({"products": result, "total": len(result)}), 200


@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(product), 200


@app.route("/products", methods=["POST"])
def create_product():
    global next_id
    data = request.get_json()
    required = ["name", "category", "price", "stock"]
    for field in required:
        if not data or field not in data:
            return jsonify({"error": f"{field} is required"}), 400
    product = {
        "id": next_id,
        "name": data["name"],
        "category": data["category"],
        "price": data["price"],
        "stock": data["stock"],
        "rating": data.get("rating", 0.0),
        "brand": data.get("brand", "Unknown"),
        "description": data.get("description", ""),
        "image": data.get("image", "🛍️"),
    }
    products.append(product)
    next_id += 1
    return jsonify(product), 201


@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json() or {}
    for key in ["name", "category", "price", "stock", "rating", "brand", "description"]:
        if key in data:
            product[key] = data[key]
    return jsonify(product), 200


@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    global products
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    products = [p for p in products if p["id"] != product_id]
    return jsonify({"deleted": product_id, "message": "Product removed"}), 200


@app.route("/products/categories", methods=["GET"])
def get_categories():
    cats = list(set(p["category"] for p in products))
    return jsonify({"categories": sorted(cats)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
