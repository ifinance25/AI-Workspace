"""Фильтр бота: вне белого списка живут только привязка и /weblogin в личке."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, PhotoSize, Update, User

from src.bot.handlers import commands
from src.bot.middleware import AuthMiddleware, SecurityMiddleware
from src.office.storage import OfficeStore, hash_channel_code

OWNER = 100
TEAM = 7_900_000_000
STRANGER = 7_900_000_001
CODE = "A" * 32


def _message(text: str | None, user_id: int, *, chat_type: str = "private", **extra) -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id if chat_type == "private" else -100, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name="A", username="ivan"),
            text=text,
            **extra,
        ),
    )


@pytest.fixture
def env(tmp_path):
    store = OfficeStore(tmp_path / "o.db")
    bound = {TEAM}
    issued: list[int] = []

    def issue(user_id: int) -> str:
        issued.append(user_id)
        return f"http://127.0.0.1/login?magic={user_id}"

    previous = getattr(commands.router, "web_server", None)
    commands.router.web_server = SimpleNamespace(
        office_store=store, issue_magic_login_url=issue
    )
    dp = Dispatcher()
    dp.message.middleware(
        AuthMiddleware(
            [OWNER], team_resolver=lambda tg_id: {"user_id": 1} if tg_id in bound else None
        )
    )
    dp.message.middleware(
        SecurityMiddleware(allowed_roots=[], audit_log_path=tmp_path / "security.log")
    )
    dp.include_router(commands.router)
    bot = Bot(token="42:TEST")
    answer = AsyncMock()
    # Фильтр Command сверяет @имя через getMe: в тестах без сети.
    me = User(id=42, is_bot=True, first_name="Bot", username="paneltestbot")
    with patch.object(Message, "answer", answer), patch.object(
        Bot, "me", AsyncMock(return_value=me)
    ):
        yield SimpleNamespace(dp=dp, bot=bot, store=store, answer=answer, issued=issued)
    commands.router._parent_router = None
    commands.router.web_server = previous
    store.close()


async def _feed(env, update: Update) -> None:
    await env.dp.feed_update(env.bot, update)


def _pending_code(env) -> None:
    env.store.start_channel_binding(
        1, "telegram", hash_channel_code(CODE), code_expires_at=time.time() + 60
    )


@pytest.mark.asyncio
async def test_stranger_can_finish_binding_step(env):
    _pending_code(env)
    await _feed(env, _message(f"/start bind_{CODE}", STRANGER))
    row = env.store.get_channel_binding(1, "telegram")
    assert row["external_user_id"] == str(STRANGER)
    assert row["external_username"] == "ivan"
    env.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_code_gets_silence(env):
    _pending_code(env)
    await _feed(env, _message(f"/start bind_{'B' * 32}", STRANGER))
    env.answer.assert_not_awaited()
    assert env.store.get_channel_binding(1, "telegram")["external_user_id"] is None


@pytest.mark.parametrize(
    "text",
    ["/start bind_!!!", "/start bind_", "/start continue_abc", "/start", "привет", "/status"],
)
@pytest.mark.asyncio
async def test_stranger_gets_silence(env, text):
    await _feed(env, _message(text, STRANGER))
    env.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_binding_in_group_is_ignored(env):
    _pending_code(env)
    await _feed(env, _message(f"/start bind_{CODE}", STRANGER, chat_type="supergroup"))
    assert env.store.get_channel_binding(1, "telegram")["external_user_id"] is None


@pytest.mark.asyncio
async def test_binding_in_caption_is_ignored(env):
    _pending_code(env)
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)]
    await _feed(env, _message(None, STRANGER, photo=photo, caption=f"/start bind_{CODE}"))
    assert env.store.get_channel_binding(1, "telegram")["external_user_id"] is None


@pytest.mark.asyncio
async def test_bound_member_gets_login_link(env):
    await _feed(env, _message("/weblogin", TEAM))
    assert env.issued == [TEAM]


@pytest.mark.asyncio
async def test_stranger_gets_no_login_link(env):
    await _feed(env, _message("/weblogin", STRANGER))
    assert env.issued == []
    env.answer.assert_not_awaited()


@pytest.mark.parametrize(
    "text,chat_type",
    [
        ("/weblogin", "supergroup"),
        ("/weblogin@paneltestbot", "private"),
        ("/weblogin extra", "private"),
    ],
)
@pytest.mark.asyncio
async def test_member_link_only_by_exact_command_in_private(env, text, chat_type):
    await _feed(env, _message(text, TEAM, chat_type=chat_type))
    assert env.issued == []


@pytest.mark.asyncio
async def test_member_cannot_use_other_commands(env):
    await _feed(env, _message("/status", TEAM))
    await _feed(env, _message("/start continue_abc", TEAM))
    await _feed(env, _message("запусти команду", TEAM))
    env.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_whitelist_unchanged(env):
    await _feed(env, _message("/weblogin", OWNER, chat_type="supergroup"))
    assert env.issued == [OWNER]
