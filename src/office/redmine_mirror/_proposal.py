"""Предложение задачи от чата: подпись, чтобы создать можно было только то, что дал инструмент.

Чат не пишет в Redmine. Он получает от инструмента готовый блок с подписью, человек видит
карточку и нажимает «Создать». Сервер создаёт задачу, только если подпись совпала с полями
и с пользователем: модель не может ни подделать карточку, ни подсунуть её другому человеку.
"""

from __future__ import annotations

import hashlib
import hmac

SUBJECT_MAX = 255
DESCRIPTION_MAX = 10_000


def _material(project_id: int, user_id: int, subject: str, description: str, due_date: str) -> bytes:
    parts = (str(int(project_id)), str(int(user_id)), subject, description, due_date)
    return "\x1f".join(parts).encode("utf-8")


def sign(
    secret: str, project_id: int, user_id: int, subject: str, description: str, due_date: str
) -> str:
    material = _material(project_id, user_id, subject, description, due_date)
    return hmac.new(secret.encode("utf-8"), b"redmine-proposal\x1f" + material, hashlib.sha256).hexdigest()


def verify(
    secret: str,
    signature: str,
    project_id: int,
    user_id: int,
    subject: str,
    description: str,
    due_date: str,
) -> bool:
    if not secret or not signature:
        return False
    expected = sign(secret, project_id, user_id, subject, description, due_date)
    return hmac.compare_digest(expected, signature)


def request_key(signature: str) -> str:
    """Ключ повтора: двойное нажатие «Создать» вторую задачу не заводит."""
    return f"chat-{signature[:32]}"
