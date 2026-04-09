from flask import Flask, jsonify, request
import sqlite3, os, hashlib, uuid
from datetime import datetime

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', '/tmp/users.db')

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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            token TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        );
    ''')
    conn.commit(); conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def safe_user(row):
    d = dict(row)
    d.pop('password_hash', None)
    d.pop('token', None)
    return d

@app.route('/health')
def health():
    return jsonify({"status":"ok","service":"user-service","db":"sqlite"}), 200

@app.route('/users', methods=['GET'])
def get_users():
    conn = get_db()
    rows = conn.execute('SELECT * FROM users ORDER BY id').fetchall()
    conn.close()
    return jsonify({"users":[safe_user(r) for r in rows]}), 200

@app.route('/users/<int:uid>', methods=['GET'])
def get_user(uid):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    conn.close()
    if not row: return jsonify({"error":"User not found"}), 404
    return jsonify(safe_user(row)), 200

@app.route('/users/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    if not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({"error":"name, email and password are required"}), 400
    conn = get_db()
    if conn.execute('SELECT id FROM users WHERE email=?',(data['email'],)).fetchone():
        conn.close(); return jsonify({"error":"Email already registered"}), 409
    token = str(uuid.uuid4())
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.execute('INSERT INTO users (name,email,password_hash,phone,address,token,created_at) VALUES (?,?,?,?,?,?,?)',
                       (data['name'], data['email'].lower(), hash_password(data['password']),
                        data.get('phone',''), data.get('address',''), token, now))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return jsonify({"message":"Registration successful","user_id":uid,"token":token,"name":data['name'],"email":data['email']}), 201

@app.route('/users/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    if not data.get('email') or not data.get('password'):
        return jsonify({"error":"email and password are required"}), 400
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE email=?',(data['email'].lower(),)).fetchone()
    if not row or row['password_hash'] != hash_password(data['password']):
        conn.close(); return jsonify({"error":"Invalid email or password"}), 401
    token = str(uuid.uuid4())
    conn.execute('UPDATE users SET token=? WHERE id=?',(token, row['id']))
    conn.commit(); conn.close()
    return jsonify({"message":"Login successful","user_id":row['id'],"token":token,"name":row['name'],"email":row['email']}), 200

@app.route('/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT id FROM users WHERE id=?',(uid,)).fetchone():
        conn.close(); return jsonify({"error":"User not found"}), 404
    fields = ['name','phone','address']
    updates = {k:data[k] for k in fields if k in data}
    if 'password' in data:
        updates['password_hash'] = hash_password(data['password'])
    if updates:
        conn.execute(f'UPDATE users SET {", ".join(f"{k}=?" for k in updates)} WHERE id=?', list(updates.values())+[uid])
        conn.commit()
    row = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    conn.close()
    return jsonify(safe_user(row)), 200

@app.route('/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    conn = get_db()
    if not conn.execute('SELECT id FROM users WHERE id=?',(uid,)).fetchone():
        conn.close(); return jsonify({"error":"User not found"}), 404
    conn.execute('DELETE FROM users WHERE id=?',(uid,))
    conn.commit(); conn.close()
    return jsonify({"deleted":uid}), 200

@app.route('/users/stats', methods=['GET'])
def user_stats():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    today = conn.execute('SELECT COUNT(*) FROM users WHERE date(created_at)=date("now")').fetchone()[0]
    conn.close()
    return jsonify({"total_users":total,"new_today":today}), 200

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
