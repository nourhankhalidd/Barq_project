#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-postgres}"
DB_USER="${POSTGRES_USER:-barq_app}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
BACKUP_FILE="${1:-}"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup-file>" >&2
  exit 2
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "FAIL: backup file does not exist or is empty: $BACKUP_FILE" >&2
  exit 1
fi

echo "=== BARQ PostgreSQL Restore ==="
echo "Container: $CONTAINER"
echo "Database: $DB_NAME"
echo "Backup: $BACKUP_FILE"

docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null

echo "WARNING: existing database objects will be replaced."

docker exec -i "$CONTAINER" \
  pg_restore \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --clean \
  --if-exists \
  --no-owner \
  --exit-on-error \
  < "$BACKUP_FILE"

echo "PASS: PostgreSQL restore completed"
