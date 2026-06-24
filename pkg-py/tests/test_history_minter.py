from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from shinychat._history_bookmark import BookmarkMinter
from shinychat._history_types import new_conversation_record


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
        async def restore_dir(id: str) -> Path:
            return tmp / id

        self._bookmark_restore_dir_fn = restore_dir


class FakeBookmark:
    def __init__(self, tmp: Path):
        self._tmp = tmp
        self.query_string_updates: list[str] = []

    async def get_bookmark_url(self) -> str:
        state_id = "test-state-abc"
        state_dir = self._tmp / state_id
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "values.json").write_text("{}", encoding="utf-8")
        return f"http://localhost:8000/app/?_state_id_={state_id}"

    async def update_query_string(self, query_string: str, mode: str = "replace") -> None:
        self.query_string_updates.append(query_string)


class FakeSession:
    def __init__(self, tmp: Path):
        self.bookmark = FakeBookmark(tmp)
        self.app = FakeApp(tmp)
        self.clientdata = FakeClientdata()

    def root_scope(self) -> "FakeSession":
        return self


def test_mint_if_needed_sets_state_id_and_updates_url(tmp_path: Path):
    session = FakeSession(tmp_path)
    minter = BookmarkMinter(session)  # type: ignore[arg-type]
    record = new_conversation_record(title="test")
    assert record.bookmark_state_id is None

    asyncio.run(minter.mint_if_needed(record))

    assert record.bookmark_state_id == "test-state-abc"
    assert session.bookmark.query_string_updates == ["?_state_id_=test-state-abc"]


def test_mint_if_needed_stops_state_id_at_ampersand(tmp_path: Path):
    """state_id must be extracted up to the next '&', not the end of the URL."""
    state_id = "clean-state-id"
    (tmp_path / state_id).mkdir()

    session = FakeSession(tmp_path)
    session.bookmark.get_bookmark_url = AsyncMock(  # type: ignore[method-assign]
        return_value=f"http://localhost:8000/app/?_state_id_={state_id}&other=value"
    )
    minter = BookmarkMinter(session)  # type: ignore[arg-type]
    record = new_conversation_record(title="test")

    asyncio.run(minter.mint_if_needed(record))

    assert record.bookmark_state_id == state_id
    assert session.bookmark.query_string_updates == [f"?_state_id_={state_id}"]


def test_mint_if_needed_is_noop_when_already_minted(tmp_path: Path):
    session = FakeSession(tmp_path)
    session.bookmark.get_bookmark_url = AsyncMock(return_value="http://localhost/?_state_id_=new")
    minter = BookmarkMinter(session)  # type: ignore[arg-type]
    record = new_conversation_record(title="test")
    record.bookmark_state_id = "existing-id"

    asyncio.run(minter.mint_if_needed(record))

    session.bookmark.get_bookmark_url.assert_not_called()
    assert record.bookmark_state_id == "existing-id"


def test_delete_state_removes_dir_and_tolerates_missing(tmp_path: Path):
    session = FakeSession(tmp_path)
    minter = BookmarkMinter(session)  # type: ignore[arg-type]

    state_dir = tmp_path / "some-state-id"
    state_dir.mkdir()
    asyncio.run(minter.delete_state("some-state-id"))
    assert not state_dir.exists()

    asyncio.run(minter.delete_state("never-existed"))  # must not raise


def test_delete_state_rejects_traversal(tmp_path: Path):
    """Guard must reject state_ids containing path traversal characters."""
    # Point restore_dir to a subdirectory so that "../adjacent" escapes to
    # tmp_path/adjacent — the directory we expect the guard to protect.
    target = tmp_path / "adjacent"
    target.mkdir()

    async def contained_restore_dir(id: str) -> Path:
        return tmp_path / "bookmarks" / id

    session = FakeSession(tmp_path)
    session.app._bookmark_restore_dir_fn = contained_restore_dir
    minter = BookmarkMinter(session)  # type: ignore[arg-type]

    asyncio.run(minter.delete_state("../adjacent"))

    assert target.exists(), "path-traversal state_id must not delete outside the bookmark dir"


def test_delete_state_rejects_invalid_state_ids(tmp_path: Path):
    """delete_state must silently ignore any state_id that fails CONV_ID_RE."""
    session = FakeSession(tmp_path)
    minter = BookmarkMinter(session)  # type: ignore[arg-type]

    for bad in ["", "a b", "foo/bar", ".", "..", "foo\x00bar"]:
        asyncio.run(minter.delete_state(bad))  # must not raise


def test_url_assembly(tmp_path: Path):
    minter = BookmarkMinter(FakeSession(tmp_path))  # type: ignore[arg-type]
    assert minter.base_url() == "http://localhost:8000/app/"
    assert minter.url_with_state("abc") == "http://localhost:8000/app/?_state_id_=abc"
