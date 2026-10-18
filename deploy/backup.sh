#!/usr/bin/env bash
# Consistent SQLite snapshot (online backup API, safe while the app writes) → Nebius Object Storage.
# Needs the AWS CLI configured for Nebius (deploy/nebius.md, step 6) and GLR_BACKUP_BUCKET in the environment.
# Cron (daily 03:00): 0 3 * * * cd ~/GreenLight_Research && GLR_BACKUP_BUCKET=glr-backups deploy/backup.sh
set -euo pipefail
: "${GLR_BACKUP_BUCKET:?set GLR_BACKUP_BUCKET}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T app python -c \
  "import sqlite3; s=sqlite3.connect('/data/glr.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp app:/data/backup.db "/tmp/glr-$stamp.db"
docker compose exec -T app rm -f /data/backup.db
gzip "/tmp/glr-$stamp.db"
aws s3 cp "/tmp/glr-$stamp.db.gz" "s3://$GLR_BACKUP_BUCKET/glr/glr-$stamp.db.gz"
rm -f "/tmp/glr-$stamp.db.gz"
echo "backed up glr-$stamp.db.gz"
