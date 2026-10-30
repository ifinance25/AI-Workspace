# Бэкап AI-Panel в S3

Регион EC2: **eu-north-1**. Bucket по умолчанию: `ifinance-ai-panel-backups-eu-north-1`.

## Что делает пайплайн (ночной timer)

1. `sqlite3 .backup` → `/var/backups/ai-workspace/db/sessions-YYYY-MM-DD.db`
2. `tar.gz` проектов → `/var/backups/ai-workspace/projects/projects-YYYY-MM-DD.tar.gz`
3. Выгрузка в `s3://BUCKET/PREFIX/YYYY-MM-DD/` (`sessions.db`, `projects.tar.gz`, `manifest.json`)

Конфиг на сервере: `/etc/default/ai-workspace-backup` (пример в `backup.env.example`).

## Один раз: bucket + IAM role на EC2

На инстансе **нет** IAM role, без неё `aws s3 cp` не работает.

1. AWS Console → **CloudShell** (регион **Europe Stockholm / eu-north-1**).
2. **Actions → Upload file**: загрузите из git-клона папку `scripts/aws/` (все `.json` и `setup-s3-backup.sh`).
3. В CloudShell:

```bash
chmod +x setup-s3-backup.sh
export AWS_DEFAULT_REGION=eu-north-1
./setup-s3-backup.sh
```

4. На сервере (SSH):

```bash
sudo systemctl start ai-workspace-db-backup.service
sudo journalctl -u ai-workspace-db-backup.service -n 20 --no-pager
aws s3 ls s3://ifinance-ai-panel-backups-eu-north-1/prod/ai-panel/
```

Последняя команда `aws s3 ls` выполняется **на EC2** после attach role (через 1–2 минуты после setup).

## Проверка

```bash
ssh AWS 'sudo systemctl start ai-workspace-db-backup.service && sudo journalctl -u ai-workspace-db-backup.service -n 15 --no-pager'
```

В S3 должна появиться папка с сегодняшней датой.

## Lifecycle

В bucket включено удаление объектов старше **90 дней** под prefix `prod/ai-panel/` (переменная `AI_WORKSPACE_S3_RETENTION_DAYS` в setup).

Локально на диске retention **14 дней** (`AI_WORKSPACE_BACKUP_RETENTION_DAYS`).
