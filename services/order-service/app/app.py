from flask import Flask, jsonify, request
import sqlite3, os, json
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', '/tmp/orders.db')

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

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 0,
            user_email TEXT DEFAULT '',
            user_name TEXT DEFAULT '',
            items TEXT DEFAULT '[]',
            subtotal REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            total REAL DEFAULT 0,
            address TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            payment_id TEXT DEFAULT '',
            payment_method TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );
    ''')
    conn.commit(); conn.close()

VALID_STATUSES = ['pending','confirmed','processing','shipped','out_for_delivery','delivered','cancelled','returned']

def row_to_dict(row):
    d = dict(row)
    try: d['items'] = json.loads(d.get('items','[]'))
    except: d['items'] = []
    try: d['address'] = json.loads(d.get('address','{}'))
    except: d['address'] = {}
    return d

@app.route('/health')
def health():
    return jsonify({"status":"ok","service":"order-service","db":"sqlite"}), 200

@app.route('/orders', methods=['GET'])
def get_orders():
    user_id = request.args.get('user_id', type=int)
    status = request.args.get('status','')
    sql = 'SELECT * FROM orders WHERE 1=1'
    params = []
    if user_id:
        sql += ' AND user_id=?'; params.append(user_id)
    if status:
        sql += ' AND status=?'; params.append(status)
    sql += ' ORDER BY id DESC'
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify({"orders":[row_to_dict(r) for r in rows],"total":len(rows)}), 200

@app.route('/orders/<int:oid>', methods=['GET'])
def get_order(oid):
    conn = get_db()
    row = conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    conn.close()
    if not row: return jsonify({"error":"Order not found"}), 404
    return jsonify(row_to_dict(row)), 200

@app.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json() or {}
    if not data.get('items'):
        return jsonify({"error":"items are required"}), 400
    items = data['items']
    subtotal = sum(item.get('price',0) * item.get('quantity',1) for item in items)
    discount = data.get('discount', 0)
    tax = round((subtotal - discount) * 0.18, 2)
    total = round(subtotal - discount + tax, 2)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur = conn.execute('''INSERT INTO orders (user_id,user_email,user_name,items,subtotal,discount,tax,total,address,status,payment_method,created_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (data.get('user_id',0), data.get('user_email',''), data.get('user_name',''),
                        json.dumps(items), subtotal, discount, tax, total,
                        json.dumps(data.get('address',{})), 'pending',
                        data.get('payment_method',''), now))
    conn.commit()
    row = conn.execute('SELECT * FROM orders WHERE id=?',(cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/orders/<int:oid>/status', methods=['PUT'])
def update_status(oid):
    data = request.get_json() or {}
    status = data.get('status','')
    if status not in VALID_STATUSES:
        return jsonify({"error":f"Invalid status. Valid: {VALID_STATUSES}"}), 400
    conn = get_db()
    if not conn.execute('SELECT id FROM orders WHERE id=?',(oid,)).fetchone():
        conn.close(); return jsonify({"error":"Order not found"}), 404
    conn.execute('UPDATE orders SET status=? WHERE id=?',(status,oid))
    conn.commit()
    row = conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 200

@app.route('/orders/<int:oid>/payment', methods=['PUT'])
def update_payment(oid):
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT id FROM orders WHERE id=?',(oid,)).fetchone():
        conn.close(); return jsonify({"error":"Order not found"}), 404
    conn.execute('UPDATE orders SET payment_id=?,status=? WHERE id=?',
                 (data.get('payment_id',''), 'confirmed', oid))
    conn.commit()
    row = conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 200

@app.route('/orders/<int:oid>', methods=['DELETE'])
def cancel_order(oid):
    conn = get_db()
    row = conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not row:
        conn.close(); return jsonify({"error":"Order not found"}), 404
    if row['status'] == 'delivered':
        conn.close(); return jsonify({"error":"Cannot cancel a delivered order"}), 400
    conn.execute('UPDATE orders SET status=? WHERE id=?',('cancelled',oid))
    conn.commit(); conn.close()
    return jsonify({"cancelled":oid}), 200

@app.route('/orders/stats', methods=['GET'])
def order_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    revenue = conn.execute('SELECT COALESCE(SUM(total),0) FROM orders WHERE status NOT IN ("cancelled","returned")').fetchone()[0]
    by_status = conn.execute('SELECT status,COUNT(*) FROM orders GROUP BY status').fetchall()
    today = conn.execute('SELECT COUNT(*) FROM orders WHERE date(created_at)=date("now")').fetchone()[0]
    conn.close()
    return jsonify({"total_orders":total,"total_revenue":round(revenue,2),"today_orders":today,
                    "by_status":[{"status":r[0],"count":r[1]} for r in by_status]}), 200

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
