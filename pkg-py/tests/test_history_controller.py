# HistoryController's session-coupled behavior (switch_to, on_response, etc.)
# is covered by Playwright e2e tests (Task 13). This file tests the pure
# helpers that HistoryController delegates to.

import warnings
from datetime import timedelta
from typing import Any, Callable, cast
from unittest.mock import AsyncMock

import pytest
from _history_test_helpers import branch_from
from shinychat._history import (
    HistoryController,
    do_bookmark_with_cleanup,
    extend_record_linear,
)
from shinychat._history_client import TurnDict
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    MAX_SCHEMA_VERSION,
    STORED_UI_VERSION,
    ConversationRecord,
    UnsupportedSchemaVersionError,
    new_conversation_record,
)


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def derived(role: str, content: str) -> dict[str, object]:
    """The stored UI message a plain-text turn group derives to."""
    return {
        "role": role,
        "segments": [{"content": content, "content_type": "markdown"}],
        "version": STORED_UI_VERSION,
    }


def chatlas_tool_group() -> list[Any]:
    """A serialized chatlas tool-call exchange (request, result, final text),
    round-tripped through JSON dicts exactly as the history store persists
    them."""
    from chatlas import Turn
    from chatlas.types import (
        ContentText,
        ContentToolRequest,
        ContentToolResult,
    )
    from shinychat._chat_bookmark import serialize_chatlas_turn

    req = ContentToolRequest(
        id="x", name="get_weather", arguments={"city": "Duluth"}
    )
    res = ContentToolResult(value="Sunny", request=req)
    turns = [
        Turn(role="assistant", contents=[req]),
        Turn(role="user", contents=[res]),
        Turn(role="assistant", contents=[ContentText(text="It's sunny.")]),
    ]
    return [serialize_chatlas_turn(t) for t in turns]


def part(
    *, chat_id: str = "chat", scope: str = "test-scope"
) -> ConversationPartition:
    return ConversationPartition(chat_id=chat_id, scope=scope)


def test_extend_appends_only_new_groups_with_ui_by_role():
    rec = new_conversation_record(title="t")
    groups: list[list[TurnDict]] = [
        [{"role": "user", "content": "q1"}],
        [{"role": "assistant", "content": "a1"}],
    ]
    extend_record_linear(
        rec, groups, [msg("user"), msg("assistant")], ui_offset=0
    )
    assert len(rec.nodes) == 2
    path = rec.path_node_ids()
    assert rec.nodes[path[0]].turns == [{"role": "user", "content": "q1"}]
    assert rec.nodes[path[0]].ui == [derived("user", "q1")]
    assert rec.nodes[path[1]].ui == [derived("assistant", "a1")]

    groups.extend(
        [
            [{"role": "user", "content": "q2"}],
            [{"role": "assistant", "content": "a2"}],
        ]
    )
    all_msgs = [msg("user"), msg("assistant"), msg("user"), msg("assistant")]
    extend_record_linear(rec, groups, all_msgs, ui_offset=2)
    assert len(rec.nodes) == 4
    assert rec.nodes[rec.path_node_ids()[2]].ui == [derived("user", "q2")]


def test_extend_groups_tool_exchange_into_single_node():
    user_turn: TurnDict = {
        "role": "user",
        "contents": [{"content_type": "text", "text": "weather?"}],
    }
    tool_group = chatlas_tool_group()
    asst_req, user_res, asst_final = tool_group

    groups: list[list[TurnDict]] = [
        [user_turn],
        tool_group,
    ]
    msgs = [msg("user"), msg("assistant")]
    rec = new_conversation_record(title="t")
    extend_record_linear(rec, groups, msgs, ui_offset=0)

    assert len(rec.nodes) == 2
    path = rec.path_node_ids()

    user_node = rec.nodes[path[0]]
    asst_node = rec.nodes[path[1]]

    assert len(user_node.turns) == 1
    assert len(asst_node.turns) == 3
    assert user_node.ui == [derived("user", "weather?")]

    assert asst_node.ui is not None and len(asst_node.ui) == 1
    asst_ui = asst_node.ui[0]
    assert asst_ui["version"] == STORED_UI_VERSION
    assert asst_ui["role"] == "assistant"
    block_types = [s["type"] for s in asst_ui["segments"] if "type" in s]
    assert block_types == ["tool_request", "tool_result"]
    assert asst_ui["segments"][0]["request_id"] == "x"
    assert asst_ui["segments"][1]["value"] == "Sunny"
    assert asst_ui["segments"][2] == {
        "content": "It's sunny.",
        "content_type": "markdown",
    }

    assert rec.path_turns() == [user_turn, asst_req, user_res, asst_final]


def test_extend_attaches_extra_assistant_msgs_to_last_node():
    rec = new_conversation_record(title="t")
    groups: list[list[TurnDict]] = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    oob_ui = msg("assistant")
    msgs = [
        msg("user"),
        msg("assistant"),
        oob_ui,
    ]
    extend_record_linear(rec, groups, msgs, ui_offset=0)
    path = rec.path_node_ids()
    assert rec.nodes[path[1]].ui == [derived("assistant", "a"), oob_ui]


def test_extend_attaches_late_ui_message_when_turn_groups_already_caught_up():
    rec = new_conversation_record(title="t")
    groups: list[list[TurnDict]] = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    user_ui = msg("user")
    oob_ui = msg("assistant")
    streamed_ui = msg("assistant")

    # Save #1: two new turn groups, two UI messages.
    extend_record_linear(rec, groups, [user_ui, oob_ui], ui_offset=0)
    assert len(rec.nodes) == 2

    # Save #2: same turn groups (streaming added no new turn), but one more
    # UI message has arrived since the last save.
    extend_record_linear(
        rec, groups, [user_ui, oob_ui, streamed_ui], ui_offset=2
    )

    all_ui = [
        m
        for node_id in rec.path_node_ids()
        for m in (rec.nodes[node_id].ui or [])
    ]
    assert all_ui == [
        derived("user", "q"),
        derived("assistant", "a"),
        streamed_ui,
    ]


def test_extend_noop_when_no_new_groups():
    rec = new_conversation_record(title="t")
    groups: list[list[TurnDict]] = [[{"role": "user", "content": "q"}]]
    extend_record_linear(rec, groups, [msg("user")], ui_offset=0)
    before = rec.model_dump()
    extend_record_linear(rec, groups, [msg("user")], ui_offset=1)
    assert rec.model_dump() == before


def test_extend_derives_ui_even_without_client_messages():
    rec = new_conversation_record(title="t")
    groups: list[list[TurnDict]] = [
        [{"role": "user", "content": "q"}],
        [{"role": "assistant", "content": "a"}],
    ]
    extend_record_linear(rec, groups, [], ui_offset=0)
    assert len(rec.nodes) == 2
    path = rec.path_node_ids()
    assert rec.nodes[path[0]].ui == [derived("user", "q")]
    assert rec.nodes[path[1]].ui == [derived("assistant", "a")]


# --- content-idempotent save guard (unit-level, no Shiny session needed) ----


class _FakeChat:
    def __init__(self) -> None:
        self.set_greeting_calls: list[Any] = []
        self._session = None

    def _messages_for_bookmark(self) -> list[Any]:
        return []

    async def _send_action(self, action: Any) -> None:
        pass

    async def clear_messages(self) -> None:
        pass

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        pass

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)


class _FakeAdapter:
    def get_turns_json(self) -> list[Any]:
        return [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.get_turns_json()]

    def set_turns_json(self, turns: list[Any]) -> None:
        pass

    def client_info(self) -> dict[str, Any]:
        return {}


class _RecordingStore(ConversationStore):
    def __init__(self) -> None:
        self.put_calls: list[tuple[ConversationPartition, Any]] = []

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        self.put_calls.append((partition, record))

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        return None

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


class _FailingStore(_RecordingStore):
    async def put(self, partition: ConversationPartition, record: Any) -> None:
        raise OSError("disk full")


class _PartitionCaptureStore(ConversationStore):
    def __init__(self) -> None:
        self.put_partitions: list[ConversationPartition] = []
        self.records: dict[str, ConversationRecord] = {}

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        return self.records.get(conv_id)

    async def put(
        self, partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        self.put_partitions.append(partition)
        self.records[record.id] = record

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.records.pop(conv_id, None)


def _make_controller(
    store: ConversationStore | None = None,
    save_callbacks: list[Callable[[dict[str, Any]], None]] | None = None,
) -> tuple[HistoryController, Any]:
    resolved_store = store if store is not None else _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=resolved_store,
        title_fn=None,
        title_enabled=False,
        client=None,
        save_callbacks=save_callbacks,
    )
    controller.partition = part()
    return controller, resolved_store


@pytest.mark.anyio
async def test_replay_ui_clears_greeting():
    controller, _store = _make_controller()
    record = new_conversation_record(title="t")

    await controller.replay_ui(record)

    fake_chat = cast(Any, controller.chat)
    assert fake_chat.set_greeting_calls == [None]


@pytest.mark.anyio
async def test_notify_settled_calls_on_settled_hook():
    controller, _store = _make_controller()
    calls: list[bool] = []

    async def _on_settled(restored: bool) -> None:
        calls.append(restored)

    controller.on_settled = _on_settled
    await controller.notify_settled(True)
    await controller.notify_settled(False)

    assert calls == [True, False]


@pytest.mark.anyio
async def test_notify_settled_no_op_when_hook_unset():
    controller, _store = _make_controller()
    # Must not raise when nothing has registered a hook.
    await controller.notify_settled(True)


@pytest.mark.anyio
async def test_new_chat_notifies_settled_false():
    controller, _store = _make_controller()
    calls: list[bool] = []

    async def _on_settled(restored: bool) -> None:
        calls.append(restored)

    controller.on_settled = _on_settled
    await controller.new_chat()

    assert calls == [False]


@pytest.mark.anyio
async def test_controller_passes_partition_to_custom_store():
    store = _PartitionCaptureStore()
    controller, _store = _make_controller(store=store)
    controller.partition = ConversationPartition(
        chat_id="ns-chat", scope="browser-1"
    )

    await controller.on_response()

    assert store.put_partitions == [
        ConversationPartition(chat_id="ns-chat", scope="browser-1")
    ]


@pytest.mark.anyio
async def test_same_scope_different_chat_ids_are_isolated():
    store = InMemoryConversationStore()

    controller_a, _store_a = _make_controller(store=store)
    controller_a.partition = ConversationPartition(
        chat_id="chat-a", scope="browser-1"
    )
    await controller_a.on_response()
    assert controller_a.record is not None

    controller_b, _store_b = _make_controller(store=store)
    controller_b.partition = ConversationPartition(
        chat_id="chat-b", scope="browser-1"
    )

    assert (
        await store.get(controller_a.partition, controller_a.record.id)
        is not None
    )
    assert (
        await store.get(controller_b.partition, controller_a.record.id) is None
    )
    assert await store.list(controller_b.partition) == []


@pytest.mark.anyio
async def test_namespaced_chat_ids_are_distinct_partitions():
    store = InMemoryConversationStore()
    ns1 = ConversationPartition(chat_id="mod1-chat", scope="browser-1")
    ns2 = ConversationPartition(chat_id="mod2-chat", scope="browser-1")
    rec = new_conversation_record(title="module one")

    await store.put(ns1, rec)

    assert await store.get(ns1, rec.id) is rec
    assert await store.get(ns2, rec.id) is None


@pytest.mark.anyio
async def test_on_response_no_new_data_does_not_overwrite_saved_values():
    controller, store = _make_controller()
    accent = "info"

    controller._save_callbacks.append(
        lambda values: values.update({"accent": accent})
    )

    await controller.on_response()
    assert controller.record is not None
    assert controller.record.values["accent"] == "info"

    accent = "danger"
    await controller.on_response()

    assert len(store.put_calls) == 1, "no-op flush should not persist again"
    assert controller.record.values["accent"] == "info"


class _ReplayFakeChat(_FakeChat):
    """Fake chat whose `_messages_for_bookmark()` reflects whatever
    `replay_ui` last restored, so `on_response` sees the same re-report a
    real client would send after a restore."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[Any] = []

    def _messages_for_bookmark(self) -> list[Any]:
        return self.messages

    async def clear_messages(self) -> None:
        self.messages = []

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        self.messages.append(message_dict)


@pytest.mark.anyio
async def test_replay_rereport_does_not_resave_or_truncate():
    # Simulates the real restore sequence: on_response() saves a
    # conversation with per-node UI, replay_ui() restores it (re-rendering
    # the stored UI into the fake chat), and the client's post-restore
    # re-report of that identical snapshot must not trigger another save.
    controller, store = _make_controller()
    chat = _ReplayFakeChat()
    controller.chat = chat  # type: ignore[assignment]

    chat.messages = [msg("user"), msg("assistant")]
    await controller.on_response()
    assert len(store.put_calls) == 1
    record = controller.record
    assert record is not None
    saved_node_count = len(record.path_node_ids())
    saved_ui = [
        m
        for nid in record.path_node_ids()
        for m in (record.nodes[nid].ui or [])
    ]

    await controller.replay_ui(record)
    assert chat.messages == saved_ui, "replay must reconstruct the full UI"

    # Client re-reports the exact restored snapshot (same length/content).
    await controller.on_response()

    assert len(store.put_calls) == 1, "re-report must not trigger another save"
    assert controller.record is record, (
        "restore re-report must not swap records"
    )
    assert len(record.path_node_ids()) == saved_node_count, (
        "restored conversation must not be truncated"
    )


@pytest.mark.anyio
async def test_replay_rereport_then_new_turn_does_not_duplicate_ui():
    store = _RecordingStore()
    chat = _ReplayFakeChat()
    adapter = _GrowingFakeAdapter()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    adapter.turns = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    chat.messages = [msg("user"), msg("assistant")]
    await controller.on_response()
    assert len(store.put_calls) == 1
    record = controller.record
    assert record is not None
    saved_ui = [
        m
        for nid in record.path_node_ids()
        for m in (record.nodes[nid].ui or [])
    ]
    assert len(saved_ui) == 2
    assert controller.ui_offset == 2

    await controller.replay_ui(record)
    assert chat.messages == saved_ui, "replay must reconstruct the full UI"
    controller.ui_offset = 0
    await controller.on_response()
    assert len(store.put_calls) == 1, "re-report must not trigger another save"
    assert controller.ui_offset == 2, (
        "ui_offset must advance past the re-reported snapshot"
    )

    chat.messages = [msg("user")]
    await controller.on_response()
    assert len(store.put_calls) == 1
    assert controller.ui_offset == 2, "partial report must not rewind ui_offset"

    adapter.turns += [
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    chat.messages = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]
    await controller.on_response()
    assert len(store.put_calls) == 2

    all_ui = [
        m
        for nid in record.path_node_ids()
        for m in (record.nodes[nid].ui or [])
    ]
    assert len(all_ui) == 4, (
        f"expected 4 stored UI messages, got {len(all_ui)}: {all_ui}"
    )
    assert all_ui == [
        derived("user", "q1"),
        derived("assistant", "a1"),
        derived("user", "q2"),
        derived("assistant", "a2"),
    ]


# --- ui_offset atomicity (not advanced when store.put raises) ----------------


def _make_failing_controller() -> HistoryController:
    store = _FailingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()
    return controller


@pytest.mark.anyio
async def test_ui_offset_unchanged_when_on_response_store_put_raises():
    controller = _make_failing_controller()
    initial_offset = controller.ui_offset

    with pytest.raises(OSError):
        await controller.on_response()

    assert controller.ui_offset == initial_offset, (
        "ui_offset must not advance when store.put() raises"
    )


@pytest.mark.anyio
async def test_ui_offset_unchanged_when_save_current_store_put_raises():
    controller = _make_failing_controller()
    controller.record = new_conversation_record(title="t")
    initial_offset = controller.ui_offset

    with pytest.raises(OSError):
        await controller.save()

    assert controller.ui_offset == initial_offset, (
        "ui_offset must not advance when store.put() raises"
    )


@pytest.mark.anyio
async def test_explicit_save_returns_false_without_active_record():
    controller, store = _make_controller()

    assert await controller.save() is False
    assert store.put_calls == []


@pytest.mark.anyio
async def test_explicit_save_captures_state_without_counting_response():
    saved_values: list[dict[str, Any]] = []

    def capture(values: dict[str, Any]) -> None:
        values["artifact"] = {"version": 2}
        saved_values.append(dict(values))

    controller, store = _make_controller(save_callbacks=[capture])
    await controller.on_response()
    assert controller.record is not None
    response_count = controller.record.response_count
    put_count = len(store.put_calls)

    assert await controller.save() is True
    assert controller.record.response_count == response_count
    assert controller.record.values == {"artifact": {"version": 2}}
    assert len(saved_values) == 2
    assert len(store.put_calls) == put_count + 1
    assert controller._title_task is None


@pytest.mark.anyio
async def test_explicit_save_does_not_start_title_generation():
    title_calls: list[list[dict[str, Any]]] = []

    async def title_fn(turns: list[dict[str, Any]]) -> str:
        title_calls.append(turns)
        return "Generated title"

    controller, _store = _make_controller()
    controller.title_enabled = True
    controller.title_fn = title_fn
    await controller.on_response()
    assert controller.record is not None
    assert controller.record.response_count == 1
    assert controller._title_task is None

    assert await controller.save() is True
    assert controller._title_task is None
    assert title_calls == []


@pytest.mark.anyio
async def test_explicit_save_runs_history_lifecycle_after_persist():
    controller, _store = _make_controller()
    await controller.on_response()
    events: list[str] = []

    original_put = controller._put_record

    async def put(
        partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        await original_put(partition, record)
        events.append("put")

    async def bookmark(record: ConversationRecord) -> None:
        events.append("bookmark")

    controller._put_record = put
    controller.on_response_saved = bookmark
    controller._evict_if_needed = AsyncMock(
        side_effect=lambda: events.append("evict")
    )
    controller.send_history_update = AsyncMock(
        side_effect=lambda: events.append("history")
    )
    controller._send_sibling_metadata = AsyncMock(
        side_effect=lambda: events.append("siblings")
    )

    assert await controller.save() is True
    assert events == ["put", "evict", "bookmark", "history", "siblings"]


# --- on_url_change (URL-mode navigation) ------------------------------------


class _NavFakeChat(_FakeChat):
    def __init__(self) -> None:
        super().__init__()
        self.actions: list[dict[str, Any]] = []
        self.cleared = 0

    async def _send_action(self, action: Any) -> None:
        self.actions.append(dict(action))

    async def clear_messages(self) -> None:
        self.cleared += 1

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        pass


class _NavFakeAdapter(_FakeAdapter):
    def __init__(self) -> None:
        self.set_calls: list[list[Any]] = []

    def set_turns_json(self, turns: list[Any]) -> None:
        self.set_calls.append(turns)


class _NavStore(_RecordingStore):
    def __init__(self) -> None:
        super().__init__()
        self.records: dict[str, Any] = {}
        self.deleted: list[str] = []

    async def get(self, partition: ConversationPartition, conv_id: str) -> Any:
        return self.records.get(conv_id)

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.deleted.append(conv_id)
        self.records.pop(conv_id, None)


def _make_nav_controller(
    *, with_url_mode: bool = False
) -> tuple[HistoryController, _NavStore, _NavFakeChat]:
    store = _NavStore()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()
    if with_url_mode:

        async def _update_url(conv_id: str | None) -> None:
            url = f"?conv={conv_id}" if conv_id is not None else None
            await controller.send_navigate(url, conv_id)

        controller.on_active_id_change = _update_url
    return controller, store, chat


def _nav_actions(chat: _NavFakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_navigate"]


@pytest.mark.anyio
async def test_switch_to_swaps_in_session():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    assert _nav_actions(chat) == []
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_switch_to_url_mode_sends_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    target = new_conversation_record(title="other")
    store.records[target.id] = target

    await controller.switch_to(target.id)

    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={target.id}"
    assert navs[0]["active_id"] == target.id
    assert chat.cleared == 1
    assert controller.record is target


@pytest.mark.anyio
async def test_switch_to_nonexistent_id_raises():
    controller, _store, _chat = _make_nav_controller()

    with pytest.raises(RuntimeError, match="no longer exists"):
        await controller.switch_to("does-not-exist")


class _UnsupportedSchemaVersionStore(ConversationStore):
    """Custom store whose get() returns a record from a newer, unsupported
    schema version -- simulates a downgrade against a store written by a
    future version of shinychat."""

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        rec = new_conversation_record(title="from the future")
        rec.id = conv_id
        rec.schema_version = MAX_SCHEMA_VERSION + 1
        return rec

    async def put(self, partition: ConversationPartition, record: Any) -> None:
        pass

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass


@pytest.mark.anyio
async def test_switch_to_rejects_record_with_unsupported_schema_version():
    store = _UnsupportedSchemaVersionStore()
    controller, _store = _make_controller(store=store)

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.switch_to("c_future")

    assert controller.record is None


@pytest.mark.anyio
async def test_rename_rejects_record_with_unsupported_schema_version_before_writing():
    # The controller must check schema_version on every write, not just every
    # read -- a custom store's put() should never see an incompatible record
    # (issue #322).
    controller, store = _make_controller()
    controller.record = new_conversation_record(title="t")
    controller.record.schema_version = MAX_SCHEMA_VERSION + 1

    with pytest.raises(UnsupportedSchemaVersionError):
        await controller.rename(controller.record.id, "new title")

    assert store.put_calls == []


@pytest.mark.anyio
async def test_new_chat_url_mode_sends_navigate_null():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.new_chat()

    navs = _nav_actions(chat)
    assert navs == [
        {"type": "history_navigate", "url": None, "active_id": None}
    ]
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_send_navigate_can_request_hard_reload():
    controller, _store, chat = _make_nav_controller()

    await controller.send_navigate("?_state_id_=abc123", "c123", reload=True)

    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": "?_state_id_=abc123",
            "active_id": "c123",
            "reload": True,
        }
    ]


@pytest.mark.anyio
async def test_new_chat_browser_mode_no_navigate():
    controller, _store, chat = _make_nav_controller()

    await controller.new_chat()

    assert _nav_actions(chat) == []
    assert chat.cleared == 1


@pytest.mark.anyio
async def test_delete_active_url_mode_sends_navigate_null():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    active = new_conversation_record(title="doomed")
    store.records[active.id] = active
    # Activate through the shared op so record and active ID move together,
    # as every real code path does.
    await controller.activate_record(active)

    await controller.delete(active.id)

    assert store.deleted == [active.id]
    navs = _nav_actions(chat)
    assert navs == [
        {
            "type": "history_navigate",
            "url": f"?conv={active.id}",
            "active_id": active.id,
        },
        {"type": "history_navigate", "url": None, "active_id": None},
    ]


@pytest.mark.anyio
async def test_delete_inactive_does_not_navigate():
    controller, store, chat = _make_nav_controller(with_url_mode=True)
    other = new_conversation_record(title="other")
    store.records[other.id] = other

    await controller.delete(other.id)

    assert store.deleted == [other.id]
    assert _nav_actions(chat) == []


@pytest.mark.anyio
async def test_on_response_first_save_url_mode_sends_navigate():
    controller, _store, chat = _make_nav_controller(with_url_mode=True)

    await controller.on_response()

    assert controller.record is not None
    navs = _nav_actions(chat)
    assert len(navs) == 1
    assert navs[0]["url"] == f"?conv={controller.record.id}"


# --- retitle ------------------------------------------------------------------


def _make_retitle_controller(
    title_fn: Any = None,
    raw_client: Any = None,
) -> tuple[HistoryController, _RecordingStore]:
    store = _RecordingStore()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=raw_client,
    )
    controller.partition = part()
    return controller, store


@pytest.mark.anyio
async def test_retitle_updates_title_and_persists():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "Generated Title",
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([{"role": "user", "content": "hi"}])

    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"
    assert len(store.put_calls) == 1


@pytest.mark.anyio
async def test_retitle_noop_when_record_is_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )

    await controller.retitle([])

    assert store.put_calls == []


# --- bookmark callback cleanup ------------------------------------------------


class _BookmarkStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.cancel_calls = 0
        self.on_bookmarked_calls = 0

    def on_bookmarked(self, fn: Any) -> Any:
        self.on_bookmarked_calls += 1

        def cancel() -> None:
            self.cancel_calls += 1

        return cancel

    async def do_bookmark(self) -> None:
        if self.fail:
            raise RuntimeError("bookmark failed")


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_success():
    bookmark = _BookmarkStub()

    async def _on_bookmarked(url: str) -> None:
        pass

    await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_do_bookmark_with_cleanup_cancels_on_failure():
    bookmark = _BookmarkStub(fail=True)

    async def _on_bookmarked(url: str) -> None:
        pass

    with pytest.raises(RuntimeError, match="bookmark failed"):
        await do_bookmark_with_cleanup(bookmark, _on_bookmarked)

    assert bookmark.on_bookmarked_calls == 1
    assert bookmark.cancel_calls == 1


@pytest.mark.anyio
async def test_retitle_noop_when_user_already_renamed():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: "should not be used",
    )
    controller.record = new_conversation_record(title="My Title")
    controller.record.title_source = "user"

    await controller.retitle([])

    assert controller.record.title == "My Title"
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_generate_returns_none():
    controller, store = _make_retitle_controller(
        title_fn=lambda turns: None,
    )
    controller.record = new_conversation_record(title="fallback")

    await controller.retitle([])

    assert controller.record.title == "fallback"
    assert controller.record.title_source is None
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_conversation_switched_during_generation():
    original = new_conversation_record(title="original")
    replacement = new_conversation_record(title="replacement")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the conversation switching while the LLM call is in flight
        controller.record = replacement
        return "Title for original"

    controller.title_fn = slow_title
    controller.record = original

    await controller.retitle([])

    assert original.title == "original", "must not update the old record"
    assert controller.record is replacement
    assert store.put_calls == []


@pytest.mark.anyio
async def test_retitle_noop_when_user_renames_during_generation():
    record = new_conversation_record(title="fallback")

    controller, store = _make_retitle_controller()

    async def slow_title(turns: Any) -> str:
        # Simulate the user renaming while the LLM call is in flight
        record.title_source = "user"
        record.title = "User's Title"
        return "LLM Title"

    controller.title_fn = slow_title
    controller.record = record

    await controller.retitle([])

    assert record.title == "User's Title"
    assert record.title_source == "user"
    assert store.put_calls == []


# --- deferred titling trigger --------------------------------------------------


class _GrowingFakeAdapter:
    """Like _FakeAdapter, but turns grow across calls to simulate multiple
    real responses (_FakeAdapter always returns the same fixed 2 turns)."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def get_turns_json(self) -> list[Any]:
        return list(self.turns)

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[t] for t in self.turns]

    def set_turns_json(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, Any]:
        return {}


def _make_deferred_title_controller(
    title_fn: Any = None,
) -> tuple[HistoryController, _RecordingStore, _GrowingFakeAdapter]:
    store = _RecordingStore()
    adapter = _GrowingFakeAdapter()
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=title_fn,
        title_enabled=True,
        client=None,
    )
    controller.partition = part()
    return controller, store, adapter


@pytest.mark.anyio
async def test_title_stays_fallback_after_first_response():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 1
    assert controller.record.title_source is None
    assert controller._title_task is None


@pytest.mark.anyio
async def test_titling_fires_after_second_response_exactly_once():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    task_after_first_response = controller._title_task
    assert task_after_first_response is None

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller.record.response_count == 2
    title_task = controller._title_task
    assert title_task is not None
    await title_task
    assert controller.record.title == "Generated Title"
    assert controller.record.title_source == "llm"


@pytest.mark.anyio
async def test_rename_between_first_and_second_response_blocks_auto_titling():
    controller, _store, adapter = _make_deferred_title_controller(
        title_fn=lambda turns: "Generated Title",
    )
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller.on_response()
    assert controller.record is not None
    await controller.rename(controller.record.id, "My Title")

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller.on_response()

    assert controller.record is not None
    assert controller._title_task is None
    assert controller.record.title == "My Title"
    assert controller.record.title_source == "user"


@pytest.mark.anyio
async def test_titling_fires_on_second_response_across_sessions():
    store = InMemoryConversationStore()
    adapter1 = _GrowingFakeAdapter()
    controller1 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter1,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller1.partition = part()
    adapter1.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await controller1.on_response()
    assert controller1.record is not None
    conv_id = controller1.record.id
    assert controller1._title_task is None

    # Simulate a brand-new session: fresh controller, same backing store,
    # loads the persisted (1-response) conversation before continuing it.
    adapter2 = _GrowingFakeAdapter()
    adapter2.turns = list(adapter1.turns)
    controller2 = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=adapter2,  # type: ignore[arg-type]
        store=store,
        title_fn=lambda turns: "Generated Title",
        title_enabled=True,
        client=None,
    )
    controller2.partition = part()
    controller2.record = await store.get(part(), conv_id)

    adapter2.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    await controller2.on_response()

    title_task = controller2._title_task
    assert title_task is not None
    await title_task
    assert controller2.record is not None
    assert controller2.record.title == "Generated Title"
    assert controller2.record.title_source == "llm"


# --- save/restore callbacks --------------------------------------------------


def _make_fake_chat() -> _FakeChat:
    return _FakeChat()


@pytest.mark.anyio
async def test_save_callback_fires_and_values_stored(tmp_path: Any) -> None:
    """on_save callback populates record.values."""
    from shinychat._history_store import FileConversationStore

    save_calls: list[dict[str, Any]] = []
    save_cbs: list[Any] = []

    def my_save(values: dict[str, Any]) -> None:
        values["x"] = 42
        save_calls.append(dict(values))

    save_cbs.append(my_save)

    store = FileConversationStore(tmp_path)
    adapter = _FakeAdapter()
    controller = HistoryController(
        chat=_make_fake_chat(),  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=save_cbs,
        restore_callbacks=[],
    )
    controller.partition = part(scope="alice")

    await controller.on_response()

    assert len(save_calls) == 1
    assert save_calls[0]["x"] == 42
    assert controller.record is not None
    assert controller.record.values.get("x") == 42


@pytest.mark.anyio
async def test_restore_callback_fires_on_switch(tmp_path: Any) -> None:
    """on_restore callback receives stored values on switch_to."""
    from shinychat._history_store import FileConversationStore
    from shinychat._history_types import new_conversation_record

    restored: list[tuple[dict[str, Any], str]] = []
    restore_cbs: list[Any] = []

    store = FileConversationStore(tmp_path)
    adapter = _NavFakeAdapter()
    chat = _NavFakeChat()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=object(),
        save_callbacks=[],
        restore_callbacks=restore_cbs,
    )
    controller.partition = part(scope="alice")

    def on_restore(values: dict[str, Any]) -> None:
        assert controller.record is not None
        restored.append((dict(values), controller.record.id))

    restore_cbs.append(on_restore)

    # Create a record with values directly in the store (not via on_response,
    # which would immediately re-capture and overwrite our values).
    target = new_conversation_record(title="old")
    target.values = {"x": 99}
    await store.put(part(scope="alice"), target)

    # Simulate having a different current conversation
    other = new_conversation_record(title="current")
    await store.put(part(scope="alice"), other)
    controller.record = other

    await controller.switch_to(target.id)

    assert restored == [({"x": 99}, target.id)]


# ---------------------------------------------------------------------------
# _evict_if_needed
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_no_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.partition = part(scope="alice")

    await controller._evict_if_needed()
    assert len(await store.list(part(scope="alice"))) == 1


@pytest.mark.anyio
async def test_evict_if_needed_noop_when_under_limit():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="t")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=100
        * 1024
        * 1024,  # 100 MB — well above any test record
    )
    controller.partition = part(scope="alice")

    await controller._evict_if_needed()
    assert len(await store.list(part(scope="alice"))) == 1


@pytest.mark.anyio
async def test_evict_if_needed_removes_oldest_preserves_active():
    store = InMemoryConversationStore()

    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.created_at = rec2.created_at + timedelta(seconds=1)
    rec3.created_at = rec3.created_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,  # 1 byte: ensures all non-active records are evicted
    )
    controller.partition = part(scope="alice")
    controller.record = rec3  # newest is active

    await controller._evict_if_needed()

    remaining = {m.id for m in await store.list(part(scope="alice"))}
    assert rec1.id not in remaining
    assert rec2.id not in remaining
    assert rec3.id in remaining


@pytest.mark.anyio
async def test_evict_if_needed_calls_list_once_and_never_total_size():
    # Regression: total_size() used to be re-called (a full-scope sweep) on
    # every eviction iteration. The running total should now come entirely
    # from a single list() call's per-record size_bytes.
    store = InMemoryConversationStore()
    rec1 = new_conversation_record(title="oldest")
    rec2 = new_conversation_record(title="middle")
    rec3 = new_conversation_record(title="newest")
    rec2.created_at = rec2.created_at + timedelta(seconds=1)
    rec3.created_at = rec3.created_at + timedelta(seconds=2)
    for rec in [rec1, rec2, rec3]:
        await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.partition = part(scope="alice")
    controller.record = rec3

    list_spy = AsyncMock(wraps=store.list)
    total_size_spy = AsyncMock(wraps=store.total_size)
    store.list = list_spy  # type: ignore[method-assign]
    store.total_size = total_size_spy  # type: ignore[method-assign]

    await controller._evict_if_needed()

    assert list_spy.call_count == 1
    assert total_size_spy.call_count == 0


@pytest.mark.anyio
async def test_evict_if_needed_warns_once_when_active_alone_exceeds_budget():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="big")
    rec.append_linear([{"role": "user", "content": "x" * 1000}])
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=1,
    )
    controller.partition = part(scope="alice")
    controller.record = rec  # active; nothing else to evict

    with pytest.warns(UserWarning, match="remains over"):
        await controller._evict_if_needed()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller._evict_if_needed()  # must not warn a second time


@pytest.mark.anyio
async def test_evict_one_deletes_from_store():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
        max_store_bytes=None,
    )
    controller.partition = part(scope="alice")

    await controller._evict_one(rec.id)

    assert await store.get(part(scope="alice"), rec.id) is None


# ---------------------------------------------------------------------------
# Controller lifecycle hooks: on_response_saved, on_pre_switch, on_evict
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_on_response_saved_fires_when_new_data_is_saved():
    controller, store = _make_controller()
    fired: list[str] = []
    turns = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]

    class _GrowingAdapter(_FakeAdapter):
        def get_turns_json(self) -> list[Any]:
            return turns

    async def hook(record: Any) -> None:
        fired.append(record.id)

    controller.adapter = _GrowingAdapter()  # type: ignore[assignment]
    controller.on_response_saved = hook

    await controller.on_response()
    turns.extend(
        [
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "sure"},
        ]
    )
    await controller.on_response()

    assert len(fired) == 2
    assert fired[0] == fired[1]  # same conversation id both times


@pytest.mark.anyio
async def test_on_pre_switch_true_skips_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return True  # signal: skip in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    # In-session swap was skipped: client turns NOT updated, UI NOT cleared
    assert chat.cleared == 0
    # record not changed because we returned True (navigation handled by hook)
    assert controller.record is None


@pytest.mark.anyio
async def test_on_pre_switch_false_allows_in_session_swap():
    controller, store, chat = _make_nav_controller()
    target = new_conversation_record(title="other")
    store.records[target.id] = target
    pre_switch_calls: list[str] = []

    async def hook(rec: Any) -> bool:
        pre_switch_calls.append(rec.id)
        return False  # allow normal in-session swap

    controller.on_pre_switch = hook

    await controller.switch_to(target.id)

    assert pre_switch_calls == [target.id]
    assert chat.cleared == 1
    assert controller.record is target


# --- on_evict hook -----------------------------------------------------------


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_evict_one():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=_FakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part(scope="alice")

    async def hook(conv_id: str) -> None:
        # Record must still exist in store when the hook fires
        still_there = await store.get(part(scope="alice"), conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller._evict_one(rec.id)

    assert order == ["hook_before"]
    assert await store.get(part(scope="alice"), rec.id) is None


@pytest.mark.anyio
async def test_on_evict_fires_before_store_delete_in_delete():
    store = InMemoryConversationStore()
    rec = new_conversation_record(title="old")
    await store.put(part(scope="alice"), rec)

    order: list[str] = []

    controller = HistoryController(
        chat=_NavFakeChat(),  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part(scope="alice")

    async def hook(conv_id: str) -> None:
        still_there = await store.get(part(scope="alice"), conv_id)
        order.append("hook_before" if still_there is not None else "hook_after")

    controller.on_evict = hook

    await controller.delete(rec.id)

    assert order == ["hook_before"]
    assert await store.get(part(scope="alice"), rec.id) is None


# ---------------------------------------------------------------------------
# handle_navigate / handle_edit
# ---------------------------------------------------------------------------


class _TrackingChat:
    def __init__(self) -> None:
        self.messages_: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.cleared: bool = False
        self.set_greeting_calls: list[Any] = []
        self._session = None

    def _messages_for_bookmark(self) -> list[dict[str, Any]]:
        return list(self.messages_)

    async def _send_action(self, action: Any) -> None:
        self.actions.append(action)

    async def clear_messages(self) -> None:
        self.messages_ = []
        self.cleared = True

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        self.messages_.append(message_dict)

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)


class _TrackingAdapter:
    def __init__(self) -> None:
        self.turns: list[TurnDict] = []

    def get_turns_json(self) -> list[TurnDict]:
        return list(self.turns)

    def get_turns_grouped(self) -> list[list[TurnDict]]:
        return [[t] for t in self.turns]

    def set_turns_json(self, turns: list[TurnDict]) -> None:
        self.turns = list(turns)

    def client_info(self) -> dict[str, str]:
        return {}


def _make_branched_controller() -> tuple[
    HistoryController, _TrackingChat, _TrackingAdapter, _RecordingStore
]:
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # Build a branched record:
    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2) -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-edited) -> n_0006(asst:a2-new)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    # Branch at n_0002: create sibling of n_0003
    branch_from(
        rec,
        "n_0002",
        [{"role": "user", "content": "q2-edited"}],
        ui=[msg("user")],
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-new"}],
        ui=[msg("assistant")],
    )
    # Active path: [n_0001, n_0002, n_0005, n_0006]
    controller.record = rec
    adapter.turns = rec.path_turns()
    return controller, chat, adapter, store


@pytest.mark.anyio
async def test_handle_navigate_switches_to_prev_sibling():
    controller, chat, adapter, store = _make_branched_controller()

    await controller.handle_navigate(2, "prev")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0004"
    assert [t.get("content") for t in adapter.turns] == ["q1", "a1", "q2", "a2"]
    assert chat.cleared
    assert len(chat.messages_) == 4
    assert len(store.put_calls) == 1


@pytest.mark.anyio
async def test_handle_navigate_switches_to_next_sibling():
    controller, chat, adapter, store = _make_branched_controller()

    await controller.handle_navigate(2, "prev")
    chat.cleared = False
    store.put_calls.clear()

    await controller.handle_navigate(2, "next")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0006"
    assert [t.get("content") for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-edited",
        "a2-new",
    ]


@pytest.mark.anyio
async def test_handle_navigate_noop_at_boundary():
    controller, chat, adapter, store = _make_branched_controller()

    await controller.handle_navigate(2, "next")

    assert not chat.cleared
    assert store.put_calls == []


@pytest.mark.anyio
async def test_handle_navigate_invalid_direction_is_noop():
    controller, chat, adapter, store = _make_branched_controller()
    await controller.handle_navigate(2, "invalid")
    assert not chat.cleared
    assert store.put_calls == []


def _make_triple_branched_controller() -> tuple[
    HistoryController, _TrackingChat, _TrackingAdapter, _RecordingStore
]:
    """Same shape as _make_branched_controller, but the user message at the
    fork point has been edited twice -- three siblings at one fork point,
    not two -- to exercise a path no existing fixture covers."""
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2)      -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-e1)  -> n_0006(asst:a2-e1)
    #                                     -> n_0007(user:q2-e2)  -> n_0008(asst:a2-e2)
    rec = new_conversation_record(title="t")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    branch_from(
        rec, "n_0002", [{"role": "user", "content": "q2-e1"}], ui=[msg("user")]
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-e1"}],
        ui=[msg("assistant")],
    )
    branch_from(
        rec, "n_0002", [{"role": "user", "content": "q2-e2"}], ui=[msg("user")]
    )
    branch_from(
        rec,
        "n_0007",
        [{"role": "assistant", "content": "a2-e2"}],
        ui=[msg("assistant")],
    )
    # Active path: [n_0001, n_0002, n_0007, n_0008]
    controller.record = rec
    adapter.turns = rec.path_turns()
    return controller, chat, adapter, store


@pytest.mark.anyio
async def test_handle_navigate_cycles_through_three_siblings():
    controller, chat, adapter, store = _make_triple_branched_controller()

    await controller.handle_navigate(2, "prev")
    assert controller.record is not None
    assert controller.record.current_leaf == "n_0006"
    assert [t.get("content") for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e1",
        "a2-e1",
    ]

    await controller.handle_navigate(2, "prev")
    assert controller.record.current_leaf == "n_0004"
    assert [t.get("content") for t in adapter.turns] == ["q1", "a1", "q2", "a2"]

    store.put_calls.clear()
    await controller.handle_navigate(2, "prev")
    assert controller.record.current_leaf == "n_0004"
    assert store.put_calls == []

    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0006"
    assert [t.get("content") for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e1",
        "a2-e1",
    ]

    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0008"
    assert [t.get("content") for t in adapter.turns] == [
        "q1",
        "a1",
        "q2-e2",
        "a2-e2",
    ]

    store.put_calls.clear()
    await controller.handle_navigate(2, "next")
    assert controller.record.current_leaf == "n_0008"
    assert store.put_calls == []


@pytest.mark.anyio
async def test_handle_edit_truncates_and_signals_resubmit():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(2, "q2-re-edited")

    assert controller.record is not None
    assert controller.record.current_leaf == "n_0002"
    assert [t.get("content") for t in adapter.turns] == ["q1", "a1"]
    assert chat.cleared
    assert len(chat.messages_) == 2
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert len(update_actions) == 1
    assert update_actions[0]["value"] == "q2-re-edited"
    assert update_actions[0]["submit"] is True


@pytest.mark.anyio
async def test_handle_edit_first_message_truncates_to_root():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(0, "new-greeting")

    assert controller.record is not None
    assert controller.record.current_leaf is None
    assert adapter.turns == []
    assert chat.messages_ == []
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert update_actions[0]["value"] == "new-greeting"


@pytest.mark.anyio
async def test_handle_edit_forks_from_a_multi_turn_tool_call_node():
    """Edit a message whose parent node is a grouped tool-call exchange
    (assistant-request/user-result/assistant-final stored as one node, one
    UI message) -- verifies node_id_for_message_index still maps to the
    right UI-facing message, and that truncating to that node preserves
    every turn in the group, not just its last one."""
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = _RecordingStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # n_0001(user:weather?)                                  ui=[msg(user)]
    # n_0002(asst_req, user_result, asst_final -- one group)  ui=[msg(assistant)]
    # n_0003(user:thanks)                                     ui=[msg(user)]
    # n_0004(asst:you're welcome)                             ui=[msg(assistant)]
    rec = new_conversation_record(title="t")
    rec.append_linear(
        [{"role": "user", "content": "weather?"}], ui=[msg("user")]
    )
    rec.append_linear(
        [
            {"role": "assistant", "content": "tool_request"},
            {"role": "user", "content": "tool_result"},
            {"role": "assistant", "content": "sunny"},
        ],
        ui=[msg("assistant")],
    )
    rec.append_linear([{"role": "user", "content": "thanks"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "you're welcome"}],
        ui=[msg("assistant")],
    )
    controller.record = rec
    adapter.turns = rec.path_turns()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(2, "thanks a lot")

    assert controller.record.current_leaf == "n_0002"
    assert [t.get("content") for t in adapter.turns] == [
        "weather?",
        "tool_request",
        "tool_result",
        "sunny",
    ]
    assert chat.cleared
    assert len(chat.messages_) == 2
    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert update_actions[0]["value"] == "thanks a lot"
    assert update_actions[0]["submit"] is True


@pytest.mark.anyio
async def test_handle_edit_with_attachments_forwards_them_with_set_mode():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]
    attachments = [
        {
            "mime": "image/png",
            "data_url": "data:image/png;base64,AAAA",
            "name": "pic.png",
            "size": 3,
        }
    ]

    await controller.handle_edit(2, "q2-re-edited", attachments)

    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert len(update_actions) == 1
    assert update_actions[0]["attachment_mode"] == "set"
    assert update_actions[0]["attachments"] == [
        {
            "mime": "image/png",
            "data_url": "data:image/png;base64,AAAA",
            "name": "pic.png",
            "size": 3,
        }
    ]


@pytest.mark.anyio
async def test_handle_edit_without_attachments_omits_attachment_fields():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]

    await controller.handle_edit(2, "q2-re-edited")

    update_actions = [
        a for a in chat.actions if a.get("type") == "update_input"
    ]
    assert "attachments" not in update_actions[0]
    assert "attachment_mode" not in update_actions[0]


@pytest.mark.anyio
async def test_handle_edit_rejects_unsupported_attachment_type():
    controller, chat, adapter, store = _make_branched_controller()
    chat.messages_ = [
        msg("user"),
        msg("assistant"),
        msg("user"),
        msg("assistant"),
    ]
    bad_attachments = [
        {
            "mime": "application/x-executable",
            "data_url": "data:application/x-executable;base64,AAA",
            "name": "bad.exe",
            "size": 3,
        }
    ]

    with pytest.raises(ValueError, match="unsupported MIME type"):
        await controller.handle_edit(2, "edited", bad_attachments)


@pytest.mark.anyio
async def test_switch_to_resends_sibling_metadata_for_branched_conversation():
    chat = _TrackingChat()
    adapter = _TrackingAdapter()
    store = InMemoryConversationStore()
    controller = HistoryController(
        chat=chat,  # type: ignore[arg-type]
        adapter=adapter,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()

    # Same branched shape as _make_branched_controller:
    # n_0001(user:q1) -> n_0002(asst:a1) -> n_0003(user:q2) -> n_0004(asst:a2)
    #                                     -> n_0005(user:q2-edited) -> n_0006(asst:a2-new)
    rec = new_conversation_record(title="branched")
    rec.append_linear([{"role": "user", "content": "q1"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a1"}], ui=[msg("assistant")]
    )
    rec.append_linear([{"role": "user", "content": "q2"}], ui=[msg("user")])
    rec.append_linear(
        [{"role": "assistant", "content": "a2"}], ui=[msg("assistant")]
    )
    branch_from(
        rec,
        "n_0002",
        [{"role": "user", "content": "q2-edited"}],
        ui=[msg("user")],
    )
    branch_from(
        rec,
        "n_0005",
        [{"role": "assistant", "content": "a2-new"}],
        ui=[msg("assistant")],
    )
    await store.put(part(), rec)

    other = new_conversation_record(title="other")
    await store.put(part(), other)

    controller.record = rec
    adapter.turns = rec.path_turns()

    # Switch to a different conversation, then back -- simulates starting a
    # new chat and returning to the conversation with edited/branched messages.
    await controller.switch_to(other.id)
    chat.actions.clear()
    await controller.switch_to(rec.id)

    sibling_actions = [
        a for a in chat.actions if a["type"] == "update_siblings"
    ]
    assert len(sibling_actions) == 1
    # n_0005 (message index 2) is the active branch's fork point: 2nd of 2 siblings.
    assert sibling_actions[0]["data"] == {2: {"index": 1, "total": 2}}


# ---------------------------------------------------------------------------
# Turns-based restore
# ---------------------------------------------------------------------------


def _user_turn_dict(text: str) -> dict[str, Any]:
    return {
        "role": "user",
        "contents": [{"content_type": "text", "text": text}],
    }


class _ToolTurnsAdapter:
    """Adapter over a fixed chatlas tool-call exchange (user question, then
    an assistant-request/user-result/assistant-final group)."""

    def __init__(self) -> None:
        self.user_turn = _user_turn_dict("weather?")
        self.tool_group = chatlas_tool_group()

    def get_turns_json(self) -> list[Any]:
        return [self.user_turn, *self.tool_group]

    def get_turns_grouped(self) -> list[list[Any]]:
        return [[self.user_turn], self.tool_group]

    def set_turns_json(self, turns: list[Any]) -> None:
        pass

    def client_info(self) -> dict[str, Any]:
        return {}


@pytest.mark.anyio
async def test_on_response_stores_derived_ui_with_structured_blocks():
    controller, _store = _make_controller()
    controller.adapter = _ToolTurnsAdapter()  # type: ignore[assignment]

    await controller.on_response()

    record = controller.record
    assert record is not None
    path = record.path_node_ids()
    assert len(path) == 2

    asst_ui = record.nodes[path[1]].ui
    assert asst_ui is not None and len(asst_ui) == 1
    stored = asst_ui[0]
    assert stored["version"] == STORED_UI_VERSION
    assert stored["role"] == "assistant"
    assert [s["type"] for s in stored["segments"] if "type" in s] == [
        "tool_request",
        "tool_result",
    ]
    assert stored["segments"][0]["tool_name"] == "get_weather"
    assert stored["segments"][1]["value"] == "Sunny"
    assert stored["segments"][2] == {
        "content": "It's sunny.",
        "content_type": "markdown",
    }


@pytest.mark.anyio
async def test_replay_emits_derived_blocks_inline_in_segments():
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat_replay_blocks")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        controller = HistoryController(
            chat=chat,  # type: ignore[arg-type]
            adapter=_ToolTurnsAdapter(),  # type: ignore[arg-type]
            store=_RecordingStore(),
            title_fn=None,
            title_enabled=False,
            client=None,
        )
        controller.partition = part()

        await controller.on_response()
        record = controller.record
        assert record is not None

        sent.clear()
        await controller.replay_ui(record)

    message_actions = [a for a in sent if a["type"] == "message"]
    assert len(message_actions) == 2

    asst_segments = message_actions[1]["message"]["segments"]
    kinds = [s.get("type", "string") for s in asst_segments]
    assert kinds == ["tool_request", "tool_result", "string"]
    assert asst_segments[0]["request_id"] == "x"
    assert asst_segments[1]["status"] == "success"
    assert asst_segments[2] == {
        "content": "It's sunny.",
        "content_type": "markdown",
    }


@pytest.mark.anyio
async def test_replay_discards_old_format_ui_and_rederives_from_turns():
    rec = new_conversation_record(title="t")
    rec.append_linear([_user_turn_dict("weather?")], ui=[msg("user")])
    rec.append_linear(
        chatlas_tool_group(),
        ui=[
            {
                "role": "assistant",
                "segments": [
                    {"content": "It's sunny.", "content_type": "markdown"}
                ],
            }
        ],
    )

    chat = _TrackingChat()
    controller, _store = _make_controller()
    controller.chat = chat  # type: ignore[assignment]

    await controller.replay_ui(rec)

    assert len(chat.messages_) == 2
    assert chat.messages_[0]["version"] == STORED_UI_VERSION
    assert chat.messages_[0]["segments"] == [
        {"content": "weather?", "content_type": "markdown"}
    ]
    asst = chat.messages_[1]
    assert asst["version"] == STORED_UI_VERSION
    assert [s["type"] for s in asst["segments"] if "type" in s] == [
        "tool_request",
        "tool_result",
    ]


@pytest.mark.anyio
async def test_replay_falls_back_to_text_when_turns_missing():
    rec = new_conversation_record(title="t")
    node_id = rec.append_linear([], ui=None)

    chat = _TrackingChat()
    controller, _store = _make_controller()
    controller.chat = chat  # type: ignore[assignment]

    await controller.replay_ui(rec)

    assert chat.messages_ == [
        {
            "version": STORED_UI_VERSION,
            "role": "assistant",
            "segments": [{"content": "", "content_type": "markdown"}],
        }
    ]
    assert rec.nodes[node_id].ui is None


@pytest.mark.anyio
async def test_replay_rederives_text_only_when_ui_missing():
    rec = new_conversation_record(title="t")
    rec.append_linear([_user_turn_dict("hi")], ui=None)
    rec.append_linear(
        [
            {
                "role": "assistant",
                "contents": [{"content_type": "text", "text": "hello"}],
            }
        ],
        ui=None,
    )

    chat = _TrackingChat()
    controller, _store = _make_controller()
    controller.chat = chat  # type: ignore[assignment]

    await controller.replay_ui(rec)

    assert chat.messages_ == [
        derived("user", "hi"),
        derived("assistant", "hello"),
    ]


@pytest.mark.anyio
async def test_out_of_band_message_survives_save_and_replay():
    controller, _store = _make_controller()
    chat = _TrackingChat()
    controller.chat = chat  # type: ignore[assignment]
    adapter = _ToolTurnsAdapter()
    controller.adapter = adapter  # type: ignore[assignment]

    note = {
        "role": "assistant",
        "segments": [
            {
                "content": "Note: rate limit reset.",
                "content_type": "markdown",
            }
        ],
    }
    chat.messages_ = [msg("user"), msg("assistant"), note]

    await controller.on_response()

    record = controller.record
    assert record is not None
    path = record.path_node_ids()
    leaf_ui = record.nodes[path[1]].ui
    assert leaf_ui is not None and len(leaf_ui) == 2
    assert leaf_ui[0]["version"] == STORED_UI_VERSION
    assert leaf_ui[1] == note

    chat.messages_ = []
    await controller.replay_ui(record)

    assert len(chat.messages_) == 3
    assert chat.messages_[2] == note
    assert [
        s["type"] for s in chat.messages_[1]["segments"] if "type" in s
    ] == [
        "tool_request",
        "tool_result",
    ]


@pytest.mark.anyio
async def test_save_replay_continue_save_bookkeeping():
    controller, store = _make_controller()
    chat = _ReplayFakeChat()
    controller.chat = chat  # type: ignore[assignment]
    adapter = _GrowingFakeAdapter()
    controller.adapter = adapter  # type: ignore[assignment]
    adapter.turns = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await controller.on_response()
    assert len(store.put_calls) == 1
    record = controller.record
    assert record is not None

    await controller.replay_ui(record)
    assert controller.ui_offset == 2

    await controller.on_response()
    assert len(store.put_calls) == 1

    adapter.turns += [
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "sure"},
    ]
    chat.messages = [
        *chat.messages,
        msg("user"),
        msg("assistant"),
    ]
    await controller.on_response()
    assert len(store.put_calls) == 2
    assert len(record.path_node_ids()) == 4
    new_node = record.nodes[record.path_node_ids()[3]]
    assert new_node.ui == [derived("assistant", "sure")]
