#!/usr/bin/env bash
# Ночная копия сервера валидации: база SQLite и каталог файлов прогонов.
# База копируется командой .backup (согласованный снимок при работающем сервисе),
# затем проверяется PRAGMA integrity_check. Старше KEEP_DAYS дней копии удаляются.
# Внешней копии нет: при потере диска пропадут решения людей (см. docs/deploy-tatnet-office.md).
set -euo pipefail
# macOS: tar не добавляет служебные файлы ._*; на Linux переменная ни на что не влияет.
export COPYFILE_DISABLE=1

DATA_DIR="${DATA_DIR:-/srv/fakt/validation/data}"
BACKUP_DIR="${BACKUP_DIR:-/srv/fakt/validation-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB="${DATA_DIR}/sessions.db"

[[ -f "$DB" ]] || { echo "Нет базы: $DB" >&2; exit 1; }
[[ "$KEEP_DAYS" =~ ^[0-9]+$ ]] || { echo "KEEP_DAYS должен быть числом" >&2; exit 1; }

umask 077
mkdir -p "$BACKUP_DIR"
work="$(mktemp -d "${BACKUP_DIR}/.tmp.XXXXXX")"
trap 'rm -rf "$work"' EXIT

sqlite3 "$DB" ".backup '${work}/sessions.db'"
[[ "$(sqlite3 "${work}/sessions.db" 'PRAGMA integrity_check')" == "ok" ]] \
    || { echo "Копия базы не прошла integrity_check" >&2; exit 1; }

parts=(sessions.db)
if [[ -d "${DATA_DIR}/office_validation" ]]; then
    tar -C "$DATA_DIR" -cf "${work}/office_validation.tar" office_validation
    parts+=(office_validation.tar)
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${BACKUP_DIR}/validation-${stamp}.tar.gz"
tar -C "$work" -czf "${out}.part" "${parts[@]}"
mv "${out}.part" "$out"

find "$BACKUP_DIR" -maxdepth 1 -name 'validation-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "Копия: $out"
