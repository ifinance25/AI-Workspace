"""Файлы, которые Claude записал в свою песочницу, а не в папку проекта.

Claude Code копирует рабочую папку в ``/tmp/claude-<uid>/<кодированный путь>/``.
Имя папки: каждый символ пути, кроме латиницы и цифр, заменён на ``-``.
Список артефактов и скачивание принимают только файлы внутри этой копии
конкретного проекта.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from src.utils.url_safety import is_path_within_root

_SESSION_DIR = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def encode_claude_cwd(path: str) -> str:
    return "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in path)


def claude_sandbox_prefix(project_root: Path) -> Path:
    root = Path(project_root).resolve()
    encoded = encode_claude_cwd(root.as_posix())
    return (Path(f"/tmp/claude-{os.getuid()}") / encoded).resolve()


def resolve_sandbox_path(project_root: Path, file_path: str) -> Path | None:
    """Абсолютный путь, если он лежит в песочнице этого проекта. Иначе None."""
    prefix = claude_sandbox_prefix(project_root)
    try:
        candidate = Path(file_path).resolve()
    except (OSError, ValueError):
        return None
    if candidate == prefix or not is_path_within_root(prefix, candidate):
        return None
    return candidate


def sandbox_display_rel(project_root: Path, candidate: Path) -> str:
    """Путь для подписи: без служебной папки сессии Claude."""
    rel = candidate.resolve().relative_to(claude_sandbox_prefix(project_root))
    parts = rel.parts
    if len(parts) >= 2 and _SESSION_DIR.match(parts[0]):
        return Path(*parts[1:]).as_posix()
    return rel.as_posix()
