from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from shinychat._history_store import (
    FileConversationStore,
    InMemoryConversationStore,
    resolve_store,
    safe_conv_path,
    sanitize_scope,
)
from shinychat._history_types import new_conversation_record


@pytest.fixture
def store(tmp_path: Path) -> FileConversationStore:
    return FileConversationStore(dir=tmp_path)


@pytest.mark.anyio
async def test_put_get_round_trip(store: FileConversationStore):
    rec = new_conversation_record(title="penguins")
    rec.append_linear([{"role": "user", "content": "hi"}])
    rec.append_linear(
        [{"role": "assistant", "content": "hello"}],
        ui=[{"role": "assistant", "segments": [{"content": "hello", "content_type": "markdown"}]}],
    )
    await store.put("alice", rec)
    got = await store.get("alice", rec.id)
    assert got is not None
    assert got.id == rec.id
    assert got.title == rec.title
    assert got.next_node_seq == rec.next_node_seq
    assert got.current_leaf == rec.current_leaf
    for nid in rec.nodes:
        assert got.nodes[nid].turns == rec.nodes[nid].turns
        assert got.nodes[nid].children == rec.nodes[nid].children
        assert got.nodes[nid].parent == rec.nodes[nid].parent
        assert got.nodes[nid].ui == rec.nodes[nid].ui


@pytest.mark.anyio
async def test_put_creates_directory_with_three_files(
    store: FileConversationStore, tmp_path: Path,
):
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "hi"}])
    await store.put("alice", rec)
    scope_dir = tmp_path / sanitize_scope("alice")
    conv_dir = scope_dir / rec.id
    assert conv_dir.is_dir()
    assert (conv_dir / "record.json").is_file()
    assert (conv_dir / "turns.jsonl").is_file()
    assert (conv_dir / "ui.jsonl").is_file()


@pytest.mark.anyio
async def test_turns_jsonl_is_append_only(
    store: FileConversationStore, tmp_path: Path,
):
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}])
    rec.append_linear([{"role": "assistant", "content": "a1"}])
    await store.put("alice", rec)

    scope_dir = tmp_path / sanitize_scope("alice")
    turns_file = scope_dir / rec.id / "turns.jsonl"
    lines_after_first = turns_file.read_text().strip().splitlines()
    assert len(lines_after_first) == 2

    rec.append_linear([{"role": "user", "content": "q2"}])
    rec.append_linear([{"role": "assistant", "content": "a2"}])
    await store.put("alice", rec)

    lines_after_second = turns_file.read_text().strip().splitlines()
    assert len(lines_after_second) == 4
    # First two lines must be identical (append-only)
    assert lines_after_second[:2] == lines_after_first


@pytest.mark.anyio
async def test_ui_jsonl_is_append_only(
    store: FileConversationStore, tmp_path: Path,
):
    rec = new_conversation_record(title="t")
    rec.append_linear(
        [{"role": "user", "content": "q1"}],
        ui=[{"role": "user", "segments": []}],
    )
    await store.put("alice", rec)

    scope_dir = tmp_path / sanitize_scope("alice")
    ui_file = scope_dir / rec.id / "ui.jsonl"
    lines_after_first = ui_file.read_text().strip().splitlines()
    assert len(lines_after_first) == 1

    rec.append_linear(
        [{"role": "assistant", "content": "a1"}],
        ui=[{"role": "assistant", "segments": []}],
    )
    await store.put("alice", rec)

    lines_after_second = ui_file.read_text().strip().splitlines()
    assert len(lines_after_second) == 2
    assert lines_after_second[0] == lines_after_first[0]


@pytest.mark.anyio
async def test_cold_start_recovery(
    tmp_path: Path,
):
    store1 = FileConversationStore(dir=tmp_path)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}])
    rec.append_linear([{"role": "assistant", "content": "a1"}])
    await store1.put("alice", rec)

    # Fresh store instance (cold start) reads existing files
    store2 = FileConversationStore(dir=tmp_path)
    rec.append_linear([{"role": "user", "content": "q2"}])
    rec.append_linear([{"role": "assistant", "content": "a2"}])
    await store2.put("alice", rec)

    # Verify only new turns were appended
    scope_dir = tmp_path / sanitize_scope("alice")
    turns_file = scope_dir / rec.id / "turns.jsonl"
    lines = turns_file.read_text().strip().splitlines()
    assert len(lines) == 4
    seqs = [json.loads(line)["seq"] for line in lines]
    assert seqs == [0, 1, 2, 3]


@pytest.mark.anyio
async def test_missing_ui_jsonl_returns_nodes_with_none_ui(
    tmp_path: Path,
):
    store = FileConversationStore(dir=tmp_path)
    rec = new_conversation_record(title="t")
    rec.append_linear(
        [{"role": "user", "content": "hi"}],
        ui=[{"role": "user", "segments": []}],
    )
    await store.put("alice", rec)

    # Delete ui.jsonl
    scope_dir = tmp_path / sanitize_scope("alice")
    (scope_dir / rec.id / "ui.jsonl").unlink()

    got = await store.get("alice", rec.id)
    assert got is not None
    for node in got.nodes.values():
        assert node.ui is None


@pytest.mark.anyio
async def test_node_with_no_ui_has_no_entry_in_ui_jsonl(
    store: FileConversationStore, tmp_path: Path,
):
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}])  # no ui
    await store.put("alice", rec)

    scope_dir = tmp_path / sanitize_scope("alice")
    ui_file = scope_dir / rec.id / "ui.jsonl"
    content = ui_file.read_text().strip()
    assert content == ""


@pytest.mark.anyio
async def test_get_missing_returns_none(store: FileConversationStore):
    assert await store.get("alice", "c_nope") is None


@pytest.mark.anyio
async def test_list_is_meta_only_newest_first(store: FileConversationStore):
    a = new_conversation_record(title="older")
    b = new_conversation_record(title="newer")
    await store.put("alice", a)
    # Force b.updated_at to be strictly after a.updated_at since
    # utcnow() has second resolution and both may share the same timestamp.
    b.updated_at = b.updated_at + timedelta(seconds=1)
    await store.put("alice", b)
    metas = await store.list("alice")
    assert [m.title for m in metas] == ["newer", "older"]


@pytest.mark.anyio
async def test_scopes_are_isolated(store: FileConversationStore):
    rec = new_conversation_record(title="private")
    await store.put("alice", rec)
    assert await store.list("bob") == []
    assert await store.get("bob", rec.id) is None


@pytest.mark.anyio
async def test_delete(store: FileConversationStore):
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)
    await store.delete("alice", rec.id)
    assert await store.list("alice") == []
    # deleting again is a no-op, not an error
    await store.delete("alice", rec.id)


@pytest.mark.anyio
async def test_default_search_is_substring_over_titles(
    store: FileConversationStore,
):
    a = new_conversation_record(title="Q1 churn analysis")
    b = new_conversation_record(title="Penguin bills")
    await store.put("alice", a)
    await store.put("alice", b)
    hits = await store.search("alice", "CHURN")
    assert [m.id for m in hits] == [a.id]


def test_sanitize_scope_is_filesystem_safe_and_stable():
    s1 = sanitize_scope("alice@example.com/../etc")
    assert "/" not in s1 and ".." not in s1
    assert s1 == sanitize_scope("alice@example.com/../etc")
    assert sanitize_scope("alice") != sanitize_scope("bob")


@pytest.mark.anyio
async def test_put_is_atomic_no_partial_files(
    store: FileConversationStore, tmp_path: Path
):
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)
    scope_dir = tmp_path / sanitize_scope("alice")
    conv_dir = scope_dir / rec.id
    assert conv_dir.is_dir()
    files = {f.name for f in conv_dir.iterdir()}
    assert files == {"record.json", "turns.jsonl", "ui.jsonl"}


def test_safe_conv_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        safe_conv_path(tmp_path, "../escape")


def test_safe_conv_path_rejects_slash(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        safe_conv_path(tmp_path, "foo/bar")


def test_safe_conv_path_accepts_valid_id(tmp_path: Path):
    result = safe_conv_path(tmp_path, "c_abc123-XYZ_456")
    assert result == tmp_path / "c_abc123-XYZ_456"


@pytest.mark.anyio
async def test_get_with_traversal_id_raises(store: FileConversationStore):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        await store.get("alice", "../escape")


@pytest.mark.anyio
async def test_delete_with_traversal_id_raises(store: FileConversationStore):
    with pytest.raises(ValueError, match="Invalid conversation id"):
        await store.delete("alice", "../escape")


# ---------------------------------------------------------------------------
# FileConversationStore — meta cache
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_populates_cache(store: FileConversationStore):
    rec = new_conversation_record(title="cached")
    await store.put("alice", rec)
    assert "alice" not in store._meta_cache  # put to cold scope: no cache
    await store.list("alice")
    assert "alice" in store._meta_cache
    assert store._meta_cache["alice"][0].id == rec.id


@pytest.mark.anyio
async def test_list_returns_from_cache_without_disk_read(
    store: FileConversationStore, tmp_path: Path
):
    rec = new_conversation_record(title="cached")
    await store.put("alice", rec)
    await store.list("alice")  # warms cache

    # Delete the conversation directory underneath — cache should still serve
    scope_dir = tmp_path / sanitize_scope("alice")
    for d in scope_dir.iterdir():
        if d.is_dir():
            shutil.rmtree(d)

    metas = await store.list("alice")
    assert len(metas) == 1
    assert metas[0].id == rec.id


@pytest.mark.anyio
async def test_get_missing_after_cached_list_invalidates_cache(
    store: FileConversationStore, tmp_path: Path
):
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)
    await store.list("alice")  # warms cache
    assert "alice" in store._meta_cache

    # Simulate another worker deleting the conversation directly on disk
    scope_dir = tmp_path / sanitize_scope("alice")
    for d in scope_dir.iterdir():
        if d.is_dir():
            shutil.rmtree(d)

    got = await store.get("alice", rec.id)
    assert got is None
    assert "alice" not in store._meta_cache

    metas = await store.list("alice")
    assert metas == []


@pytest.mark.anyio
async def test_put_updates_warm_cache(store: FileConversationStore):
    a = new_conversation_record(title="first")
    await store.put("alice", a)
    await store.list("alice")  # warm

    b = new_conversation_record(title="second")
    await store.put("alice", b)

    cached = store._meta_cache["alice"]
    assert {m.id for m in cached} == {a.id, b.id}


@pytest.mark.anyio
async def test_put_does_not_create_cache_for_cold_scope(
    store: FileConversationStore,
):
    rec = new_conversation_record(title="cold")
    await store.put("alice", rec)
    assert "alice" not in store._meta_cache


@pytest.mark.anyio
async def test_delete_updates_warm_cache(store: FileConversationStore):
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)
    await store.list("alice")  # warm
    await store.delete("alice", rec.id)

    assert store._meta_cache["alice"] == []


@pytest.mark.anyio
async def test_list_returns_independent_copy(store: FileConversationStore):
    rec = new_conversation_record(title="t")
    await store.put("alice", rec)
    result = await store.list("alice")
    result.clear()
    assert len(store._meta_cache["alice"]) == 1


# ---------------------------------------------------------------------------
# InMemoryConversationStore
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_store() -> InMemoryConversationStore:
    return InMemoryConversationStore()


@pytest.mark.anyio
async def test_memory_put_get_round_trip(mem_store: InMemoryConversationStore):
    rec = new_conversation_record(title="penguins")
    rec.append_linear([{"role": "user", "content": "hi"}])
    await mem_store.put("alice", rec)
    got = await mem_store.get("alice", rec.id)
    assert got == rec


@pytest.mark.anyio
async def test_memory_get_missing_returns_none(
    mem_store: InMemoryConversationStore,
):
    assert await mem_store.get("alice", "c_nope") is None


@pytest.mark.anyio
async def test_memory_list_newest_first(mem_store: InMemoryConversationStore):
    a = new_conversation_record(title="older")
    b = new_conversation_record(title="newer")
    await mem_store.put("alice", a)
    b.updated_at = b.updated_at + timedelta(seconds=1)
    await mem_store.put("alice", b)
    metas = await mem_store.list("alice")
    assert [m.title for m in metas] == ["newer", "older"]


@pytest.mark.anyio
async def test_memory_scopes_are_isolated(mem_store: InMemoryConversationStore):
    rec = new_conversation_record(title="private")
    await mem_store.put("alice", rec)
    assert await mem_store.list("bob") == []
    assert await mem_store.get("bob", rec.id) is None


@pytest.mark.anyio
async def test_memory_delete(mem_store: InMemoryConversationStore):
    rec = new_conversation_record(title="t")
    await mem_store.put("alice", rec)
    await mem_store.delete("alice", rec.id)
    assert await mem_store.list("alice") == []
    await mem_store.delete("alice", rec.id)  # no-op


@pytest.mark.anyio
async def test_memory_search(mem_store: InMemoryConversationStore):
    a = new_conversation_record(title="Q1 churn analysis")
    b = new_conversation_record(title="Penguin bills")
    await mem_store.put("alice", a)
    await mem_store.put("alice", b)
    hits = await mem_store.search("alice", "CHURN")
    assert [m.id for m in hits] == [a.id]


# ---------------------------------------------------------------------------
# resolve_store
# ---------------------------------------------------------------------------


def test_resolve_store_memory_returns_in_memory_store():
    assert isinstance(resolve_store("memory"), InMemoryConversationStore)


def test_resolve_store_file_returns_file_store():
    assert isinstance(resolve_store("file"), FileConversationStore)


def test_resolve_store_auto_dev_mode_returns_in_memory(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINY_DEV_MODE", "1")
    assert isinstance(resolve_store("auto"), InMemoryConversationStore)


def test_resolve_store_auto_no_dev_mode_returns_file(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("SHINY_DEV_MODE", raising=False)
    assert isinstance(resolve_store("auto"), FileConversationStore)


def test_resolve_store_passthrough_custom_store(
    mem_store: InMemoryConversationStore,
):
    assert resolve_store(mem_store) is mem_store


# ---------------------------------------------------------------------------
# total_size
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_file_store_total_size_zero_for_missing_scope(tmp_path: Path):
    store = FileConversationStore(dir=tmp_path)
    assert await store.total_size("alice") == 0


@pytest.mark.anyio
async def test_file_store_total_size_grows_with_put(tmp_path: Path):
    store = FileConversationStore(dir=tmp_path)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "hello world"}])
    await store.put("alice", rec)
    size1 = await store.total_size("alice")
    assert size1 > 0

    rec2 = new_conversation_record(title="t2")
    await store.put("alice", rec2)
    assert await store.total_size("alice") > size1


@pytest.mark.anyio
async def test_file_store_total_size_shrinks_with_delete(tmp_path: Path):
    store = FileConversationStore(dir=tmp_path)
    rec1 = new_conversation_record(title="a")
    rec2 = new_conversation_record(title="b")
    await store.put("alice", rec1)
    await store.put("alice", rec2)
    total = await store.total_size("alice")
    await store.delete("alice", rec1.id)
    assert await store.total_size("alice") < total


@pytest.mark.anyio
async def test_memory_total_size_zero_for_missing_scope(
    mem_store: InMemoryConversationStore,
):
    assert await mem_store.total_size("alice") == 0


@pytest.mark.anyio
async def test_memory_total_size_grows_with_put(
    mem_store: InMemoryConversationStore,
):
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "hello world"}])
    await mem_store.put("alice", rec)
    size1 = await mem_store.total_size("alice")
    assert size1 > 0

    rec2 = new_conversation_record(title="t2")
    await mem_store.put("alice", rec2)
    assert await mem_store.total_size("alice") > size1


@pytest.mark.anyio
async def test_memory_total_size_shrinks_with_delete(
    mem_store: InMemoryConversationStore,
):
    rec1 = new_conversation_record(title="a")
    rec2 = new_conversation_record(title="b")
    await mem_store.put("alice", rec1)
    await mem_store.put("alice", rec2)
    total = await mem_store.total_size("alice")
    await mem_store.delete("alice", rec1.id)
    assert await mem_store.total_size("alice") < total
