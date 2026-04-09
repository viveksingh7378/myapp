from flask import Flask, jsonify, request
import sqlite3, os, uuid, random, string
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', '/tmp/payments.db')

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
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 0,
            amount REAL DEFAULT 0,
            method TEXT DEFAULT '',
            card_last4 TEXT DEFAULT '',
            upi_id TEXT DEFAULT '',
            bank_name TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            transaction_id TEXT DEFAULT '',
            failure_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
    ''')
    conn.commit(); conn.close()

PAYMENT_METHODS = ['credit_card','debit_card','upi','net_banking','wallet','cod']

def gen_txn_id():
    return 'TXN' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def row_to_dict(row):
    return dict(row)

@app.route('/health')
def health():
    return jsonify({"status":"ok","service":"payment-service","db":"sqlite"}), 200

@app.route('/payments', methods=['GET'])
def get_payments():
    user_id = request.args.get('user_id', type=int)
    order_id = request.args.get('order_id', type=int)
    status = request.args.get('status','')
    sql = 'SELECT * FROM payments WHERE 1=1'
    params = []
    if user_id:
        sql += ' AND user_id=?'; params.append(user_id)
    if order_id:
        sql += ' AND order_id=?'; params.append(order_id)
    if status:
        sql += ' AND status=?'; params.append(status)
    sql += ' ORDER BY id DESC'
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify({"payments":[row_to_dict(r) for r in rows],"total":len(rows)}), 200

@app.route('/payments/<int:pid>', methods=['GET'])
def get_payment(pid):
    conn = get_db()
    row = conn.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
    conn.close()
    if not row: return jsonify({"error":"Payment not found"}), 404
    return jsonify(row_to_dict(row)), 200

@app.route('/payments', methods=['POST'])
def process_payment():
    data = request.get_json() or {}
    if not data.get('order_id') or not data.get('amount') or not data.get('method'):
        return jsonify({"error":"order_id, amount, and method are required"}), 400
    if data['method'] not in PAYMENT_METHODS:
        return jsonify({"error":f"Invalid method. Valid: {PAYMENT_METHODS}"}), 400

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Simulate payment processing
    # COD always pending; others succeed (with rare random failure for realism)
    if data['method'] == 'cod':
        status = 'pending'
        txn_id = 'COD-' + gen_txn_id()
    else:
        # Simulate 95% success rate
        import random as r
        status = 'success' if r.random() > 0.05 else 'failed'
        txn_id = gen_txn_id() if status == 'success' else ''

    conn = get_db()
    cur = conn.execute('''INSERT INTO payments (order_id,user_id,amount,method,card_last4,upi_id,bank_name,status,transaction_id,created_at,updated_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                       (data['order_id'], data.get('user_id',0), data['amount'], data['method'],
                        data.get('card_last4',''), data.get('upi_id',''), data.get('bank_name',''),
                        status, txn_id, now, now))
    conn.commit()
    payment = row_to_dict(conn.execute('SELECT * FROM payments WHERE id=?',(cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify({**payment, "message": "Payment processed successfully" if status == 'success' else ("COD order placed" if status == 'pending' else "Payment failed")}), 201

@app.route('/payments/<int:pid>/refund', methods=['PUT'])
def refund(pid):
    conn = get_db()
    row = conn.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
    if not row:
        conn.close(); return jsonify({"error":"Payment not found"}), 404
    if row['status'] not in ('success','pending'):
        conn.close(); return jsonify({"error":"Only successful payments can be refunded"}), 400
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    refund_txn = 'REF-' + gen_txn_id()
    conn.execute('UPDATE payments SET status=?,transaction_id=?,updated_at=? WHERE id=?',
                 ('refunded', refund_txn, now, pid))
    conn.commit()
    row = conn.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
    conn.close()
    return jsonify({**row_to_dict(row),"message":"Refund initiated successfully"}), 200

@app.route('/payments/summary', methods=['GET'])
def summary():
    conn = get_db()
    total_revenue = conn.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE status="success"').fetchone()[0]
    total_txns = conn.execute('SELECT COUNT(*) FROM payments').fetchone()[0]
    success = conn.execute('SELECT COUNT(*) FROM payments WHERE status="success"').fetchone()[0]
    failed = conn.execute('SELECT COUNT(*) FROM payments WHERE status="failed"').fetchone()[0]
    pending = conn.execute('SELECT COUNT(*) FROM payments WHERE status="pending"').fetchone()[0]
    refunded = conn.execute('SELECT COUNT(*) FROM payments WHERE status="refunded"').fetchone()[0]
    by_method = conn.execute('SELECT method,COUNT(*),COALESCE(SUM(amount),0) FROM payments WHERE status="success" GROUP BY method').fetchall()
    conn.close()
    return jsonify({
        "total_revenue": round(total_revenue,2),
        "total_transactions": total_txns,
        "successful": success, "failed": failed,
        "pending": pending, "refunded": refunded,
        "by_method": [{"method":r[0],"count":r[1],"revenue":round(r[2],2)} for r in by_method]
    }), 200

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)
