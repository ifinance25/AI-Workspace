#!/usr/bin/env bash
# backup_projects.sh — сжатый архив каталога проектов (PROJECTS_DIR).
set -euo pipefail

PROJECTS_DIR="${AI_WORKSPACE_PROJECTS_DIR:-/var/lib/ai-workspace/projects}"
ARCHIVE_DIR="${AI_WORKSPACE_PROJECTS_BACKUP_DIR:-/var/backups/ai-workspace/projects}"
RETENTION="${AI_WORKSPACE_BACKUP_RETENTION_DAYS:-14}"

if [[ ! -d "$PROJECTS_DIR" ]]; then
    echo "projects dir missing: $PROJECTS_DIR" >&2
    exit 1
fi

install -d -m 0750 -o root -g root "$ARCHIVE_DIR"

DATE="$(date +%Y-%m-%d)"
TARGET="$ARCHIVE_DIR/projects-${DATE}.tar.gz"
TMP="$ARCHIVE_DIR/.projects-${DATE}.tar.gz.tmp"

tar -C "$(dirname "$PROJECTS_DIR")" -czf "$TMP" "$(basename "$PROJECTS_DIR")"
mv -f "$TMP" "$TARGET"
chmod 0640 "$TARGET"
ln -sfn "$(basename "$TARGET")" "$ARCHIVE_DIR/projects.latest.tar.gz"

find "$ARCHIVE_DIR" -maxdepth 1 -type f -name 'projects-????-??-??.tar.gz' -mtime +"$RETENTION" -delete

echo "projects archive ok: $TARGET"
