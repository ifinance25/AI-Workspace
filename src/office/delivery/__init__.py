"""Граница ``delivery``: пока только ручная валидация находок прогона.

Это узкая часть будущего модуля поставки (``architecture/10``, таски 34 и 35).
Импорт пакета, решения проверяющего, статистика, markdown и выгрузка. Публичные
операции здесь, внутренности в модулях ``_*.py``.
"""
from src.office.delivery._validation_access import (
    require_decide,
    require_manage,
    require_team,
)
from src.office.delivery._validation_decisions import decide
from src.office.delivery._validation_export import export_run
from src.office.delivery._validation_files import purge_project_files, rebuild_files, sync_files
from src.office.delivery._validation_import import MAX_ARCHIVE_BYTES, import_package
from src.office.delivery._validation_read import (
    asset_path,
    get_finding,
    get_policy,
    get_run,
    has_runs,
    list_findings,
    list_runs,
    set_policy,
)
from src.office.delivery._validation_redmine import export_finding_to_redmine, export_run_stand_remediation
from src.office.delivery._validation_schema import ValidationError, data_root, ensure, run_dir

__all__ = [
    "MAX_ARCHIVE_BYTES",
    "ValidationError",
    "actor_ref",
    "asset_path",
    "data_root",
    "decide",
    "ensure",
    "export_finding_to_redmine",
    "export_run_stand_remediation",
    "export_run",
    "get_finding",
    "get_policy",
    "get_run",
    "has_runs",
    "import_package",
    "list_findings",
    "list_runs",
    "purge_project_files",
    "rebuild_files",
    "require_decide",
    "require_manage",
    "require_team",
    "run_dir",
    "set_policy",
    "sync_files",
]
