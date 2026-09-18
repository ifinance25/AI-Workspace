#!/usr/bin/env bash
# Перенос состояния с предыдущей установки AI-Panel на диске (другой INSTALL_DIR).
# Старый каталог на диске не удаляется.
#
# На проде до переезда каталог и сервис назывались иначе — задайте явно:
#   PREVIOUS_INSTALL_DIR=/opt/vels-claude \
#   PREVIOUS_SERVICE=vels-claude \
#   PREVIOUS_SERVICE_USER=vels-bot \
#   PREVIOUS_SERVICE_HOME=/var/lib/vels-bot \
#   sudo -E bash scripts/install.sh

migrate_previous_install_state() {
    local prev_dir="${PREVIOUS_INSTALL_DIR:-}"
    local prev_svc="${PREVIOUS_SERVICE:-}"
    local prev_user="${PREVIOUS_SERVICE_USER:-}"
    local prev_home="${PREVIOUS_SERVICE_HOME:-}"

    if [[ -z "$prev_dir" ]]; then
        # Авто: типичный путь прежней установки (имя каталога на диске до переезда).
        if [[ -f /opt/vels-claude/src/main.py ]]; then
            prev_dir="/opt/vels-claude"
        else
            return 0
        fi
    fi
    [[ -z "$prev_svc" ]] && prev_svc="vels-claude"
    [[ -z "$prev_user" ]] && prev_user="vels-bot"
    [[ -z "$prev_home" ]] && prev_home="/var/lib/${prev_user}"

    [[ -n "${INSTALL_DIR:-}" ]] || return 0
    [[ "$prev_dir" == "$INSTALL_DIR" ]] && return 0
    [[ -f "$prev_dir/src/main.py" ]] || return 0

    step "Migrate from previous install ($prev_dir)"

    if systemctl list-unit-files "${prev_svc}.service" &>/dev/null \
        && systemctl is-active --quiet "$prev_svc" 2>/dev/null; then
        log_info "Останавливаю прежний сервис $prev_svc (каталог $prev_dir не трогаем)"
        systemctl stop "$prev_svc" 2>/dev/null || true
        systemctl disable "$prev_svc" 2>/dev/null || true
    fi

    mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/config"

    if [[ -f "$prev_dir/.env" && -f "$INSTALL_DIR/.env" ]]; then
        local key line
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
            key="${line%%=*}"
            if ! grep -q "^${key}=" "$INSTALL_DIR/.env" 2>/dev/null; then
                printf '%s\n' "$line" >>"$INSTALL_DIR/.env"
            fi
        done <"$prev_dir/.env"
        log_ok "Дополнен .env недостающими ключами из $prev_dir"
    elif [[ -f "$prev_dir/.env" && ! -f "$INSTALL_DIR/.env" ]]; then
        cp -a "$prev_dir/.env" "$INSTALL_DIR/.env"
        log_ok "Скопирован .env из $prev_dir"
    fi

    if [[ -f "$prev_dir/config/config.local.yaml" \
          && ! -f "$INSTALL_DIR/config/config.local.yaml" ]]; then
        cp -a "$prev_dir/config/config.local.yaml" "$INSTALL_DIR/config/config.local.yaml"
        log_ok "Скопирован config.local.yaml"
    fi

    if [[ -d "$prev_dir/data" ]]; then
        local db
        for db in "$prev_dir/data"/*.db; do
            [[ -e "$db" ]] || continue
            local dest="$INSTALL_DIR/data/$(basename "$db")"
            if [[ ! -f "$dest" ]]; then
                cp -a "$db" "$dest"
                log_ok "Скопирована БД $(basename "$db")"
            fi
        done
    fi

    local prev_projects=""
    if [[ -f "$prev_dir/.env" ]]; then
        prev_projects="$(grep -E '^PROJECTS_DIR=' "$prev_dir/.env" | tail -1 | cut -d= -f2- || true)"
    fi
    [[ -n "$prev_projects" ]] || prev_projects="${prev_home}/projects"
    local dest_projects="${CFG_PROJECTS_DIR:-${SERVICE_HOME}/projects}"
    if [[ -d "$prev_projects" ]]; then
        mkdir -p "$dest_projects"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --ignore-existing "$prev_projects"/ "$dest_projects"/
        else
            cp -an "$prev_projects"/. "$dest_projects"/ 2>/dev/null || true
        fi
        chown -R "$SERVICE_USER":"${SERVICE_GROUP:-$SERVICE_USER}" "$dest_projects" 2>/dev/null || true
        log_ok "Проекты скопированы: $prev_projects -> $dest_projects"
    fi

    if [[ -d "$prev_home/.claude" && ! -e "${SERVICE_HOME}/.claude" ]]; then
        mkdir -p "$SERVICE_HOME"
        cp -a "$prev_home/.claude" "$SERVICE_HOME/.claude"
        chown -R "$SERVICE_USER":"${SERVICE_GROUP:-$SERVICE_USER}" "$SERVICE_HOME/.claude"
        log_ok "Перенесён ~/.claude пользователя $prev_user"
    fi

    log_info "Предыдущая установка в $prev_dir сохранена (удаление не выполнялось)."
}
