"""Запуск только проектного офиса: вход, офис, ручная валидация находок.

Для сервера с документами заказчика. Здесь нет Claude Code, Telegram, терминала
SSH, чата по WebSocket, файлов проектов и загрузок: роутеры не подключаются,
процессы моста и подключений не создаются. Ключ Claude серверу не нужен.

    python scripts/run_office.py --host 0.0.0.0 --port 8765

Настройки те же, что у ``run_web.py`` (config/config.yaml и .env). Добавлено два
переменных окружения для работы за прокси: ``WEB_PUBLIC_ORIGIN`` (адрес сайта)
и ``WEB_COOKIE_SECURE=1``.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()


def _load_settings():
    from src.config import Settings

    config_path = Path("config/config.yaml")
    if not config_path.exists():
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    settings = Settings.from_yaml(config_path)
    origin = os.environ.get("WEB_PUBLIC_ORIGIN", "").strip()
    if origin:
        settings.web.public_origin = origin
    if os.environ.get("WEB_COOKIE_SECURE", "").strip() in ("1", "true", "yes"):
        settings.web.cookie_secure = True
    return settings


async def _serve(host: str | None, port: int | None) -> int:
    from src.claude.session import SessionManager
    from src.web.server import WebServer

    settings = _load_settings()
    if host:
        settings.web.host = host
    if port:
        settings.web.port = port
    settings.web.enabled = True
    # Вход только по паролю: статический bearer и Telegram здесь не нужны.
    settings.web.dev_login_enabled = False

    session_manager = SessionManager(storage_path=settings.get_session_database_path())
    server = WebServer(
        settings=settings.web,
        allowed_user_ids=settings.get_allowed_user_ids(),
        bot_username="",
        session_manager=session_manager,
        event_bus=None,
        jwt_secret=settings.get_web_jwt_secret(),
        admin_login=settings.get_admin_login(),
        admin_password=settings.get_admin_password(),
        display_settings=settings.display,
        office_only=True,
    )
    await server.start()
    logger.info("office_only_started", url=f"http://{settings.web.host}:{settings.web.port}")
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()
        await session_manager.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Проектный офис без чата, терминала и файлов")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    try:
        return asyncio.run(_serve(args.host, args.port))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
