from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from shinychat._history_bridge import BookmarkBridge, BookmarkMinter


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


# ---------------------------------------------------------------------------
# BookmarkMinter tests
# ---------------------------------------------------------------------------


class FakeInput:
    async def _serialize(self, *, exclude: list[str], state_dir: Any) -> dict[str, Any]:
        return {"some_input": 1}


class FakeClientdata:
    def url_protocol(self) -> str:
        return "http:"

    def url_hostname(self) -> str:
        return "localhost"

    def url_port(self) -> int:
        return 8000

    def url_pathname(self) -> str:
        return "/app/"


class FakeApp:
    def __init__(self, tmp: Path):
        self._tmp = tmp

        async def save_dir(id: str) -> Path:
            d = tmp / id
            d.mkdir(parents=True, exist_ok=True)
            return d

        async def restore_dir(id: str) -> Path:
            return tmp / id

        self._bookmark_save_dir_fn = save_dir
        self._bookmark_restore_dir_fn = restore_dir


class FakeMinterBookmark(FakeBookmark):
    def __init__(self):
        super().__init__()
        self.query_string_updates: list[str] = []

    def _get_bookmark_exclude(self) -> list[str]:
        return []

    async def update_query_string(self, query_string: str, mode: str = "replace") -> None:
        self.query_string_updates.append(query_string)


class FakeMinterSession(FakeSession):
    def __init__(self, tmp: Path):
        super().__init__()
        self.bookmark = FakeMinterBookmark()
        self.app = FakeApp(tmp)
        self.input = FakeInput()
        self.clientdata = FakeClientdata()


def test_mint_saves_state_and_returns_id_and_filtered_values(tmp_path: Path):
    session = FakeMinterSession(tmp_path)

    def on_bookmark(state: Any):
        state.values["app_filter"] = "penguins"
        state.values["chat--msgs"] = []

    session.bookmark._on_bookmark_callbacks.register(on_bookmark)
    minter = BookmarkMinter(session, exclude_keys={"chat", "chat--msgs"})

    state_id, values = asyncio.run(minter.mint())

    assert values == {"app_filter": "penguins"}
    state_dir = tmp_path / state_id
    assert (state_dir / "input.json").is_file()
    assert (state_dir / "values.json").is_file()


def test_delete_state_removes_dir_and_tolerates_missing(tmp_path: Path):
    session = FakeMinterSession(tmp_path)
    minter = BookmarkMinter(session, exclude_keys=set())

    state_id, _ = asyncio.run(minter.mint())
    assert (tmp_path / state_id).is_dir()
    asyncio.run(minter.delete_state(state_id))
    assert not (tmp_path / state_id).exists()

    asyncio.run(minter.delete_state("never-existed"))  # must not raise


def test_url_assembly(tmp_path: Path):
    minter = BookmarkMinter(FakeMinterSession(tmp_path), exclude_keys=set())
    assert minter.base_url() == "http://localhost:8000/app/"
    assert (
        minter.url_with_state("abc")
        == "http://localhost:8000/app/?_state_id_=abc"
    )


def test_update_query_string_sends_query_form(tmp_path: Path):
    session = FakeMinterSession(tmp_path)
    minter = BookmarkMinter(session, exclude_keys=set())
    asyncio.run(minter.update_query_string("abc"))
    assert session.bookmark.query_string_updates == ["?_state_id_=abc"]
