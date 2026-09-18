# Переезд на `/opt/ai-workspace`

Установщик по умолчанию ставит код в `/opt/ai-workspace`, systemd-сервис `ai-workspace`,
системный пользователь `ai-workspace`, проекты в `/var/lib/ai-workspace/projects`.

## С сохранением данных со старой установки

Если на сервере уже работала панель в другом каталоге (например `/opt/vels-claude`),
**старый каталог не удаляйте**. Установщик при первом запуске в новый путь:

1. Останавливает прежний systemd-сервис (если он ещё активен).
2. Дополняет новый `.env` ключами из старого (JWT и пароль админа не затирает).
3. Копирует `data/*.db`, `config/config.local.yaml`, каталог проектов и `~/.claude` сервисного пользователя.

Автоопределение: если существует `/opt/vels-claude/src/main.py`, он считается источником.
Иначе задайте переменные явно:

```bash
export PREVIOUS_INSTALL_DIR=/opt/vels-claude
export PREVIOUS_SERVICE=vels-claude
export PREVIOUS_SERVICE_USER=vels-bot
export PREVIOUS_SERVICE_HOME=/var/lib/vels-bot
curl -sSL https://raw.githubusercontent.com/ifinance25/AI-Workspace/develop/scripts/install.sh | sudo -E bash
```

После установки проверьте:

```bash
systemctl status ai-workspace
journalctl -u ai-workspace -n 50 --no-pager
```

Старый каталог остаётся на диске для ручного сравнения и резервной копии.

## Обновление без git (релиз-архив)

Повторите команду установки из README. `.env` и `data/` не перезаписываются целиком.
