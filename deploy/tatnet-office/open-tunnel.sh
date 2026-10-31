#!/usr/bin/env bash
# Открыть сервис валидации на VPS tatnet через защищённый SSH-туннель.
# Пока у runs.pm-workspace.ru нет DNS-записи и сертификата, это единственный путь к сервису:
# порт контейнера наружу не опубликован.
#
#   bash deploy/tatnet-office/open-tunnel.sh              поднять туннель и открыть браузер
#   bash deploy/tatnet-office/open-tunnel.sh --close      закрыть туннель
#   bash deploy/tatnet-office/open-tunnel.sh --show-admin показать логин и пароль администратора (только в вашем терминале)
set -euo pipefail

HOST="${TATNET_HOST:-fact@185.152.82.63}"
PORT="${TATNET_RUNS_PORT:-8613}"
URL="http://localhost:${PORT}/office/1/runs"

case "${1:-}" in
    --close)
        pkill -f "ssh .*-L ${PORT}:" && echo "Туннель закрыт" || echo "Туннель не был открыт"
        exit 0 ;;
    --show-admin)
        ssh -o BatchMode=yes "$HOST" "sudo grep -E '^(ADMIN_LOGIN|ADMIN_PASSWORD)=' /srv/fakt/validation/runs.env" \
            | sed -e 's/^ADMIN_LOGIN=/Логин:  /' -e 's/^ADMIN_PASSWORD=/Пароль: /'
        exit 0 ;;
    "") ;;
    *) echo "Неизвестный аргумент: $1" >&2; exit 2 ;;
esac

IP="$(ssh -o BatchMode=yes "$HOST" "sudo docker inspect -f '{{(index .NetworkSettings.Networks \"fakt_runs-net\").IPAddress}}' fakt-runs")"
[[ -n "$IP" ]] || { echo "Контейнер fakt-runs не найден или не запущен" >&2; exit 1; }
pkill -f "ssh .*-L ${PORT}:" 2>/dev/null || true
ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -f -N -L "${PORT}:${IP}:8765" "$HOST"
sleep 1
curl -fs --max-time 5 "http://localhost:${PORT}/api/health" >/dev/null || { echo "Сервис не ответил через туннель" >&2; exit 1; }
echo "Туннель открыт: $URL"
echo "Войти как admin, пароль: bash deploy/tatnet-office/open-tunnel.sh --show-admin"
echo "Закрыть: bash deploy/tatnet-office/open-tunnel.sh --close"
command -v open >/dev/null && open "$URL"
