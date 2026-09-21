#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-postgres}"
DB_USER="${POSTGRES_USER:-barq_app}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"

echo "=== BARQ PostgreSQL Backup ==="
echo "Container: $CONTAINER"
echo "Database: $DB_NAME"
echo "Output: $BACKUP_FILE"

docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null

docker exec "$CONTAINER" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc \
  > "$BACKUP_FILE"

test -s "$BACKUP_FILE"

echo "PASS: PostgreSQL backup created"
ls -lh "$BACKUP_FILE"
