from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from shinychat._history_store import (
    FileConversationStore,
    safe_conv_path,
    sanitize_scope,
)
from shinychat._history_types import new_conversation_record


@pytest.fixture
def store(tmp_path: Path) -> FileConversationStore:
    return FileConversationStore(dir=tmp_path)


def test_put_get_round_trip(store: FileConversationStore):
    async def _run() -> None:
        rec = new_conversation_record(title="penguins")
        rec.append_linear({"role": "user", "content": "hi"})
        await store.put("alice", rec)
        got = await store.get("alice", rec.id)
        assert got == rec

    asyncio.run(_run())


def test_get_missing_returns_none(store: FileConversationStore):
    async def _run() -> None:
        assert await store.get("alice", "c_nope") is None

    asyncio.run(_run())


def test_list_is_meta_only_newest_first(store: FileConversationStore):
    async def _run() -> None:
        a = new_conversation_record(title="older")
        b = new_conversation_record(title="newer")
        await store.put("alice", a)
        # Force b.updated_at to be strictly after a.updated_at since
        # utcnow() has second resolution and both may share the same timestamp.
        b.updated_at = b.updated_at + timedelta(seconds=1)
        await store.put("alice", b)
        metas = await store.list("alice")
        assert [m.title for m in metas] == ["newer", "older"]

    asyncio.run(_run())


def test_scopes_are_isolated(store: FileConversationStore):
    async def _run() -> None:
        rec = new_conversation_record(title="private")
        await store.put("alice", rec)
        assert await store.list("bob") == []
        assert await store.get("bob", rec.id) is None

    asyncio.run(_run())


def test_delete(store: FileConversationStore):
    async def _run() -> None:
        rec = new_conversation_record(title="t")
        await store.put("alice", rec)
        await store.delete("alice", rec.id)
        assert await store.list("alice") == []
        # deleting again is a no-op, not an error
        await store.delete("alice", rec.id)

    asyncio.run(_run())


def test_default_search_is_substring_over_titles(store: FileConversationStore):
    async def _run() -> None:
        a = new_conversation_record(title="Q1 churn analysis")
        b = new_conversation_record(title="Penguin bills")
        await store.put("alice", a)
        await store.put("alice", b)
        hits = await store.search("alice", "CHURN")
        assert [m.id for m in hits] == [a.id]

    asyncio.run(_run())


def test_sanitize_scope_is_filesystem_safe_and_stable():
    s1 = sanitize_scope("alice@example.com/../etc")
    assert "/" not in s1 and ".." not in s1
    assert s1 == sanitize_scope("alice@example.com/../etc")
    assert sanitize_scope("alice") != sanitize_scope("bob")


def test_put_is_atomic_no_partial_files(
    store: FileConversationStore, tmp_path: Path
):
    async def _run() -> None:
        rec = new_conversation_record(title="t")
        await store.put("alice", rec)
        files = list((tmp_path / sanitize_scope("alice")).iterdir())
        assert {f.name for f in files} == {
            f"{rec.id}.json"
        }  # no .tmp leftovers

    asyncio.run(_run())


def test_safe_conv_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        safe_conv_path(tmp_path, "../escape")


def test_safe_conv_path_rejects_slash(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        safe_conv_path(tmp_path, "foo/bar")


def test_safe_conv_path_accepts_valid_id(tmp_path: Path):
    result = safe_conv_path(tmp_path, "c_abc123-XYZ_456")
    assert result == tmp_path / "c_abc123-XYZ_456.json"


def test_get_with_traversal_id_raises(store: FileConversationStore):
    async def _run() -> None:
        with pytest.raises(ValueError, match="Invalid conversation id"):
            await store.get("alice", "../escape")

    asyncio.run(_run())


def test_delete_with_traversal_id_raises(store: FileConversationStore):
    async def _run() -> None:
        with pytest.raises(ValueError, match="Invalid conversation id"):
            await store.delete("alice", "../escape")

    asyncio.run(_run())
