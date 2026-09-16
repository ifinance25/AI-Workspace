"""Open an interactive SSH shell and bridge it to a WebSocket."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from src.ssh.store import SshProfile

logger = structlog.get_logger()

CONNECT_TIMEOUT_SEC = 20
KEEPALIVE_INTERVAL = 30
MAX_IN_CHARS = 16_384
DEFAULT_COLS = 80
DEFAULT_ROWS = 24


class SshConnectError(RuntimeError):
    """Public, safe-to-show SSH connection failure."""


def public_ssh_error(exc: BaseException) -> str:
    """Map library errors to a short Russian message (no secrets)."""
    msg = str(exc).lower()
    if "permission denied" in msg or "authentication" in msg or "auth" in msg:
        return "Сервер отклонил ключ или имя пользователя"
    if "timed out" in msg or "timeout" in msg:
        return "Не удалось достучаться до сервера (таймаут)"
    if "name or service not known" in msg or "nodename" in msg or "resolve" in msg:
        return "Не удалось найти хост (проверьте адрес)"
    if "connection refused" in msg or "connect" in msg:
        return "Сервер не принял соединение (хост, порт или сеть)"
    return "Ошибка SSH-подключения"


async def open_ssh_shell(
    profile: SshProfile,
    *,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
) -> tuple[Any, Any]:
    """Connect and start a PTY login shell. Returns (connection, process)."""
    import asyncssh

    try:
        key = asyncssh.import_private_key(
            profile.private_key,
            passphrase=profile.passphrase or None,
        )
    except (asyncssh.KeyImportError, ValueError, TypeError) as exc:
        raise SshConnectError("Не удалось прочитать сохранённый ключ") from exc

    try:
        conn = await asyncio.wait_for(
            asyncssh.connect(
                profile.host,
                port=profile.port,
                username=profile.username,
                client_keys=[key],
                known_hosts=None,
                keepalive_interval=KEEPALIVE_INTERVAL,
                login_timeout=CONNECT_TIMEOUT_SEC,
            ),
            timeout=CONNECT_TIMEOUT_SEC + 2,
        )
    except asyncio.TimeoutError as exc:
        raise SshConnectError("Не удалось достучаться до сервера (таймаут)") from exc
    except Exception as exc:
        raise SshConnectError(public_ssh_error(exc)) from exc

    try:
        process = await conn.create_process(
            term_type="xterm-256color",
            term_size=(max(cols, 20), max(rows, 8)),
            encoding=None,
        )
    except Exception as exc:
        conn.close()
        try:
            await conn.wait_closed()
        except Exception:
            pass
        raise SshConnectError(public_ssh_error(exc)) from exc
    return conn, process


OpenShellFn = Callable[..., Awaitable[tuple[Any, Any]]]


def _clamp_size(value: object, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


async def bridge_ssh_websocket(
    websocket: WebSocket,
    profile: SshProfile,
    *,
    open_shell: OpenShellFn | None = None,
) -> None:
    """Accept is already done. Pump stdin/stdout until either side closes."""
    connect = open_shell or open_ssh_shell
    conn = None
    process = None
    try:
        conn, process = await connect(
            profile, cols=DEFAULT_COLS, rows=DEFAULT_ROWS
        )
    except SshConnectError as exc:
        await websocket.send_json({"type": "error", "error": str(exc)})
        return
    except Exception as exc:
        logger.warning("ssh_connect_failed", error=str(exc), host=profile.host)
        await websocket.send_json(
            {"type": "error", "error": public_ssh_error(exc)}
        )
        return

    await websocket.send_json(
        {
            "type": "ready",
            "host": profile.host,
            "port": profile.port,
            "username": profile.username,
        }
    )

    async def stdout_pump() -> None:
        try:
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                if isinstance(chunk, bytes):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = str(chunk)
                await websocket.send_json({"type": "out", "data": text})
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.info("ssh_stdout_ended", error=str(exc))

    async def stdin_pump() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if kind == "in":
                    data = msg.get("data")
                    if not isinstance(data, str) or not data:
                        continue
                    if len(data) > MAX_IN_CHARS:
                        data = data[:MAX_IN_CHARS]
                    payload = data.encode("utf-8", errors="replace")
                    process.stdin.write(payload)
                    await _maybe_drain(process.stdin)
                elif kind == "resize":
                    cols = _clamp_size(msg.get("cols"), DEFAULT_COLS, 20, 400)
                    rows = _clamp_size(msg.get("rows"), DEFAULT_ROWS, 8, 200)
                    changer = getattr(process, "change_terminal_size", None)
                    if callable(changer):
                        changer(cols, rows)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.info("ssh_stdin_ended", error=str(exc))

    out_task = asyncio.create_task(stdout_pump())
    in_task = asyncio.create_task(stdin_pump())
    try:
        done, pending = await asyncio.wait(
            {out_task, in_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        for task in done:
            exc = task.exception() if not task.cancelled() else None
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.info("ssh_bridge_task_error", error=str(exc))
    finally:
        await _close_ssh(conn, process)


async def _maybe_drain(stdin: Any) -> None:
    drain = getattr(stdin, "drain", None)
    if callable(drain):
        result = drain()
        if asyncio.iscoroutine(result):
            await result


async def _close_ssh(conn: Any, process: Any) -> None:
    for obj in (process, conn):
        if obj is None:
            continue
        closer = getattr(obj, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        wait = getattr(obj, "wait_closed", None)
        if callable(wait):
            try:
                result = wait()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
