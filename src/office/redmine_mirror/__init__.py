"""Зеркало Redmine: локальная копия задач подключённого проекта.

Публичные вызовы: загрузить проект, загрузить одну задачу по номеру,
создать задачу, записать правку по номеру. Ключ API, разбор ответа
и сопоставление логинов наружу не выходят.
"""

from src.office.redmine_mirror._account import (
    TokenStorageDisabledError,
    account_view,
    cipher_for,
    cipher_from_key,
    resolve_access,
    save_account,
    url_allowed,
)
from src.office.redmine_mirror._http import open_client
from src.office.redmine_mirror._demo_seed import create_demo_issue, seed_demo_mirror
from src.office.redmine_mirror._mirror import (
    SYNC_INTERVAL_MINUTES,
    MirrorError,
    RedmineUnavailableError,
    connection_url,
    create_issue,
    load_issue,
    load_project,
    run_due,
    update_issue,
)

__all__ = [
    "SYNC_INTERVAL_MINUTES",
    "MirrorError",
    "RedmineUnavailableError",
    "TokenStorageDisabledError",
    "account_view",
    "cipher_for",
    "cipher_from_key",
    "connection_url",
    "create_issue",
    "load_issue",
    "load_project",
    "open_client",
    "resolve_access",
    "run_due",
    "save_account",
    "seed_demo_mirror",
    "create_demo_issue",
    "update_issue",
    "url_allowed",
]
