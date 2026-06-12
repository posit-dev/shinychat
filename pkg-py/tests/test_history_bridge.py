from __future__ import annotations

import asyncio
from typing import Any

from shinychat._history_bridge import BookmarkBridge


class FakeCallbacks:
    """Mimics shiny._utils.AsyncCallbacks enough for the bridge."""

    def __init__(self):
        self._fns: list[Any] = []

    def register(self, fn: Any):
        self._fns.append(fn)

    def count(self) -> int:
        return len(self._fns)

    async def invoke(self, arg: Any) -> None:
        for fn in self._fns:
            res = fn(arg)
            if hasattr(res, "__await__"):
                await res


class FakeBookmark:
    def __init__(self):
        self._on_bookmark_callbacks = FakeCallbacks()
        self._on_restore_callbacks = FakeCallbacks()
        self._on_restored_callbacks = FakeCallbacks()


class FakeSession:
    def __init__(self):
        self.bookmark = FakeBookmark()
        self.input = {}

    def root_scope(self):
        return self


def test_capture_collects_values_and_excludes_chat_keys():
    session = FakeSession()

    def on_bookmark(state: Any):
        state.values["querychat_sql"] = "SELECT 1"
        state.values["chat"] = {"turns": []}
        state.values["chat--msgs"] = []

    session.bookmark._on_bookmark_callbacks.register(on_bookmark)
    bridge = BookmarkBridge(session, exclude_keys={"chat", "chat--msgs"})
    values = asyncio.run(bridge.capture())
    assert values == {"querychat_sql": "SELECT 1"}


def test_restore_invokes_on_restore_and_on_restored_with_values():
    session = FakeSession()
    seen: dict[str, Any] = {}
    restored_seen: dict[str, Any] = {}

    def on_restore(state: Any):
        seen.update(state.values)

    def on_restored(state: Any):
        restored_seen.update(state.values)

    session.bookmark._on_restore_callbacks.register(on_restore)
    session.bookmark._on_restored_callbacks.register(on_restored)
    bridge = BookmarkBridge(session, exclude_keys=set())
    asyncio.run(bridge.restore({"querychat_sql": None}))
    assert seen == {"querychat_sql": None}
    assert restored_seen == {"querychat_sql": None}


def test_capture_with_no_callbacks_is_empty():
    bridge = BookmarkBridge(FakeSession(), exclude_keys=set())
    assert asyncio.run(bridge.capture()) == {}


def test_restore_with_no_callbacks_is_noop():
    bridge = BookmarkBridge(FakeSession(), exclude_keys=set())
    asyncio.run(bridge.restore({"x": 1}))  # must not raise


def test_restore_on_restored_only_is_invoked():
    session = FakeSession()
    restored_seen: dict[str, Any] = {}

    def on_restored(state: Any):
        restored_seen.update(state.values)

    session.bookmark._on_restored_callbacks.register(on_restored)
    bridge = BookmarkBridge(session, exclude_keys=set())
    asyncio.run(bridge.restore({"k": "v"}))
    assert restored_seen == {"k": "v"}
