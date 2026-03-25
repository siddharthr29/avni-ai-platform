#!/usr/bin/env bash
# =============================================================================
# Avni AI Platform — Production Deploy Script
#
# Usage:
#   ./scripts/deploy.sh                  # Deploy latest from current branch
#   ./scripts/deploy.sh --rollback       # Rollback to previous deployment
#   ./scripts/deploy.sh --sha abc123     # Deploy specific commit
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_URL="http://localhost:8080/health"
HEALTH_TIMEOUT=60
PREV_SHA_FILE="${APP_DIR}/.prev-deploy-sha"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
ROLLBACK=false
TARGET_SHA=""

for arg in "$@"; do
    case "$arg" in
        --rollback)
            ROLLBACK=true
            ;;
        --sha)
            shift
            TARGET_SHA="${1:-}"
            ;;
        --sha=*)
            TARGET_SHA="${arg#--sha=}"
            ;;
        --help|-h)
            echo "Usage: $0 [--rollback] [--sha <commit>]"
            echo "  --rollback   Roll back to previous deployment"
            echo "  --sha SHA    Deploy specific git commit"
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error_exit() {
    log "ERROR: $*"
    exit 1
}

wait_for_health() {
    local url="$1"
    local timeout="$2"
    local start elapsed

    start=$(date +%s)
    log "Waiting for health check at $url (timeout: ${timeout}s)..."

    while true; do
        elapsed=$(( $(date +%s) - start ))
        if [ "$elapsed" -ge "$timeout" ]; then
            return 1
        fi

        if curl -sf "$url" > /dev/null 2>&1; then
            log "Health check passed after ${elapsed}s"
            return 0
        fi

        sleep 2
    done
}

do_rollback() {
    if [ ! -f "$PREV_SHA_FILE" ]; then
        error_exit "No previous deployment SHA found. Cannot rollback."
    fi

    local prev_sha
    prev_sha=$(cat "$PREV_SHA_FILE")
    log "=== ROLLING BACK to $prev_sha ==="

    cd "$APP_DIR"
    git checkout "$prev_sha"

    docker compose -f "$COMPOSE_FILE" build --parallel
    docker compose -f "$COMPOSE_FILE" up -d

    if wait_for_health "$HEALTH_URL" "$HEALTH_TIMEOUT"; then
        log "=== Rollback completed successfully ==="
    else
        error_exit "Rollback health check failed. Manual intervention required."
    fi
}

# ---------------------------------------------------------------------------
# Main deploy flow
# ---------------------------------------------------------------------------
cd "$APP_DIR"

# Handle rollback
if [ "$ROLLBACK" = true ]; then
    do_rollback
    exit 0
fi

log "=== Avni AI Platform — Production Deploy ==="

# Save current state for rollback
CURRENT_SHA=$(git rev-parse HEAD)
echo "$CURRENT_SHA" > "$PREV_SHA_FILE"
log "Current SHA: $CURRENT_SHA (saved for rollback)"

# Pull latest or checkout specific SHA
if [ -n "$TARGET_SHA" ]; then
    log "Deploying specific commit: $TARGET_SHA"
    git fetch origin
    git checkout "$TARGET_SHA"
else
    log "Pulling latest changes..."
    git pull origin "$(git branch --show-current)"
fi

NEW_SHA=$(git rev-parse HEAD)
log "Deploying SHA: $NEW_SHA"

if [ "$CURRENT_SHA" = "$NEW_SHA" ] && [ -z "$TARGET_SHA" ]; then
    log "Already at latest commit. Rebuilding anyway..."
fi

# ---------------------------------------------------------------------------
# Build images
# ---------------------------------------------------------------------------
log "Building Docker images..."
docker compose -f "$COMPOSE_FILE" build --parallel

# ---------------------------------------------------------------------------
# Run database migrations
# ---------------------------------------------------------------------------
log "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm backend \
    python -c "import asyncio; from app.db import init_db; asyncio.run(init_db())" \
    2>&1 || log "WARNING: Migration step returned non-zero (may be OK if tables already exist)"

# ---------------------------------------------------------------------------
# Rolling restart
# ---------------------------------------------------------------------------
log "Starting rolling restart..."

# 1. Restart backend (nginx continues to serve old connections)
log "Restarting backend..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps --build backend

# 2. Wait for backend to be healthy
if ! wait_for_health "$HEALTH_URL" "$HEALTH_TIMEOUT"; then
    log "ERROR: Backend health check failed. Initiating rollback..."
    do_rollback
    exit 1
fi

# 3. Restart frontend and nginx
log "Restarting frontend and nginx..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps frontend
sleep 3
docker compose -f "$COMPOSE_FILE" up -d --no-deps nginx

# 4. Final health check
sleep 5
if ! wait_for_health "$HEALTH_URL" 30; then
    log "ERROR: Final health check failed. Initiating rollback..."
    do_rollback
    exit 1
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
log "Cleaning up old Docker images..."
docker image prune -f --filter "until=168h" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log "=== Deploy Summary ==="
log "  Previous SHA: $CURRENT_SHA"
log "  Deployed SHA: $NEW_SHA"
log "  Backend status: $(docker compose -f "$COMPOSE_FILE" ps --format '{{.Status}}' backend 2>/dev/null || echo 'unknown')"
log "  Health: OK"
log "=== Deploy completed successfully ==="
