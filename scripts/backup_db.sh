#!/usr/bin/env bash
# Nightly PostgreSQL backup for the production Compose stack.
#
# Writes a timestamped, gzip-compressed SQL dump to BACKUP_DIR, verifies the
# gzip stream, and deletes dumps older than BACKUP_RETENTION_DAYS. Run it from
# cron on the host (see DEPLOYMENT.md); Docker must be available to that user.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "BACKUP_RETENTION_DAYS must be a whole number, got: $RETENTION_DAYS" >&2
    exit 1
fi

command -v docker >/dev/null 2>&1 || {
    echo "docker is not installed or not on PATH" >&2
    exit 1
}
for file in docker-compose.yml docker-compose.prod.yml; do
    if [ ! -f "$file" ]; then
        echo "Missing $file; run this script from the deployed checkout" >&2
        exit 1
    fi
done

umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

# Read the database name from the running container so POSTGRES_DB in .env is
# the single source of truth (the host script does not source .env).
db_name="$("${COMPOSE[@]}" exec -T db sh -c 'printf %s "$POSTGRES_DB"' | tr -d '\r\n')"
if [ -z "$db_name" ]; then
    echo "Could not read POSTGRES_DB from the db container; is the stack running?" >&2
    exit 1
fi
safe_db="$(printf '%s' "$db_name" | tr -c 'A-Za-z0-9._-' '_')"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$BACKUP_DIR/academic-dashboard_${safe_db}_${timestamp}.sql.gz"
tmp="${file}.partial"

cleanup() {
    rm -f "$tmp"
}
trap cleanup EXIT

echo "Backing up database '$db_name'..."
"${COMPOSE[@]}" exec -T db sh -c \
    'exec pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    | gzip -9 > "$tmp"

if [ ! -s "$tmp" ]; then
    echo "pg_dump produced an empty file; backup failed" >&2
    exit 1
fi
gzip -t "$tmp"

mv "$tmp" "$file"
chmod 600 "$file"
trap - EXIT

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'academic-dashboard_*.sql.gz' \
    -mtime +"$RETENTION_DAYS" -delete

echo "Backup written: $file ($(du -h "$file" | cut -f1))"
echo "Retained backups newer than ${RETENTION_DAYS} days in $BACKUP_DIR"
