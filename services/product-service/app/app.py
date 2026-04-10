from flask import Flask, jsonify, request
import sqlite3, os
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', '/tmp/products.db')

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path=''):
    return '', 200

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SEED_PRODUCTS = [
    {"name":"iPhone 15 Pro","category":"Electronics","brand":"Apple","price":119999,"original_price":134900,"stock":50,"rating":4.8,"review_count":2847,"image":"https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=400&h=400&fit=crop","description":"A17 Pro chip, 48MP camera, titanium design, USB-C","sku":"APL-IP15P-128"},
    {"name":"Samsung Galaxy S24 Ultra","category":"Electronics","brand":"Samsung","price":109999,"original_price":124999,"stock":35,"rating":4.7,"review_count":1923,"image":"https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop","description":"Snapdragon 8 Gen 3, 200MP camera, built-in S Pen","sku":"SAM-S24U-256"},
    {"name":"MacBook Air M3","category":"Electronics","brand":"Apple","price":114900,"original_price":124900,"stock":25,"rating":4.9,"review_count":3421,"image":"https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop","description":"Apple M3 chip, 18-hour battery, 13.6\" Liquid Retina display","sku":"APL-MBA-M3-8"},
    {"name":"Dell XPS 15 Laptop","category":"Electronics","brand":"Dell","price":149999,"original_price":179999,"stock":18,"rating":4.6,"review_count":892,"image":"https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop","description":"Intel Core i9, 32GB RAM, 1TB SSD, 15.6\" OLED 4K display","sku":"DEL-XPS15-I9"},
    {"name":"Sony WH-1000XM5 Headphones","category":"Electronics","brand":"Sony","price":24990,"original_price":34990,"stock":80,"rating":4.8,"review_count":5621,"image":"https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400&h=400&fit=crop","description":"Industry-leading noise cancellation, 30hr battery, multipoint connection","sku":"SNY-WH1000XM5"},
    {"name":"Samsung 65\" 4K QLED TV","category":"Electronics","brand":"Samsung","price":74999,"original_price":99999,"stock":20,"rating":4.6,"review_count":1456,"image":"https://images.unsplash.com/photo-1593784991095-a205069470b6?w=400&h=400&fit=crop","description":"Quantum HDR, 120Hz, Tizen OS, Dolby Atmos sound","sku":"SAM-TV65-QLED"},
    {"name":"iPad Pro 12.9\" M2","category":"Electronics","brand":"Apple","price":109900,"original_price":119900,"stock":30,"rating":4.8,"review_count":2103,"image":"https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop","description":"M2 chip, Liquid Retina XDR, Wi-Fi 6E, Apple Pencil support","sku":"APL-IPADP-M2"},
    {"name":"Canon EOS R50 Camera","category":"Electronics","brand":"Canon","price":64990,"original_price":79990,"stock":15,"rating":4.5,"review_count":432,"image":"https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop","description":"24.2MP APS-C sensor, 4K video, dual pixel autofocus, Wi-Fi","sku":"CAN-EOSR50-KIT"},
    {"name":"Nike Air Max 270","category":"Fashion","brand":"Nike","price":7999,"original_price":12995,"stock":150,"rating":4.5,"review_count":3892,"image":"https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop","description":"Max Air unit in heel, lightweight mesh upper, comfortable all-day wear","sku":"NKE-AM270-BLK"},
    {"name":"Levi's 511 Slim Jeans","category":"Fashion","brand":"Levi's","price":2499,"original_price":5999,"stock":200,"rating":4.4,"review_count":7823,"image":"https://images.unsplash.com/photo-1542272604-787c3835535d?w=400&h=400&fit=crop","description":"Slim fit, sits below waist, straight through thigh, tapered leg","sku":"LVI-511-SLM-32"},
    {"name":"Adidas Ultraboost 23","category":"Fashion","brand":"Adidas","price":12999,"original_price":17999,"stock":90,"rating":4.7,"review_count":2341,"image":"https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&h=400&fit=crop","description":"Boost midsole, Primeknit upper, Continental rubber outsole","sku":"ADI-UB23-WHT"},
    {"name":"Ray-Ban Aviator Classic","category":"Fashion","brand":"Ray-Ban","price":6490,"original_price":9990,"stock":60,"rating":4.6,"review_count":4512,"image":"https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=400&h=400&fit=crop","description":"Iconic aviator frame, G-15 green lenses, UV protection","sku":"RB-3025-G15"},
    {"name":"Dyson V15 Detect Vacuum","category":"Home & Kitchen","brand":"Dyson","price":54900,"original_price":64900,"stock":22,"rating":4.7,"review_count":1234,"image":"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400&h=400&fit=crop","description":"Laser dust detection, LCD screen, 60min runtime","sku":"DYS-V15-DET"},
    {"name":"Instant Pot Duo 7-in-1","category":"Home & Kitchen","brand":"Instant Pot","price":7999,"original_price":12999,"stock":75,"rating":4.6,"review_count":9821,"image":"https://images.unsplash.com/photo-1585515320310-259814833e62?w=400&h=400&fit=crop","description":"Pressure cooker, slow cooker, rice cooker, steamer, saute, yogurt maker","sku":"IP-DUO7-6L"},
    {"name":"Philips Air Fryer XXL","category":"Home & Kitchen","brand":"Philips","price":9999,"original_price":15999,"stock":55,"rating":4.5,"review_count":6723,"image":"https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?w=400&h=400&fit=crop","description":"7.2L capacity, 80% less fat, digital touchscreen, 7 preset programs","sku":"PHL-AF-XXL"},
    {"name":"Atomic Habits - James Clear","category":"Books","brand":"Penguin","price":349,"original_price":699,"stock":500,"rating":4.9,"review_count":45823,"image":"https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=400&h=400&fit=crop","description":"Proven framework for building good habits and breaking bad ones","sku":"BK-ATOMHAB"},
    {"name":"Rich Dad Poor Dad","category":"Books","brand":"Plata Publishing","price":249,"original_price":499,"stock":400,"rating":4.7,"review_count":32145,"image":"https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400&h=400&fit=crop","description":"What the rich teach their kids about money","sku":"BK-RDPD"},
    {"name":"Yonex Arcsaber 11 Badminton Racket","category":"Sports","brand":"Yonex","price":5499,"original_price":8999,"stock":40,"rating":4.7,"review_count":892,"image":"https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=400&h=400&fit=crop","description":"Carbon graphite shaft, 85g, repulsion power technology","sku":"YNX-ARC11-G4"},
    {"name":"The Ordinary Hyaluronic Acid","category":"Beauty","brand":"The Ordinary","price":699,"original_price":1299,"stock":120,"rating":4.5,"review_count":12891,"image":"https://images.unsplash.com/photo-1556228578-8c89e6adf883?w=400&h=400&fit=crop","description":"2% Hyaluronic acid, multi-depth hydration, plumped skin","sku":"TOD-HA-30ML"},
    {"name":"boAt Airdopes 141 TWS","category":"Electronics","brand":"boAt","price":1299,"original_price":4990,"stock":300,"rating":4.1,"review_count":89234,"image":"https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop","description":"42H playback, Beast Mode gaming, IPX4 water resistance","sku":"BOAT-AD141"},
]

SEED_REVIEWS = [
    (1,"Rahul S.",5,"Best phone I've used. Camera quality is phenomenal!","2024-01-15"),
    (1,"Priya M.",5,"Worth every rupee. Build quality is amazing.","2024-01-20"),
    (1,"Amit K.",4,"Great phone but very expensive. Battery could be better.","2024-02-01"),
    (3,"Sneha R.",5,"Lightning fast, amazing battery. Best laptop for creators.","2024-01-10"),
    (3,"Vikram P.",5,"Switched from Windows and never looked back!","2024-02-15"),
    (5,"Anjali D.",5,"Noise cancellation is absolutely insane. Love it!","2024-01-25"),
    (9,"Deepak S.",5,"Very comfortable for long runs. True to size.","2024-02-10"),
    (13,"Kavya N.",4,"Powerful suction. Worth the price.","2024-01-30"),
]

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT DEFAULT '',
            brand TEXT DEFAULT '', price REAL DEFAULT 0,
            original_price REAL DEFAULT 0, stock INTEGER DEFAULT 100,
            rating REAL DEFAULT 4.0, review_count INTEGER DEFAULT 0,
            description TEXT DEFAULT '', image TEXT DEFAULT '📦', sku TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER, user_name TEXT, rating INTEGER DEFAULT 5,
            comment TEXT, date TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
    ''')
    if conn.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        for p in SEED_PRODUCTS:
            conn.execute(
                'INSERT INTO products (name,category,brand,price,original_price,stock,rating,review_count,description,image,sku) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (p['name'],p['category'],p['brand'],p['price'],p['original_price'],p['stock'],p['rating'],p['review_count'],p['description'],p['image'],p['sku'])
            )
        for (pid,uname,rat,comment,date) in SEED_REVIEWS:
            conn.execute('INSERT INTO reviews (product_id,user_name,rating,comment,date) VALUES (?,?,?,?,?)', (pid,uname,rat,comment,date))
        conn.commit()
    conn.close()

def row_to_dict(row):
    return dict(row)

@app.route('/health')
def health():
    return jsonify({"status":"ok","service":"product-service","db":"sqlite"}), 200

@app.route('/products', methods=['GET'])
def get_products():
    category = request.args.get('category','')
    q = request.args.get('q','')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    brand = request.args.get('brand','')
    sort = request.args.get('sort','')
    sql = 'SELECT * FROM products WHERE 1=1'
    params = []
    if category:
        sql += ' AND LOWER(category)=LOWER(?)'; params.append(category)
    if q:
        sql += ' AND (LOWER(name) LIKE LOWER(?) OR LOWER(brand) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))'; params += [f'%{q}%',f'%{q}%',f'%{q}%']
    if min_price is not None:
        sql += ' AND price >= ?'; params.append(min_price)
    if max_price is not None:
        sql += ' AND price <= ?'; params.append(max_price)
    if brand:
        sql += ' AND LOWER(brand)=LOWER(?)'; params.append(brand)
    sort_map = {'price_asc':'price ASC','price_desc':'price DESC','rating':'rating DESC','newest':'id DESC','popular':'review_count DESC'}
    sql += f' ORDER BY {sort_map.get(sort,"id ASC")}'
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    products = [row_to_dict(r) for r in rows]
    for p in products:
        p['discount'] = int((1 - p['price']/p['original_price'])*100) if p['original_price'] > 0 else 0
    return jsonify({"products": products, "total": len(products)}), 200

@app.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    conn = get_db()
    row = conn.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error":"Product not found"}), 404
    p = row_to_dict(row)
    reviews = [row_to_dict(r) for r in conn.execute('SELECT * FROM reviews WHERE product_id=? ORDER BY date DESC',(pid,)).fetchall()]
    conn.close()
    p['discount'] = int((1-p['price']/p['original_price'])*100) if p['original_price'] > 0 else 0
    p['reviews'] = reviews
    return jsonify(p), 200

@app.route('/products/<int:pid>/reviews', methods=['POST'])
def add_review(pid):
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone():
        conn.close(); return jsonify({"error":"Product not found"}), 404
    conn.execute('INSERT INTO reviews (product_id,user_name,rating,comment,date) VALUES (?,?,?,?,?)',
                 (pid, data.get('user_name','Anonymous'), data.get('rating',5), data.get('comment',''), datetime.now().strftime('%Y-%m-%d')))
    stats = conn.execute('SELECT COUNT(*) as cnt, AVG(rating) as avg FROM reviews WHERE product_id=?',(pid,)).fetchone()
    conn.execute('UPDATE products SET review_count=?,rating=? WHERE id=?',(stats['cnt'],round(stats['avg'],1),pid))
    conn.commit(); conn.close()
    return jsonify({"message":"Review added"}), 201

@app.route('/products', methods=['POST'])
def create_product():
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({"error":"name is required"}), 400
    conn = get_db()
    cur = conn.execute('INSERT INTO products (name,category,brand,price,original_price,stock,description,image,sku) VALUES (?,?,?,?,?,?,?,?,?)',
                       (data['name'],data.get('category',''),data.get('brand',''),data.get('price',0),data.get('original_price',data.get('price',0)),data.get('stock',100),data.get('description',''),data.get('image','📦'),data.get('sku','')))
    conn.commit()
    row = conn.execute('SELECT * FROM products WHERE id=?',(cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/products/<int:pid>', methods=['PUT'])
def update_product(pid):
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone():
        conn.close(); return jsonify({"error":"Product not found"}), 404
    fields = ['name','category','brand','price','original_price','stock','description','image']
    updates = {k:data[k] for k in fields if k in data}
    if updates:
        conn.execute(f'UPDATE products SET {", ".join(f"{k}=?" for k in updates)} WHERE id=?', list(updates.values())+[pid])
        conn.commit()
    row = conn.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 200

@app.route('/products/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    conn = get_db()
    if not conn.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone():
        conn.close(); return jsonify({"error":"Product not found"}), 404
    conn.execute('DELETE FROM products WHERE id=?',(pid,))
    conn.execute('DELETE FROM reviews WHERE product_id=?',(pid,))
    conn.commit(); conn.close()
    return jsonify({"deleted":pid}), 200

@app.route('/products/categories', methods=['GET'])
def get_categories():
    conn = get_db()
    rows = conn.execute('SELECT DISTINCT category FROM products WHERE category!="" ORDER BY category').fetchall()
    conn.close()
    return jsonify({"categories":[r['category'] for r in rows]}), 200

@app.route('/products/brands', methods=['GET'])
def get_brands():
    conn = get_db()
    rows = conn.execute('SELECT DISTINCT brand FROM products WHERE brand!="" ORDER BY brand').fetchall()
    conn.close()
    return jsonify({"brands":[r['brand'] for r in rows]}), 200

@app.route('/products/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    low_stock = conn.execute('SELECT COUNT(*) FROM products WHERE stock < 20').fetchone()[0]
    by_cat = conn.execute('SELECT category,COUNT(*) as cnt FROM products GROUP BY category').fetchall()
    conn.close()
    return jsonify({"total_products":total,"low_stock_count":low_stock,"by_category":[{"category":r[0],"count":r[1]} for r in by_cat]}), 200

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
