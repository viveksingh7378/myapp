#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# stop_services.sh  —  Stop all 4 Flask microservices
# ─────────────────────────────────────────────────────────────────

echo ""
echo " Stopping all ShopEasy services..."
echo ""

for PORT in 5001 5002 5003 5004; do
  PID=$(lsof -ti tcp:$PORT 2>/dev/null)
  if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null
    echo "  Stopped port $PORT (PID $PID)"
  else
    echo "  Port $PORT — already stopped"
  fi
done

echo ""
echo " All services stopped."
echo ""
