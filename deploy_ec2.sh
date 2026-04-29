#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
#  deploy_ec2.sh — pull latest images and restart all services
#  Run this on the EC2 server after Jenkins pushes new Docker images.
#
#  Usage:
#    ./deploy_ec2.sh            # deploy latest
#    ./deploy_ec2.sh rollback   # revert to previous images
# ─────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] ⚠${NC}  $1"; }
fail() { echo -e "${RED}[$(date +%H:%M:%S)] ✗${NC}  $1"; exit 1; }

# ── Rollback mode ────────────────────────────────────────────────────
if [ "$1" = "rollback" ]; then
    warn "Rolling back to previous images..."
    docker compose down
    # Docker keeps the previous image layer — just re-tag previous as latest
    for svc in product-service order-service user-service payment-service frontend; do
        PREV=$(docker images vivek7378/${svc} --format "{{.Tag}}" | grep -v latest | head -1)
        if [ -n "$PREV" ]; then
            docker tag vivek7378/${svc}:${PREV} vivek7378/${svc}:latest
            log "Rolled back ${svc} to :${PREV}"
        else
            warn "No previous image found for ${svc} — keeping current"
        fi
    done
    docker compose up -d
    log "Rollback complete"
    exit 0
fi

# ── Normal deploy ────────────────────────────────────────────────────
log "=== ShopEasy Deploy Started ==="

log "Step 1: Pulling latest images from DockerHub..."
docker compose pull || fail "Failed to pull images — check DockerHub credentials"

log "Step 2: Restarting services with zero-downtime..."
# up --no-deps only restarts containers whose image changed
docker compose up -d --remove-orphans

log "Step 3: Waiting for services to be healthy..."
sleep 5

SERVICES=("product-service:5001" "order-service:5002" "user-service:5003" "payment-service:5004")
ALL_OK=true

for entry in "${SERVICES[@]}"; do
    name="${entry%%:*}"
    port="${entry##*:}"
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "no-healthcheck")
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${port}/health" 2>/dev/null || echo "000")

    if [ "$HTTP" = "200" ]; then
        log "   $name → HTTP 200 on port $port"
    else
        warn "  ⚠  $name → HTTP $HTTP on port $port (container status: $STATUS)"
        ALL_OK=false
    fi
done

log "Step 4: Running containers:"
docker compose ps

echo ""
if [ "$ALL_OK" = true ]; then
    log "=== Deploy SUCCESSFUL ==="
    echo ""
    echo "   Frontend     → http://$(curl -s ifconfig.me 2>/dev/null || echo 'EC2_PUBLIC_IP'):80"
    echo "   Products API → http://$(curl -s ifconfig.me 2>/dev/null || echo 'EC2_PUBLIC_IP'):5001"
    echo "   Orders API   → http://$(curl -s ifconfig.me 2>/dev/null || echo 'EC2_PUBLIC_IP'):5002"
    echo "   Users API    → http://$(curl -s ifconfig.me 2>/dev/null || echo 'EC2_PUBLIC_IP'):5003"
    echo "   Payments API → http://$(curl -s ifconfig.me 2>/dev/null || echo 'EC2_PUBLIC_IP'):5004"
else
    warn "=== Deploy finished with warnings — check logs above ==="
    echo "  Run:  docker compose logs --tail=50  to debug"
fi
