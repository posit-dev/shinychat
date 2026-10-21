# Per-exchange application values (`shinychat:values`) and the public
# `on_navigate` dispatch (shinychat#t829): sparse capture semantics, shared
# parent anchoring, store format, v1 import, validation, and the callback
# contract through production controller/transcript paths.

import asyncio
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from _history_test_helpers import replay_exchange_record
from shiny import reactive
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._history_plan import (
    canonical_values,
    latest_values,
    resolve_path_values,
)
from shinychat._history_store import (
    FileConversationStore,
    InMemoryConversationStore,
    sanitize_scope,
)
from shinychat._history_types import (
    VALUES_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record,
    new_conversation_record_v2,
)
from shinychat._history_v1 import import_v1_record
from shinychat.types import HistoryNavigateContext
from test_history_controller import (
    _FakeChat,
    _make_controller,
    _make_v2_navigation_controller,
    _make_v2_resubmit_controller,
    _RealChatSession,
    _sent,
    _stored_message,
    part,
)


def _values_entry(data: Any) -> StateEntry:
    return StateEntry(kind="values", version=1, mode="snapshot", data=data)


def _wire_transcript(recorder: Any) -> ChatTranscript:
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )


# ---------------------------------------------------------------------------
# Sparse capture semantics
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("with_callback", [False, True])
async def test_values_root_always_records_empty(with_callback: bool) -> None:
    def save_callback(values: dict[str, Any]) -> None:
        # Writes nothing: the values object stays empty.
        pass

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback] if with_callback else None,
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hi")
    )

    # Capture the descendant too: its empty value inherits from the root.
    assert await controller.save()
    record = recorder.record
    assert record is not None
    # The root always records, even the empty object.
    root_entry = record.nodes[record.root_id].state[VALUES_STATE_KEY]
    assert (root_entry.kind, root_entry.version, root_entry.mode) == (
        "values",
        1,
        "snapshot",
    )
    assert root_entry.data == {}
    # The descendant inherits instead of recording; resolution agrees.
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state
    assert resolve_path_values(record, exchange_id) == {}


@pytest.mark.anyio
async def test_values_sparse_record_on_change_and_back() -> None:
    current: dict[str, Any] = {"filter": "a"}

    def save_callback(values: dict[str, Any]) -> None:
        values.update(current)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    first = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    current = {"filter": "b"}
    assert await controller.save()
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    current = {"filter": "a"}
    assert await controller.save()
    third = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "three")
    )
    current = {}
    assert await controller.save()

    record = recorder.record
    assert record is not None
    nodes = record.nodes
    # A -> B -> A -> {}: every change against the nearest recorded
    # ancestor records, including the change back to the empty object
    # (an empty object is an explicit value, not inheritance).
    assert nodes[record.root_id].state[VALUES_STATE_KEY].data == {"filter": "a"}
    assert nodes[first].state[VALUES_STATE_KEY].data == {"filter": "b"}
    assert nodes[second].state[VALUES_STATE_KEY].data == {"filter": "a"}
    assert nodes[third].state[VALUES_STATE_KEY].data == {}
    assert resolve_path_values(record, third) == {}


@pytest.mark.anyio
async def test_values_bool_and_numeric_changes_are_not_conflated() -> None:
    # Python equality conflates distinct JSON values (True == 1); the
    # sparse comparison must not silently drop those changes.
    current: dict[str, Any] = {"nested": [1, True]}

    def save_callback(values: dict[str, Any]) -> None:
        values.update(current)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    first = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    current = {"nested": [1, 1]}
    assert await controller.save()
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    current = {"flag": True}
    assert await controller.save()
    current = {"flag": 1}
    assert await controller.save()

    record = recorder.record
    assert record is not None
    nodes = record.nodes
    assert nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "nested": [1, True]
    }
    assert nodes[first].state[VALUES_STATE_KEY].data == {"nested": [1, 1]}
    assert nodes[second].state[VALUES_STATE_KEY].data == {"flag": 1}


@pytest.mark.anyio
async def test_values_stream_finish_captures_tool_like_change() -> None:
    live = {"filter": "all"}

    def save_callback(values: dict[str, Any]) -> None:
        values["filter"] = live["filter"]

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = _wire_transcript(recorder)

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "west")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    # A tool-like state change lands mid-stream.
    live["filter"] = "west"
    await transcript.end_stream(
        stream_id="stream",
        status="ok",  # type: ignore[arg-type]
        error=None,
        send=_sent,
    )
    await controller.on_response()

    record = recorder.record
    assert record is not None
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "filter": "all"
    }
    assert record.nodes[exchange_id].state[VALUES_STATE_KEY].data == {
        "filter": "west"
    }


@pytest.mark.anyio
async def test_values_capture_reads_reactive_state_inside_stream_task() -> None:
    # `on_save` callbacks legitimately read reactive state; the stream
    # task's denial context must not break them (the capture runs inside
    # `reactive.isolate()`).
    from shiny.reactive._extended_task import DenialContext

    region = reactive.Value("all")

    def save_callback(values: dict[str, Any]) -> None:
        values["filter"] = region()

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = _wire_transcript(recorder)

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "west")
    )
    await transcript.start_stream(
        stream_id="stream",
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    region.set("west")
    with DenialContext()():
        await transcript.end_stream(
            stream_id="stream",
            status="ok",  # type: ignore[arg-type]
            error=None,
            send=_sent,
        )

    record = recorder.record
    assert record is not None
    assert record.nodes[exchange_id].state[VALUES_STATE_KEY].data == {
        "filter": "west"
    }


# ---------------------------------------------------------------------------
# Shared-parent anchoring
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_values_shared_parent_recapture_pins_inheriting_children() -> (
    None
):
    live = {"v": "same"}

    def save_callback(values: dict[str, Any]) -> None:
        values["v"] = live["v"]

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = _wire_transcript(recorder)

    abandoned = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "original")
    )
    # Unchanged from the root: the exchange inherits and records nothing.
    await controller.on_response()
    await controller.handle_edit(0, "alternative", request_id="edit-1")
    sibling = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "alternative")
    )
    await controller.on_response()

    live["v"] = "changed"
    await controller.handle_edit(0, "alternative two", request_id="edit-2")
    replacement = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "alternative two")
    )

    record = recorder.record
    assert record is not None
    # The root's recapture to the new value pinned the abandoned branch's
    # previous inherited value before the replacement opened.
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "v": "changed"
    }
    assert record.nodes[abandoned].state[VALUES_STATE_KEY].data == {"v": "same"}
    assert resolve_path_values(record, abandoned) == {"v": "same"}
    assert resolve_path_values(record, sibling) == {"v": "changed"}
    assert resolve_path_values(record, replacement) == {"v": "changed"}


@pytest.mark.anyio
async def test_values_shared_parent_recapture_pins_implicit_empty_default() -> (
    None
):
    # A record without any values entries: the implicit {} default is the
    # effective value. A shared parent's first recording must pin it on
    # existing children or they silently change to the new value.
    current: dict[str, Any] = {}

    def save_callback(values: dict[str, Any]) -> None:
        values.update(current)

    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    controller._save_callbacks.append(save_callback)
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    assert all(
        VALUES_STATE_KEY not in node.state for node in record.nodes.values()
    )

    await controller.resubmit(
        target, kind="edit", request_id="r", message_index=1
    )
    # The leave capture wrote the unchanged empty object nowhere.
    assert VALUES_STATE_KEY not in record.nodes[target].state

    current = {"f": "x"}
    replacement = await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )

    assert record.nodes[first].state[VALUES_STATE_KEY].data == {"f": "x"}
    # Pinned explicit empty object: the abandoned target still resolves to
    # the implicit value it had before the parent first recorded.
    assert record.nodes[target].state[VALUES_STATE_KEY].data == {}
    assert resolve_path_values(record, target) == {}
    assert resolve_path_values(record, replacement) == {"f": "x"}


# ---------------------------------------------------------------------------
# Validation and detachment
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad,error,match",
    [
        ({1: "x"}, ValueError, "Non-string mapping key"),
        ({"nested": [{2: "y"}]}, ValueError, "Non-string mapping key"),
        ({"pi": float("nan")}, ValueError, "Out of range float values"),
        ({"pi": float("inf")}, ValueError, "Out of range float values"),
        ({"obj": object()}, TypeError, "not JSON serializable"),
    ],
)
async def test_values_capture_rejects_unserializable_values(
    bad: dict[Any, Any], error: type[Exception], match: str
) -> None:
    current: dict[str, Any] = {"ok": 1}

    def save_callback(values: dict[str, Any]) -> None:
        values.update(current)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hi")
    )

    current = bad
    with pytest.raises(error, match=match):
        await controller.save()


def test_canonical_values_detaches_and_preserves_types() -> None:
    source: dict[str, Any] = {"b": {"n": 1}, "a": [True, 1.5]}
    canonical = canonical_values(source)
    assert canonical == source
    source["b"]["n"] = 999
    source["a"].append("later")
    assert canonical == {"b": {"n": 1}, "a": [True, 1.5]}
    # JSON types are preserved exactly: bool never becomes int.
    assert canonical["a"][0] is True
    assert canonical["a"][1] == 1.5


@pytest.mark.anyio
async def test_values_callback_dictionary_is_detached_from_record() -> None:
    held: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        values["deep"] = {"n": 1}
        held.append(values)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hi")
    )

    record = recorder.record
    assert record is not None
    # Mutating the dictionary the callback retained must not reach the
    # stored entry.
    held[0]["deep"]["n"] = 999
    held[0]["extra"] = True
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "deep": {"n": 1}
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "entry",
    [
        _values_entry(None),
        _values_entry(["not", "a", "dict"]),
        _values_entry("text"),
        StateEntry(kind="wrong", version=1, mode="snapshot", data={}),
        StateEntry(kind="values", version=2, mode="snapshot", data={}),
        StateEntry(kind="values", version=1, mode="delta", data={}),
    ],
)
def test_latest_values_validates_envelope_and_object(entry: StateEntry) -> None:
    with pytest.raises(ValueError, match="shinychat:values"):
        latest_values((("n_0000", entry),))


def test_latest_values_resolves_latest_object() -> None:
    entries = (
        ("n_0000", _values_entry({"a": 1})),
        ("n_0001", _values_entry({})),
    )
    latest = latest_values(entries)
    assert latest is not None
    # The empty object is an explicit value, not inheritance.
    assert latest.data == {}


@pytest.mark.anyio
async def test_values_malformed_entry_fails_restore_preflight() -> None:
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    target = new_conversation_record_v2(
        title="malformed",
        id="c_malformed_values",
        client_info={},
    )
    target.nodes[target.root_id].state[VALUES_STATE_KEY] = _values_entry(
        ["not", "a", "dict"]
    )
    chat = cast(_FakeChat, controller.chat)

    with pytest.raises(ValueError, match="shinychat:values"):
        await replay_exchange_record(controller, target)

    assert recorder.record is None
    assert chat.clear_messages_calls == 0


@pytest.mark.anyio
async def test_values_malformed_entry_on_active_path_fails_resubmit() -> None:
    controller, chat, _adapter, store, _first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[target].state[VALUES_STATE_KEY] = _values_entry(None)
    active_before = record.active_leaf

    with pytest.raises(ValueError, match="shinychat:values"):
        await controller.handle_resubmit(1, "retry", request_id="retry")

    assert record.active_leaf == active_before
    assert store.put_calls == []
    assert chat.actions == []


# ---------------------------------------------------------------------------
# Store format
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_values_file_store_round_trip_has_no_conversation_level_values(
    tmp_path: Any,
) -> None:
    store = FileConversationStore(dir=tmp_path)

    def save_callback(values: dict[str, Any]) -> None:
        values["filter"] = "west"

    controller, _ = _make_controller(
        store=store, save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "west")
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    partition = part()
    record_file = (
        tmp_path
        / sanitize_scope(partition.chat_id)
        / sanitize_scope(partition.scope)
        / record.id
        / "record.json"
    )
    raw = json.loads(record_file.read_text(encoding="utf-8"))
    # No conversation-level v2 values; the values live in node state.
    assert "values" not in raw
    root_state = raw["nodes"][record.root_id]["state"]
    assert root_state[VALUES_STATE_KEY] == {
        "kind": "values",
        "version": 1,
        "mode": "snapshot",
        "data": {"filter": "west"},
    }

    reloaded = await FileConversationStore(dir=tmp_path).get(
        partition, record.id
    )
    assert isinstance(reloaded, ConversationRecordV2)
    leaf = reloaded.active_leaf
    assert leaf is not None
    assert resolve_path_values(reloaded, leaf) == {"filter": "west"}


# ---------------------------------------------------------------------------
# v1 import
# ---------------------------------------------------------------------------


def test_v1_import_writes_values_on_active_leaf() -> None:
    record = new_conversation_record(title="v1 values")
    record.append_linear([{"role": "user", "content": "hello"}])
    record.values = {"a": 1}

    imported = import_v1_record(record)

    leaf = imported.active_leaf
    assert leaf is not None
    assert leaf != imported.root_id
    entry = imported.nodes[leaf].state[VALUES_STATE_KEY]
    assert (entry.kind, entry.version, entry.mode) == ("values", 1, "snapshot")
    assert entry.data == {"a": 1}
    assert resolve_path_values(imported, leaf) == {"a": 1}


def test_v1_import_writes_values_on_root_only_import() -> None:
    record = new_conversation_record(title="v1 root only")
    record.values = {"a": 1}

    imported = import_v1_record(record)

    # The active leaf of a root-only import is the synthesized root; the
    # imported values land there.
    assert imported.active_leaf == imported.root_id
    assert imported.nodes[imported.root_id].state[VALUES_STATE_KEY].data == {
        "a": 1
    }


def test_v1_import_writes_empty_values_explicitly() -> None:
    record = new_conversation_record(title="v1 empty values")

    imported = import_v1_record(record)

    leaf = imported.active_leaf
    assert leaf is not None
    # Even an empty v1 values object imports as an explicit empty entry on
    # the active leaf.
    assert imported.nodes[leaf].state[VALUES_STATE_KEY].data == {}


# ---------------------------------------------------------------------------
# on_navigate dispatch
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_on_navigate_edit_retry_regenerate_and_sibling_navigation() -> (
    None
):
    """Tool-like filter changes followed by every position move, through a
    real ``Chat``: reason, ids, target/previous values, and callback
    ordering before the resubmitted work starts."""
    store = InMemoryConversationStore()
    live = {"filter": "all"}

    def save_callback(values: dict[str, Any]) -> None:
        values["filter"] = live["filter"]

    controller, _ = _make_controller(
        store=store, save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_values_real_chat", history=False)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    events: list[tuple[Any, ...]] = []

    def navigate_callback(context: HistoryNavigateContext) -> None:
        events.append(
            (
                "navigate",
                context.reason,
                dict(context.values),
                dict(context.previous_values),
                context.exchange_id,
                context.previous_exchange_id,
            )
        )
        # The app syncs its tool-like filter from the target position.
        live["filter"] = str(context.values.get("filter", "all"))

    controller._navigate_callbacks.append(navigate_callback)

    async def drive_exchange(
        text: str, tool_filter: str, *, status: str = "ok"
    ) -> str:
        exchange_id = await chat._transcript.record_accepted_input_and_notify(
            _stored_message("user", text)
        )
        stream_id = f"stream-{exchange_id}"
        await chat._transcript.start_stream(
            stream_id=stream_id,
            entry=TranscriptEntry(message=_stored_message("assistant", "")),
            owner_task=None,
            exchange_id=exchange_id,
            send=_sent,
        )
        # What the provider observes when the response starts.
        events.append(("provider-filter", live["filter"]))
        live["filter"] = tool_filter
        await chat._transcript.end_stream(
            stream_id=stream_id,
            status=status,  # type: ignore[arg-type]
            error="failed" if status == "error" else None,
            send=_sent,
        )
        if status == "ok":
            await controller.on_response()
        return exchange_id

    ex_west = await drive_exchange("west", "west")
    record = recorder.record
    assert record is not None
    root_id = record.root_id
    assert record.nodes[root_id].state[VALUES_STATE_KEY].data == {
        "filter": "all"
    }
    assert record.nodes[ex_west].state[VALUES_STATE_KEY].data == {
        "filter": "west"
    }

    await controller.handle_edit(0, "east", request_id="edit-1")
    ex_east = await drive_exchange("east", "east")

    await controller.handle_navigate(0, "prev", request_id="nav-prev")
    assert record.active_leaf == ex_west
    await controller.handle_navigate(0, "next", request_id="nav-next")
    assert record.active_leaf == ex_east

    await controller.handle_resubmit(0, "regenerate", request_id="regen-1")
    ex_regen = await drive_exchange("east", "east", status="error")

    await controller.handle_resubmit(0, "retry", request_id="retry-1")

    assert events == [
        ("provider-filter", "all"),
        (
            "navigate",
            "edit",
            {"filter": "all"},
            {"filter": "west"},
            root_id,
            ex_west,
        ),
        # The synced target values were in place before the replacement
        # work started.
        ("provider-filter", "all"),
        (
            "navigate",
            "navigate",
            {"filter": "west"},
            {"filter": "east"},
            ex_west,
            ex_east,
        ),
        (
            "navigate",
            "navigate",
            {"filter": "east"},
            {"filter": "west"},
            ex_east,
            ex_west,
        ),
        (
            "navigate",
            "regenerate",
            {"filter": "all"},
            {"filter": "east"},
            root_id,
            ex_east,
        ),
        ("provider-filter", "all"),
        (
            "navigate",
            "retry",
            {"filter": "all"},
            {"filter": "east"},
            root_id,
            ex_regen,
        ),
    ]
    # Every abandoned branch keeps its recorded values.
    assert record.nodes[ex_west].state[VALUES_STATE_KEY].data == {
        "filter": "west"
    }
    assert record.nodes[ex_east].state[VALUES_STATE_KEY].data == {
        "filter": "east"
    }
    assert record.nodes[ex_regen].state[VALUES_STATE_KEY].data == {
        "filter": "east"
    }
    assert record.children_of(root_id) == [ex_west, ex_east, ex_regen]
    assert record.active_leaf == root_id


@pytest.mark.anyio
async def test_on_navigate_failure_keeps_move_notifies_once_and_continues():
    controller, chat, adapter, store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    record.nodes[original].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "original"}
    )
    record.nodes[replacement].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "replacement"}
    )
    # The live save callback agrees with the active exchange's recorded
    # values, so the leave capture keeps them.
    controller._save_callbacks.append(
        lambda values: values.update({"f": "replacement"})
    )

    calls: list[str] = []
    contexts: list[HistoryNavigateContext] = []

    def failing(_context: HistoryNavigateContext) -> None:
        calls.append("failing")
        raise RuntimeError("PRIVATE_HOOK_DETAIL")

    def observing(context: HistoryNavigateContext) -> None:
        calls.append("observing")
        contexts.append(context)

    controller._navigate_callbacks.extend([failing, observing])

    with (
        patch("shiny.ui.notification_show") as toast,
        pytest.warns(UserWarning, match="on_navigate callback failed"),
    ):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    # The failure warned the developer, showed one sanitized notification
    # (no raw exception text), and did not stop the remaining callback.
    assert calls == ["failing", "observing"]
    assert toast.call_count == 1
    toast_text = str(toast.call_args.args[0])
    assert "PRIVATE_HOOK_DETAIL" not in toast_text
    # The move is fully retained: leaf moved, model rewound, display
    # replayed, and the position persisted.
    assert record.active_leaf == original
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert [m["segments"][0]["content"] for m in chat.restored_messages] == [
        "first",
        "custom prefix",
        "original",
        "original reply",
    ]
    assert store.put_calls[-1][1].active_leaf == original
    assert len(contexts) == 1
    context = contexts[0]
    assert context.reason == "navigate"
    assert context.values == {"f": "original"}
    assert context.previous_values == {"f": "replacement"}
    assert context.exchange_id == original
    assert context.previous_exchange_id == replacement


@pytest.mark.anyio
async def test_on_navigate_cancellation_propagates_without_cleanup() -> None:
    controller, _chat, _adapter, store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None

    def cancelling(_context: HistoryNavigateContext) -> None:
        raise asyncio.CancelledError()

    controller._navigate_callbacks.append(cancelling)

    with pytest.raises(asyncio.CancelledError):
        await controller.handle_navigate(2, "prev", request_id="navigation")

    # Cancellation propagates with its identity and triggers no
    # restore-failure cleanup: the completed move is retained.
    assert record.active_leaf == original
    assert recorder.record is record
    assert controller._active_id_now() == record.id
    assert store.put_calls[-1][1].active_leaf == original


@pytest.mark.anyio
async def test_on_navigate_no_hooks_and_no_restore_on_moves() -> None:
    controller, _chat, _adapter, _store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None

    restored: list[dict[str, Any]] = []
    controller._restore_callbacks.append(restored.append)

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller.handle_navigate(2, "prev", request_id="navigation")

    assert record.active_leaf == original
    # No navigation hook means no dispatch, and an in-session move never
    # fires on_restore.
    assert restored == []


@pytest.mark.anyio
async def test_on_navigate_read_only_uses_recorded_values_no_live_capture():
    controller, _chat, _adapter, _store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    record.nodes[original].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "original"}
    )
    record.nodes[replacement].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "replacement"}
    )
    for node in record.nodes.values():
        node.state["shinychat:turns"].kind = "unsupported"

    save_calls: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        save_calls.append(dict(values))
        values["f"] = "LIVE"

    controller._save_callbacks.append(save_callback)
    contexts: list[HistoryNavigateContext] = []
    controller._navigate_callbacks.append(contexts.append)

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, record)
    assert recorder.read_only
    save_calls.clear()

    await controller.handle_navigate(2, "prev", request_id="navigation")

    # Recorded source/target values, no live capture anywhere on the move.
    assert save_calls == []
    assert len(contexts) == 1
    context = contexts[0]
    assert context.reason == "navigate"
    assert context.values == {"f": "original"}
    assert context.previous_values == {"f": "replacement"}
    assert record.nodes[replacement].state[VALUES_STATE_KEY].data == {
        "f": "replacement"
    }


@pytest.mark.anyio
async def test_on_navigate_contexts_are_detached_per_callback() -> None:
    controller, _chat, _adapter, _store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[original].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "original"}
    )
    record.nodes[replacement].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "replacement"}
    )
    # The live save callback agrees with the active exchange's recorded
    # values, so the leave capture keeps them.
    controller._save_callbacks.append(
        lambda values: values.update({"f": "replacement"})
    )

    observed: list[HistoryNavigateContext] = []

    def mutating(context: HistoryNavigateContext) -> None:
        context.values["f"] = "MUTATED"
        context.previous_values.clear()

    controller._navigate_callbacks.extend([mutating, observed.append])

    await controller.handle_navigate(2, "prev", request_id="navigation")

    # The second callback gets pristine snapshots, and the stored entries
    # are untouched by the first callback's mutations.
    assert len(observed) == 1
    assert observed[0].values == {"f": "original"}
    assert observed[0].previous_values == {"f": "replacement"}
    assert record.nodes[original].state[VALUES_STATE_KEY].data == {
        "f": "original"
    }
    assert record.nodes[replacement].state[VALUES_STATE_KEY].data == {
        "f": "replacement"
    }


@pytest.mark.anyio
async def test_on_restore_receives_selected_position_values_detached() -> None:
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store)

    target = new_conversation_record_v2(
        title="position values",
        id="c_position_values",
        client_info={},
    )
    target.nodes[target.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    target.open_exchange("n_0001", _stored_message("user", "one"))
    target.nodes["n_0001"].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "leaf"}
    )
    await store.put(part(), target)

    restored: list[dict[str, Any]] = []
    controller._restore_callbacks.append(restored.append)
    await controller.switch_to(target.id)

    assert restored == [{"f": "leaf"}]
    # The callback's dict is detached from the stored entry.
    restored[0]["f"] = "MUTATED"
    assert target.nodes["n_0001"].state[VALUES_STATE_KEY].data == {"f": "leaf"}


_VALUES_MATRIX = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tests/shared/history-values-fixture-matrix.json"
    ).read_text()
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case", _VALUES_MATRIX, ids=[case["name"] for case in _VALUES_MATRIX]
)
async def test_values_shared_capture_matrix(case: dict[str, Any]) -> None:
    assert case["exchanges"], "Capture matrix cases require an exchange"
    current = case["root"]

    def save_callback(values: dict[str, Any]) -> None:
        values.update(current)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    for index, (values, expected) in enumerate(
        zip(case["exchanges"], case["entries"], strict=True)
    ):
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", f"exchange {index}")
        )
        current = values
        assert await controller.save()

        record = recorder.record
        assert record is not None
        root = record.nodes[record.root_id].state[VALUES_STATE_KEY]
        assert root.model_dump(mode="json") == {
            "kind": "values",
            "version": 1,
            "mode": "snapshot",
            "data": case["root"],
        }
        entry = record.nodes[exchange_id].state.get(VALUES_STATE_KEY)
        if expected is None:
            assert entry is None
        else:
            assert entry is not None
            assert (entry.kind, entry.version, entry.mode) == (
                "values",
                1,
                "snapshot",
            )
            # JSON comparison distinguishes nested boolean and numeric values.
            assert json.dumps(entry.data, sort_keys=True) == json.dumps(
                expected, sort_keys=True
            )
        assert json.dumps(
            resolve_path_values(record, exchange_id), sort_keys=True
        ) == json.dumps(values, sort_keys=True)
