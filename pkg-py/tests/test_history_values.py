# Per-exchange application values (`shinychat:values`) and the public
# `on_navigate` dispatch (shinychat#t829): sparse capture semantics, shared
# parent anchoring, store format, v1 import, validation, and the callback
# contract through production controller/transcript paths.

import asyncio
import json
import warnings
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

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
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
    TurnDict,
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


def _finish_pending(record: ConversationRecordV2 | None) -> None:
    """Terminal-finish every pending exchange.

    A completed response leaves no pending node, and explicit saves and
    response settlement refuse a pending active leaf. Fixtures that accept
    input without streaming finish it here so the record is coherent.
    """
    assert record is not None
    for node_id, node in record.nodes.items():
        if node.status == "pending":
            record.finish_exchange(node_id, "ok", None)
            record.nodes[node_id].checkpoint = "valid"


def _values_entry(data: Any) -> StateEntry:
    return StateEntry(kind="values", version=1, mode="snapshot", data=data)


def _capture_values_on(recorder: Any, node_id: str) -> None:
    """Explicit values capture on ``node_id``, which need not be the leaf.

    Accepted inputs capture values only at the node they open, so a shared
    parent is recaptured explicitly through this helper. That recapture is
    what pins existing children to the parent's previous value.
    """
    record = recorder.record
    entry = recorder._capture_values_at(node_id)
    node = record.nodes[node_id]
    if entry is None:
        node.state.pop(VALUES_STATE_KEY, None)
    else:
        node.state[VALUES_STATE_KEY] = entry


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

    _finish_pending(recorder.record)
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
    _finish_pending(recorder.record)
    current = {"filter": "b"}
    assert await controller.save()
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    _finish_pending(recorder.record)
    current = {"filter": "a"}
    assert await controller.save()
    third = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "three")
    )
    _finish_pending(recorder.record)
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
    _finish_pending(recorder.record)
    current = {"nested": [1, 1]}
    assert await controller.save()
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    _finish_pending(recorder.record)
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
async def test_values_capture_reads_reactive_state_after_stream_task_terminal() -> None:
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

    await controller.on_response()
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
    _finish_pending(recorder.record)
    # Unchanged from the root: the exchange inherits and records nothing.
    await controller.on_response()
    await controller.handle_edit(0, "alternative", request_id="edit-1")
    sibling = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "alternative")
    )
    _finish_pending(recorder.record)
    await controller.on_response()

    live["v"] = "changed"
    await controller.handle_edit(0, "alternative two", request_id="edit-2")
    replacement = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "alternative two")
    )
    _finish_pending(recorder.record)

    record = recorder.record
    assert record is not None
    # Accepted inputs capture values only at the node they open: the new
    # exchange records the changed value and the root keeps its old one.
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "v": "same"
    }
    assert record.nodes[replacement].state[VALUES_STATE_KEY].data == {
        "v": "changed"
    }
    assert VALUES_STATE_KEY not in record.nodes[abandoned].state
    assert VALUES_STATE_KEY not in record.nodes[sibling].state
    # The explicit recapture of the shared parent pins the existing children
    # that inherited its previous value before the parent changed.
    _capture_values_on(recorder, record.root_id)
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "v": "changed"
    }
    assert record.nodes[abandoned].state[VALUES_STATE_KEY].data == {"v": "same"}
    assert resolve_path_values(record, abandoned) == {"v": "same"}
    assert record.nodes[sibling].state[VALUES_STATE_KEY].data == {"v": "same"}
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

    # The accepted input recorded only its own node; the shared parent keeps
    # its implicit default until it is recaptured explicitly.
    assert VALUES_STATE_KEY not in record.nodes[first].state
    assert resolve_path_values(record, first) == {}
    assert record.nodes[replacement].state[VALUES_STATE_KEY].data == {"f": "x"}
    _capture_values_on(recorder, first)

    assert record.nodes[first].state[VALUES_STATE_KEY].data == {"f": "x"}
    # Pinned explicit empty object: the abandoned target still resolves to
    # the implicit value it had before the parent first recorded.
    assert record.nodes[target].state[VALUES_STATE_KEY].data == {}
    assert resolve_path_values(record, target) == {}
    assert resolve_path_values(record, replacement) == {"f": "x"}


@pytest.mark.anyio
async def test_values_pending_predecessor_is_validated_not_captured() -> None:
    # An unresolved predecessor is validated when the next input arrives, but
    # it never becomes a checkpoint: the live value lands on the new node.
    live = {"v": "same"}

    def save_callback(values: dict[str, Any]) -> None:
        values["v"] = live["v"]

    controller, _ = _make_controller(
        store=InMemoryConversationStore(),
        save_callbacks=[save_callback],
    )
    recorder = controller._exchange_recorder
    transcript = _wire_transcript(recorder)

    pending = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    live["v"] = "changed"
    following = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )

    record = recorder.record
    assert record is not None
    assert record.nodes[pending].status == "pending"
    assert VALUES_STATE_KEY not in record.nodes[pending].state
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "v": "same"
    }
    assert record.nodes[following].state[VALUES_STATE_KEY].data == {
        "v": "changed"
    }
    assert resolve_path_values(record, pending) == {"v": "same"}


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
        (  # Unknown objects stay loudly rejected by the pydantic coercion.
            {"obj": object()},
            ValueError,
            "Unable to serialize unknown type",
        ),
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
    _finish_pending(recorder.record)

    current = bad
    # The explicit save stays strict: an invalid payload raises to the
    # caller (controller.save() is the chat.history.save() path).
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


# Rich app values must keep the old pydantic-compatible encoding: the
# pre-t829 path stored values in a ``dict[str, Any]`` pydantic field and
# wrote them with ``model_dump_json``, which serializes date/datetime,
# Decimal, UUID, tuples, sets, and bytes. Common Shiny values ride on
# these: ``input.date()`` returns a ``datetime.date`` and
# ``input.date_range()`` returns a tuple of dates.
_RICH_VALUES: dict[str, Any] = {
    "d": date(2024, 1, 31),
    "dt": datetime(2024, 1, 31, 12, 30, 45),
    "dr": (date(2024, 1, 1), date(2024, 2, 1)),
    "n": Decimal("1.25"),
    "u": UUID("12345678-1234-5678-1234-567812345678"),
    "s": {1, 2},
    "b": b"raw",
}


def _rich_expected() -> dict[str, Any]:
    """The old ``model_dump_json`` encoding of ``_RICH_VALUES``."""
    return {
        "d": "2024-01-31",
        "dt": "2024-01-31T12:30:45",
        "dr": ["2024-01-01", "2024-02-01"],
        "n": "1.25",
        "u": "12345678-1234-5678-1234-567812345678",
        "s": [1, 2],
        "b": "raw",
    }


def _assert_rich_encoding(data: Any) -> None:
    expected = _rich_expected()
    assert {k: v for k, v in data.items() if k != "s"} == {
        k: v for k, v in expected.items() if k != "s"
    }
    # Sets serialize to a list whose order is not guaranteed.
    assert sorted(data["s"]) == [1, 2]


@pytest.mark.anyio
async def test_values_rich_app_values_keep_old_encoding() -> None:
    def save_callback(values: dict[str, Any]) -> None:
        values.update(_RICH_VALUES)

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hi")
    )
    await controller.save()

    record = recorder.record
    assert record is not None
    _assert_rich_encoding(
        record.nodes[record.root_id].state[VALUES_STATE_KEY].data
    )
    # The descendant capture deduped against the rich root entry and
    # inherits; resolution returns the detached JSON forms.
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state
    _assert_rich_encoding(resolve_path_values(record, exchange_id))


@pytest.mark.anyio
async def test_values_rich_file_store_round_trip(tmp_path: Any) -> None:
    store = FileConversationStore(dir=tmp_path)

    def save_callback(values: dict[str, Any]) -> None:
        values.update(_RICH_VALUES)

    controller, _ = _make_controller(
        store=store, save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    await transcript.record_accepted_input_and_notify(
        _stored_message("user", "hi")
    )
    await controller.save()
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
    # On disk, the rich values are already their JSON forms -- a file
    # written by the old model_dump_json path and reloaded agree.
    _assert_rich_encoding(
        raw["nodes"][record.root_id]["state"]["shinychat:values"]["data"]
    )

    reloaded = await FileConversationStore(dir=tmp_path).get(
        partition, record.id
    )
    assert isinstance(reloaded, ConversationRecordV2)
    leaf = reloaded.active_leaf
    assert leaf is not None
    _assert_rich_encoding(resolve_path_values(reloaded, leaf))


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
@pytest.mark.parametrize(
    "data",
    [
        ["not", "a", "dict"],
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": -float("inf")},
    ],
    ids=["not-an-object", "nan", "infinity", "negative-infinity"],
)
async def test_values_malformed_entry_fails_restore_preflight(
    data: Any,
) -> None:
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    target = new_conversation_record_v2(
        title="malformed",
        id="c_malformed_values",
        client_info={},
    )
    target.nodes[target.root_id].state[VALUES_STATE_KEY] = _values_entry(data)
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


def test_v1_import_normalizes_rich_values() -> None:
    record = new_conversation_record(title="v1 rich values")
    record.append_linear([{"role": "user", "content": "hello"}])
    # A typed/custom store can hand the v1 record rich app values; the
    # same pure normalizer the live capture uses must convert them, so
    # StateEntry's JsonValue validation accepts them.
    record.values = dict(_RICH_VALUES)

    imported = import_v1_record(record)

    leaf = imported.active_leaf
    assert leaf is not None
    entry = imported.nodes[leaf].state[VALUES_STATE_KEY]
    assert (entry.kind, entry.version, entry.mode) == (
        "values",
        1,
        "snapshot",
    )
    _assert_rich_encoding(entry.data)
    # The import is detached: later mutation of the v1 record does not
    # reach the imported entry.
    record.values["d"] = date(1999, 12, 31)
    _assert_rich_encoding(imported.nodes[leaf].state[VALUES_STATE_KEY].data)


def test_v1_import_rejects_nonfinite_values_loudly() -> None:
    record = new_conversation_record(title="v1 nan values")
    record.values = {"x": float("nan")}

    # Non-finite floats are refused after normalization, never silently
    # coerced to null, exactly as on the live capture path.
    with pytest.raises(ValueError, match="Out of range float values"):
        import_v1_record(record)


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
    _finish_pending(record)
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    record.nodes[original].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "original"}
    )
    record.nodes[replacement].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "replacement"}
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
    _finish_pending(record)

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


# ---------------------------------------------------------------------------
# Auto-vs-explicit capture error policy
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["raise", "nan"])
async def test_values_settlement_failure_warns_and_invalidates_terminal_checkpoint(
    failure: str, tmp_path: Path
) -> None:
    """APP failure keeps the terminal outcome and SDK frame, not a valid checkpoint."""
    store = FileConversationStore(dir=tmp_path)
    live: dict[str, Any] = {"filter": "all"}
    failing = False

    def save_callback(values: dict[str, Any]) -> None:
        if failing:
            if failure == "raise":
                raise RuntimeError("callback exploded")
            values["filter"] = live["filter"]
            values["pi"] = float("nan")
            return
        values["filter"] = live["filter"]

    controller, _ = _make_controller(
        store=store, save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("history_values_stream_failure", history=False)
    controller.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    exchange_id = await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "west")
    )
    stream_id = "stream"
    await chat._transcript.start_stream(
        stream_id=stream_id,
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    live["filter"] = "west"
    expected_turns: list[TurnDict] = [
        {"role": "user", "content": "west"},
        {"role": "assistant", "content": "answer west"},
    ]
    controller.adapter.set_turns_json(expected_turns)

    failing = True
    await chat._transcript.end_stream(
        stream_id=stream_id, status=None, error=None, send=_sent
    )
    with pytest.warns(
        UserWarning, match="Automatic app-state values capture failed"
    ):
        assert not await recorder.response_settled()

    record = recorder.record
    assert record is not None
    # The exchange finalized instead of staying in streaming status, and
    # the model-state capture was unaffected by the values failure.
    assert record.nodes[exchange_id].status == "ok"
    assert record.nodes[exchange_id].error is None
    assert (
        record.nodes[exchange_id].state[TURNS_STATE_KEY].data == expected_turns
    )
    # Stream tracking was released before the post-flush values capture.
    assert stream_id not in recorder._stream_exchanges
    # The root's recorded values are retained; the failed capture at the
    # exchange left no own entry, so inheritance answers.
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "filter": "all"
    }
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state
    assert resolve_path_values(record, exchange_id) == {"filter": "all"}
    # The finished record persisted with its finalized node.
    persisted = await store.get(part(), record.id)
    assert isinstance(persisted, ConversationRecordV2)
    assert persisted is not record
    assert persisted.nodes[exchange_id].status == "ok"
    assert persisted.nodes[exchange_id].checkpoint_state == "invalid"
    assert (
        persisted.nodes[exchange_id].state[TURNS_STATE_KEY].data
        == expected_turns
    )

    # The chat continues after the fix: the new exchange's own capture
    # records cleanly.
    failing = False
    live["filter"] = "east"
    second = await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "east")
    )
    assert second != exchange_id
    assert record.nodes[second].state[VALUES_STATE_KEY].data == {
        "filter": "east"
    }


@pytest.mark.anyio
async def test_values_leave_never_invokes_on_save_during_navigation() -> None:
    """Leaving a position for a sibling is model-only: on_save never runs,
    so a failing callback neither warns nor blocks the move, and the
    navigation context carries the recorded values of both positions."""
    controller, _chat, _adapter, _store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    _finish_pending(record)
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    record.nodes[original].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "original"}
    )
    record.nodes[replacement].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "replacement"}
    )

    saves: list[str] = []

    def failing_save(values: dict[str, Any]) -> None:
        saves.append("save")
        raise RuntimeError("leave must not run on_save")

    controller._save_callbacks.append(failing_save)
    contexts: list[HistoryNavigateContext] = []
    controller._navigate_callbacks.append(contexts.append)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller.handle_navigate(2, "prev", request_id="navigation")

    assert saves == []
    assert record.active_leaf == original
    assert record.nodes[replacement].state[VALUES_STATE_KEY].data == {
        "f": "replacement"
    }
    assert len(contexts) == 1
    context = contexts[0]
    assert context.reason == "navigate"
    assert context.values == {"f": "original"}
    assert context.previous_values == {"f": "replacement"}


@pytest.mark.anyio
async def test_values_leave_never_invokes_on_save_during_retry() -> None:
    """Retrying leaves the target model-only: on_save never runs, and the
    target keeps its recorded values for the navigation context."""
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    # Retry only applies to a failed exchange: the target finished in error.
    record.finish_exchange(target, "error", "failed")
    record.nodes[target].checkpoint = "valid"
    _finish_pending(record)
    record.nodes[target].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "target"}
    )

    saves: list[str] = []

    def failing_save(values: dict[str, Any]) -> None:
        saves.append("save")
        raise RuntimeError("leave must not run on_save")

    controller._save_callbacks.append(failing_save)
    contexts: list[HistoryNavigateContext] = []
    controller._navigate_callbacks.append(contexts.append)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await controller.handle_resubmit(1, "retry", request_id="retry")

    assert saves == []
    assert record.active_leaf == first
    assert chat.actions
    assert record.nodes[target].state[VALUES_STATE_KEY].data == {"f": "target"}
    assert len(contexts) == 1
    context = contexts[0]
    assert context.reason == "retry"
    assert context.previous_values == {"f": "target"}


@pytest.mark.anyio
async def test_values_root_close_failure_warns_and_continues() -> None:
    failing = True

    def save_callback(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("root capture exploded")
        values["filter"] = "fixed"

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.warns(
        UserWarning, match="Automatic app-state values capture failed"
    ):
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", "hi")
        )

    record = recorder.record
    assert record is not None
    assert exchange_id in record.nodes
    # Known fallback when there is no entry: the root stays missing and
    # resolution answers {}.
    assert VALUES_STATE_KEY not in record.nodes[record.root_id].state
    assert resolve_path_values(record, exchange_id) == {}

    # After the fix, the new exchange's own capture records normally.
    failing = False
    again = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "again")
    )
    assert record.nodes[again].state[VALUES_STATE_KEY].data == {
        "filter": "fixed"
    }


@pytest.mark.anyio
async def test_values_automatic_settlement_warns_and_invalidates_candidate() -> None:
    def save_callback(values: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.warns(
        UserWarning, match="Automatic app-state values capture failed"
    ):
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", "hi")
        )
    _finish_pending(recorder.record)
    assert recorder.record is not None
    recorder.record.nodes[exchange_id].checkpoint = "candidate"

    # Automatic settlement warns, retains recoverable values, and refuses validity.
    with pytest.warns(
        UserWarning, match="Automatic app-state values capture failed"
    ):
        assert await recorder.response_settled() is False
    record = recorder.record
    assert record is not None
    assert record.response_count == 1
    assert record.nodes[exchange_id].checkpoint_state == "invalid"
    # The failed capture kept no entry, so the exchange still resolves.
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state


@pytest.mark.anyio
async def test_values_explicit_save_raises_callback_failure() -> None:
    def save_callback(values: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    with pytest.warns(
        UserWarning, match="Automatic app-state values capture failed"
    ):
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", "hi")
        )
    _finish_pending(recorder.record)

    # The explicit save (chat.history.save()) is strict: the callback
    # failure raises to the caller instead of warning.
    with pytest.raises(RuntimeError, match="boom"):
        await controller.save()
    record = recorder.record
    assert record is not None
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state


@pytest.mark.anyio
@pytest.mark.parametrize("leave", ["switch", "new_chat", "disconnect"])
async def test_values_leaving_never_invokes_on_save(leave: str) -> None:
    """Leaving (switch, New chat, or session disconnect) is a model-only
    save: on_save never runs, so a value changed since the last capture is
    not recorded and no capture warning fires."""
    live = {"filter": "west"}
    saves: list[str] = []

    def save_callback(values: dict[str, Any]) -> None:
        saves.append(live["filter"])
        values["filter"] = live["filter"]

    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store, save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "west")
    )
    _finish_pending(recorder.record)
    record = recorder.record
    assert record is not None

    target = new_conversation_record_v2(
        title="target", id="c_leave_target", client_info={}
    )
    await store.put(part(), target)
    live["filter"] = "changed"
    leaves = {
        "switch": lambda: controller.switch_to(target.id),
        "new_chat": controller.new_chat,
        "disconnect": recorder.flush_pending,
    }

    saves_before = len(saves)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await leaves[leave]()

    assert len(saves) == saves_before
    # The changed value was never captured at the position being left.
    assert VALUES_STATE_KEY not in record.nodes[exchange_id].state
    assert resolve_path_values(record, exchange_id) == {"filter": "west"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model_only", "expected_saves", "expected_values"),
    [(True, 0, None), (False, 1, {"filter": "changed"})],
    ids=["model-only-skips-values", "full-cycle-runs-on-save"],
)
async def test_capture_state_model_only_filters_values(
    model_only: bool,
    expected_saves: int,
    expected_values: dict[str, Any] | None,
) -> None:
    live = {"filter": "west"}
    saves: list[str] = []

    def save_callback(values: dict[str, Any]) -> None:
        saves.append(live["filter"])
        values["filter"] = live["filter"]

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    _finish_pending(recorder.record)
    record = recorder.record
    assert record is not None

    saves.clear()
    live["filter"] = "changed"
    controller.adapter.set_turns_json([{"role": "user", "content": "one"}])
    await recorder.capture_state_locked(
        exchange_id, "node_close", model_only=model_only
    )

    node = record.nodes[exchange_id]
    # Turns are captured either way; only the values hook is filtered.
    assert node.state[TURNS_STATE_KEY].data == [
        {"role": "user", "content": "one"}
    ]
    assert len(saves) == expected_saves
    entry = node.state.get(VALUES_STATE_KEY)
    assert (None if entry is None else entry.data) == expected_values


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error", [KeyboardInterrupt(), asyncio.CancelledError()]
)
async def test_values_capture_fatal_error_propagates(
    error: BaseException,
) -> None:
    # Only ordinary Exceptions are isolated; cancellation and fatal
    # errors propagate even on automatic capture points.
    def save_callback(values: dict[str, Any]) -> None:
        raise error

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(on_accepted_input=recorder.accepted_input)

    with pytest.raises(type(error)) as caught:
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "hi")
        )
    assert caught.value is error


@pytest.mark.anyio
async def test_values_retitle_read_only_suppresses_live_capture() -> None:
    """Read-only suppression wins even on retitle: the title metadata
    write stays live, but live app values never replace the saved
    record's."""
    controller, _chat, _adapter, _store, original, replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[record.root_id].state[VALUES_STATE_KEY] = _values_entry(
        {"f": "root"}
    )
    for node in record.nodes.values():
        node.state["shinychat:turns"].kind = "unsupported"

    with pytest.warns(UserWarning, match="read-only"):
        await replay_exchange_record(controller, record)
    assert recorder.read_only

    save_calls: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        save_calls.append(dict(values))
        values["f"] = "LIVE"

    controller._save_callbacks.append(save_callback)

    assert record.title_source != "user"
    assert await recorder.retitle_active_locked(record, "Retitled") is True
    assert record.title == "Retitled"
    # Title metadata writes stay live; the live app-value capture never
    # ran, and the saved values are untouched.
    assert save_calls == []
    assert record.nodes[record.root_id].state[VALUES_STATE_KEY].data == {
        "f": "root"
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
    _finish_pending(target)
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
        _finish_pending(recorder.record)
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
