#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# start_services.sh  —  Start all 4 Flask microservices locally
# Run this from the project root:  bash start_services.sh
# ─────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║      ShopEasy — Starting All Microservices           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Install dependencies for each service ──────────────────────
echo "📦 Installing dependencies..."
for svc in product-service order-service user-service payment-service; do
  pip3 install flask --quiet 2>/dev/null
done
echo ""

# ── Kill any previous instances on those ports ─────────────────
for PORT in 5001 5002 5003 5004; do
  PID=$(lsof -ti tcp:$PORT 2>/dev/null)
  if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null
    echo "  Stopped old process on port $PORT"
  fi
done

# ── Start each service in the background ───────────────────────
echo "🚀 Starting services..."
echo ""

cd "$ROOT/services/product-service" && \
  PYTHONPATH="$ROOT/services/product-service" \
  python3 app/app.py > /tmp/product.log 2>&1 &
echo "  ✅ product-service  → http://localhost:5001   (log: /tmp/product.log)"

cd "$ROOT/services/order-service" && \
  PYTHONPATH="$ROOT/services/order-service" \
  python3 app/app.py > /tmp/order.log 2>&1 &
echo "  ✅ order-service    → http://localhost:5002   (log: /tmp/order.log)"

cd "$ROOT/services/user-service" && \
  PYTHONPATH="$ROOT/services/user-service" \
  python3 app/app.py > /tmp/user.log 2>&1 &
echo "  ✅ user-service     → http://localhost:5003   (log: /tmp/user.log)"

cd "$ROOT/services/payment-service" && \
  PYTHONPATH="$ROOT/services/payment-service" \
  python3 app/app.py > /tmp/payment.log 2>&1 &
echo "  ✅ payment-service  → http://localhost:5004   (log: /tmp/payment.log)"

# ── Wait for startup ───────────────────────────────────────────
sleep 2
echo ""
echo "─────────────────────────────────────────────────────────"
echo "🌐 Open your website:"
echo "   file://$ROOT/frontend/index.html"
echo ""
echo "📄 New features demo page:"
echo "   file://$ROOT/new-features.html"
echo ""
echo "🔗 API Endpoints to test:"
echo "   http://localhost:5001/products             (all products)"
echo "   http://localhost:5001/products/featured    (NEW - top rated)"
echo "   http://localhost:5001/health"
echo ""
echo "   http://localhost:5002/orders               (all orders)"
echo "   http://localhost:5002/coupons/apply        (NEW - coupon page)"
echo "   http://localhost:5002/health"
echo ""
echo "   http://localhost:5003/users                (all users)"
echo "   http://localhost:5003/users/1/change-password  (NEW - change pwd)"
echo "   http://localhost:5003/health"
echo ""
echo "   http://localhost:5004/payments/summary     (payment stats)"
echo "   http://localhost:5004/payments/1/invoice   (NEW - invoice)"
echo "   http://localhost:5004/health"
echo ""
echo "   Jenkins Dashboard → http://localhost:8080"
echo "─────────────────────────────────────────────────────────"
echo ""
echo "⚠️  NOTE: New endpoints have syntax bugs on purpose!"
echo "   Push code → Jenkins detects errors → AI fixes them →"
echo "   Pull fixed code → restart this script → endpoints work!"
echo ""
echo "To stop all services:  bash stop_services.sh"
echo ""
