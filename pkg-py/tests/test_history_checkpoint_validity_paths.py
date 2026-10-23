"""Coherent restore paths retain structural state without offering it as a checkpoint."""

from typing import Any

import pytest
from shinychat._chat_transcript import TranscriptEntry
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_checkpoint_models import _prompt_adapter
from test_history_controller import _make_controller, _stored_message, part
from test_history_stream_persistence import (
    _assistant_message,
    _Backend,
    _chunk,
    _end_stream,
    _open_stream,
    _saved,
    _sent,
    _start_stream,
    _text,
    _wire,
)
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


def _entry(kind: str, data: Any, mode: Any = "snapshot") -> StateEntry:
    return StateEntry(kind=kind, version=1, mode=mode, data=data)


@pytest.mark.anyio
async def test_failed_root_is_not_a_writable_empty_draft_and_live_recovery_works(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    recorder = writer._exchange_recorder
    transcript = _wire(writer)
    await transcript.start_stream(
        stream_id="stream",
        exchange_id=None,
        owner_task=None,
        entry=TranscriptEntry(message=_stored_message("assistant", "")),
        send=_sent,
    )
    await _chunk(transcript, _assistant_message(_text("unpaired greeting")))
    record = recorder.record
    assert record is not None
    original = writer.adapter.get_turns_json

    def fail() -> Any:
        raise ValueError("root SDK failure")

    monkeypatch.setattr(writer.adapter, "get_turns_json", fail)
    with pytest.raises(ValueError, match="root SDK failure"):
        await _end_stream(transcript)
    assert record.nodes[record.root_id].checkpoint_state == "invalid"
    assert recorder._stream_exchanges == {}
    assert not await recorder.flush_pending()
    # Metadata persistence may retain an invalid point, never advertise it as
    # a valid empty starting checkpoint after its display is filtered out.
    async with recorder.lock:
        await recorder.persist_record_locked()
    frozen = (await _saved(backend, record.id)).model_dump_json()
    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(record.id)
    local = viewer._exchange_recorder.record
    assert local is not None
    assert local.nodes[local.root_id].messages == []
    assert local.nodes[local.root_id].checkpoint_state == "invalid"
    assert viewer._exchange_recorder.read_only
    assert not await viewer.save()
    await viewer.new_chat()
    assert (await _saved(backend, record.id)).model_dump_json() == frozen

    monkeypatch.setattr(writer.adapter, "get_turns_json", original)
    next_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "recovery")
    )
    await _start_stream(transcript, next_id)
    await _chunk(transcript, _assistant_message(_text("recovered")))
    await _end_stream(transcript)
    assert record.nodes[next_id].is_checkpoint
    assert await recorder.flush_pending()
    saved = await _saved(backend, record.id)
    assert saved.nodes[next_id].is_checkpoint
    assert saved.nodes[record.root_id].checkpoint_state == "invalid"


@pytest.mark.anyio
async def test_projection_keeps_sparse_and_delta_ancestors_and_two_valid_branches(
    backend: _Backend,
) -> None:
    source = new_conversation_record_v2(
        title="coherent paths", id="c_paths", client_info={}
    )
    root = source.root_id
    source.nodes[root].state[TURNS_STATE_KEY] = _entry(
        "turns", [{"role": "system", "content": "base"}]
    )
    source.nodes[root].state[SYSTEM_PROMPT_STATE_KEY] = _entry(
        "system_prompt", "base prompt"
    )
    source.open_exchange("prefix", _stored_message("user", "structural input"))
    prefix = source.nodes["prefix"]
    prefix.checkpoint = "invalid"
    prefix.state[TURNS_STATE_KEY] = _entry(
        "turns", [{"role": "user", "content": "structural input"}], "delta"
    )
    prefix.state[VALUES_STATE_KEY] = _entry("values", {"filter": "inherited"})
    prefix.state[SYSTEM_PROMPT_STATE_KEY] = _entry(
        "system_prompt", "needed prompt"
    )
    prefix.messages.append(
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "unchecked fragment"), icon=None
        )
    )
    for key in ("A", "B"):
        source.set_active_leaf("prefix")
        source.open_exchange(key, _stored_message("user", key))
        node = source.nodes[key]
        node.state[TURNS_STATE_KEY] = _entry(
            "turns", [{"role": "user", "content": key}], "delta"
        )
        source.append_message(
            key,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", key + " answer"), icon=None
            ),
        )
        node.checkpoint = "valid"
    source.nodes["prefix"].selected_child = "B"
    source.set_active_leaf("B")
    source.open_exchange("unfinished", _stored_message("user", "unfinished"))
    source.nodes["unfinished"].messages.append(
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "unsafe"), icon=None
        )
    )
    source.set_active_leaf(root)
    source.open_exchange("invalid_only", _stored_message("user", "discard"))
    source.nodes["invalid_only"].checkpoint = "invalid"
    source.set_active_leaf("unfinished")
    await backend.store.put(part(), source)
    frozen = source.model_dump_json()

    viewer, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await viewer._restore_initial_exchange_record(source, node_id="B")
    recorder = viewer._exchange_recorder
    local = recorder.record
    assert local is not None
    assert recorder.source_isolated and recorder.read_only
    assert set(local.nodes) == {root, "prefix", "A", "B"}
    assert local.active_leaf == "B"
    assert local.nodes["prefix"].selected_child == "B"
    assert local.nodes["prefix"].input == source.nodes["prefix"].input
    assert local.nodes["prefix"].state == source.nodes["prefix"].state
    assert local.nodes["prefix"].messages == []
    assert local.path_sibling_metadata() == {"B": (1, 2)}
    assert viewer.adapter.get_turns_json() == [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "structural input"},
        {"role": "user", "content": "B"},
    ]
    assert viewer.adapter.get_system_prompt() == "needed prompt"
    from shinychat._history_plan import resolve_path_values

    assert resolve_path_values(local, "B") == {"filter": "inherited"}
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        viewer._validate_resubmit_target(local, "B", "edit")
    await viewer.handle_navigate(1, "prev", request_id="A")
    assert local.active_leaf == "A"
    await viewer.handle_navigate(1, "next", request_id="B")
    assert local.active_leaf == "B"
    await viewer.new_chat()
    assert source.model_dump_json() == frozen
    assert (await _saved(backend, source.id)).model_dump_json() == frozen


@pytest.mark.anyio
async def test_sdk_failure_after_prompt_pins_commits_nothing(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, _ = _make_controller(store=backend.store, adapter=_prompt_adapter())
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    child = record.open_inputless_exchange()
    record.nodes[child].state[TURNS_STATE_KEY] = _entry(
        "turns", [{"role": "user", "content": "child"}], "delta"
    )
    record.set_active_leaf(node_id)
    before = record.model_dump_json()
    writer.adapter.set_system_prompt("replacement prompt")

    def fail() -> Any:
        raise ValueError("turns failure after prompt staging")

    monkeypatch.setattr(writer.adapter, "get_turns_json", fail)
    with pytest.raises(ValueError, match="after prompt staging"):
        await recorder.save_current()
    assert record.model_dump_json() == before
    assert SYSTEM_PROMPT_STATE_KEY not in record.nodes[child].state


@pytest.mark.anyio
@pytest.mark.parametrize("classification", ["candidate", "invalid"])
async def test_historical_position_and_retained_parent_guards(
    backend: _Backend,
    classification: Any,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[node_id].checkpoint = classification
    before = record.model_dump_json()
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        await recorder.persist_active_leaf_locked(record, node_id)
    target, parent = writer._validate_resubmit_target(record, node_id, "edit")
    assert target is record.nodes[node_id]
    assert parent == record.root_id
    assert record.model_dump_json() == before
    record.nodes[node_id].checkpoint = "valid"
    record.nodes[record.root_id].checkpoint = classification
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        writer._validate_resubmit_target(record, node_id, "edit")
