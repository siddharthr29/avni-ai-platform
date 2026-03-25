#!/usr/bin/env bash
# =============================================================================
# Avni AI Platform — PostgreSQL Backup Script
#
# Usage:
#   ./scripts/backup.sh                    # Local backup only
#   ./scripts/backup.sh --s3               # Local + S3 upload
#   ./scripts/backup.sh --s3 --cleanup     # Local + S3 + rotate old backups
#
# Cron example (daily at 2 AM):
#   0 2 * * * /opt/avni-ai-platform/scripts/backup.sh --s3 --cleanup >> /var/log/avni-backup.log 2>&1
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$0")/../backups}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-avni_ai}"
DB_USER="${DB_USER:-avni_ai}"
DB_PASSWORD="${DB_PASSWORD:-}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-avni-ai/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="avni_ai_${TIMESTAMP}.dump.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

UPLOAD_TO_S3=false
CLEANUP=false

for arg in "$@"; do
    case "$arg" in
        --s3) UPLOAD_TO_S3=true ;;
        --cleanup) CLEANUP=true ;;
        --help|-h)
            echo "Usage: $0 [--s3] [--cleanup]"
            echo "  --s3       Upload backup to S3 (requires AWS CLI and S3_BUCKET env var)"
            echo "  --cleanup  Remove local backups older than RETENTION_DAYS (default: 30)"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error_exit() {
    log "ERROR: $*"
    exit 1
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [ -z "$DB_PASSWORD" ]; then
    error_exit "DB_PASSWORD environment variable must be set"
fi

mkdir -p "$BACKUP_DIR"

if ! command -v pg_dump &> /dev/null; then
    # Try using Docker container
    log "pg_dump not found locally, using Docker container..."
    USE_DOCKER=true
else
    USE_DOCKER=false
fi

# ---------------------------------------------------------------------------
# Create backup
# ---------------------------------------------------------------------------
log "Starting backup of database '$DB_NAME' on $DB_HOST:$DB_PORT"
START_TIME=$(date +%s)

export PGPASSWORD="$DB_PASSWORD"

if [ "$USE_DOCKER" = true ]; then
    docker exec avni-ai-db pg_dump \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --format=custom \
        --compress=0 \
        --verbose \
        2>/dev/null | gzip > "$BACKUP_PATH"
else
    pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --format=custom \
        --compress=0 \
        --verbose \
        2>/dev/null | gzip > "$BACKUP_PATH"
fi

unset PGPASSWORD

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)

log "Backup completed in ${DURATION}s: $BACKUP_PATH ($BACKUP_SIZE)"

# ---------------------------------------------------------------------------
# Verify backup integrity
# ---------------------------------------------------------------------------
if [ ! -s "$BACKUP_PATH" ]; then
    error_exit "Backup file is empty: $BACKUP_PATH"
fi

log "Backup integrity check passed (file is non-empty)"

# ---------------------------------------------------------------------------
# Upload to S3
# ---------------------------------------------------------------------------
if [ "$UPLOAD_TO_S3" = true ]; then
    if [ -z "$S3_BUCKET" ]; then
        log "WARNING: S3_BUCKET not set, skipping S3 upload"
    elif ! command -v aws &> /dev/null; then
        log "WARNING: AWS CLI not found, skipping S3 upload"
    else
        S3_PATH="s3://${S3_BUCKET}/${S3_PREFIX}/${BACKUP_FILE}"
        log "Uploading to $S3_PATH ..."

        aws s3 cp "$BACKUP_PATH" "$S3_PATH" \
            --storage-class STANDARD_IA \
            --only-show-errors

        log "S3 upload completed"
    fi
fi

# ---------------------------------------------------------------------------
# Rotate old backups
# ---------------------------------------------------------------------------
if [ "$CLEANUP" = true ]; then
    log "Removing local backups older than ${RETENTION_DAYS} days..."

    DELETED_COUNT=$(find "$BACKUP_DIR" -name "avni_ai_*.dump.gz" -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
    log "Deleted $DELETED_COUNT old backup(s)"

    # S3 lifecycle is preferred for S3 rotation, but we can clean up here too
    if [ "$UPLOAD_TO_S3" = true ] && [ -n "$S3_BUCKET" ] && command -v aws &> /dev/null; then
        CUTOFF_DATE=$(date -d "-${RETENTION_DAYS} days" +%Y%m%d 2>/dev/null || date -v-${RETENTION_DAYS}d +%Y%m%d)
        log "Note: Configure S3 lifecycle policies for automated S3 backup rotation"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "avni_ai_*.dump.gz" 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

log "=== Backup Summary ==="
log "  File: $BACKUP_FILE"
log "  Size: $BACKUP_SIZE"
log "  Duration: ${DURATION}s"
log "  Total backups: $TOTAL_BACKUPS ($TOTAL_SIZE)"
log "  S3 upload: $([ "$UPLOAD_TO_S3" = true ] && echo 'yes' || echo 'no')"
log "=== Done ==="
