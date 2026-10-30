"""У43-01: без джейла bwrap ограниченная сессия запускается только для чтения.

Файрвол инструментов обходится двумя шагами (Write скрипта в проект, Bash
python3 файл.py), поэтому пока bwrap недоступен и ``require_jail`` выключен,
relay сам выставляет ``readonly`` и предупреждает человека в ленте.
"""
from __future__ import annotations

import unittest

from src.claude.bridge import ClaudeEvent, ClaudeEventType
from src.event_bus import ClaudeEventRelay, EventBus
from src.event_bus.claude import JAIL_FALLBACK_READONLY_MESSAGE
from src.event_bus.events import AgentStreamingUpdate, UserMessageReceived


class _Bridge:
    def __init__(self, *, jail: bool, require_jail: bool = False) -> None:
        self.jail = jail
        self.require_jail = require_jail
        self.calls: list[dict] = []

    def _jail_available(self) -> bool:
        return self.jail

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        yield ClaudeEvent(ClaudeEventType.COMPLETE, metadata={"usage": {}, "session_id": "s"})


class _BareBridge:
    """Заглушка без пробы джейла: поведение не меняется."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        yield ClaudeEvent(ClaudeEventType.COMPLETE, metadata={"usage": {}, "session_id": "s"})


class RelayJailReadonlyTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, bridge, *, confine_root, readonly=False) -> list[AgentStreamingUpdate]:
        bus = EventBus()
        updates: list[AgentStreamingUpdate] = []

        async def collect(ev: AgentStreamingUpdate) -> None:
            updates.append(ev)

        bus.subscribe(AgentStreamingUpdate, collect)
        relay = ClaudeEventRelay(bus=bus, claude_bridge=bridge)
        await bus.publish(
            UserMessageReceived(
                request_id="r1", chat_id=1, user_id=1, topic_id=1, project_path="/p",
                text="hi", session_uuid="s1", readonly=readonly, confine_root=confine_root,
            )
        )
        relay.close()
        return updates

    async def test_confined_without_jail_becomes_readonly_and_warns(self) -> None:
        bridge = _Bridge(jail=False)
        updates = await self._run(bridge, confine_root="/p")
        self.assertTrue(bridge.calls[0]["readonly"])
        logs = [u.content for u in updates if u.kind == "log"]
        self.assertEqual(logs, [JAIL_FALLBACK_READONLY_MESSAGE])

    async def test_confined_with_jail_keeps_full_access(self) -> None:
        bridge = _Bridge(jail=True)
        updates = await self._run(bridge, confine_root="/p")
        self.assertFalse(bridge.calls[0]["readonly"])
        self.assertEqual([u for u in updates if u.kind == "log"], [])

    async def test_privileged_session_is_untouched(self) -> None:
        bridge = _Bridge(jail=False)
        await self._run(bridge, confine_root=None)
        self.assertFalse(bridge.calls[0]["readonly"])

    async def test_require_jail_leaves_refusal_to_bridge(self) -> None:
        bridge = _Bridge(jail=False, require_jail=True)
        await self._run(bridge, confine_root="/p")
        self.assertFalse(bridge.calls[0]["readonly"])

    async def test_bridge_without_probe_is_unchanged(self) -> None:
        bridge = _BareBridge()
        await self._run(bridge, confine_root="/p")
        self.assertFalse(bridge.calls[0]["readonly"])
