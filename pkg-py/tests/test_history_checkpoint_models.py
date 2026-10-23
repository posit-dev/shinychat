"""Model/display coherence at response and model-only save boundaries."""

from typing import Any, cast

import pytest
from pydantic import JsonValue
from shinychat._history_client import TurnsAdapter
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    ConversationRecordV2,
    StateEntry,
    TurnDict,
    new_conversation_record_v2,
)
from test_history_controller import (
    _make_controller,
    _stored_message,
    part,
)
from test_history_stream_persistence import (
    _assistant_message,
    _Backend,
    _chunk,
    _end_stream,
    _live,
    _open_stream,
    _saved,
    _text,
)
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


@pytest.mark.anyio
@pytest.mark.parametrize("boundary", ["disconnect", "leave"])
async def test_completed_checkpoint_retains_latest_model_only_changes(
    backend: _Backend,
    boundary: str,
) -> None:
    calls: list[dict[str, Any]] = []
    writer, _ = _make_controller(
        store=backend.store, save_callbacks=[calls.append]
    )
    transcript, exchange_id = await _open_stream(writer)
    await _chunk(transcript, _assistant_message(_text("displayed answer")))
    await _end_stream(transcript)
    record = writer._exchange_recorder.record
    assert record is not None
    conv_id = record.id
    expected = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "model-only change"},
    ]
    writer.adapter.set_turns_json(expected)
    calls.clear()

    if boundary == "disconnect":
        assert await writer._exchange_recorder.flush_pending()
    else:
        await writer.new_chat()

    assert calls == []
    saved = await backend.reader.get(part(), conv_id)
    assert isinstance(saved, ConversationRecordV2)
    assert [
        m.as_stored_message().content for m in saved.nodes[exchange_id].messages
    ] == ["displayed answer"]
    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(conv_id)
    assert viewer.adapter.get_turns_json() == expected
    assert not viewer._exchange_recorder.read_only


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["ok", "error", "cancelled"])
async def test_terminal_capture_failure_does_not_publish_display_without_model(
    backend: _Backend,
    status: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    transcript, exchange_id = await _open_stream(writer)
    record = writer._exchange_recorder.record
    assert record is not None
    checkpoint = await backend.reader.get(part(), record.id)
    assert isinstance(checkpoint, ConversationRecordV2)
    frozen = checkpoint.model_dump_json()
    await _chunk(transcript, _assistant_message(_text("live response")))
    original = writer.adapter.get_turns_json

    def unavailable() -> Any:
        raise ValueError("model capture unavailable")

    monkeypatch.setattr(writer.adapter, "get_turns_json", unavailable)
    with pytest.raises(ValueError, match="model capture unavailable"):
        await writer._exchange_recorder.stream_finished("stream", status, None)

    saved = await backend.reader.get(part(), record.id)
    assert isinstance(saved, ConversationRecordV2)
    assert saved.model_dump_json() == frozen
    assert saved.nodes[exchange_id].status == "pending"
    assert saved.nodes[exchange_id].messages == []
    assert writer._exchange_recorder._stream_exchanges == {}
    monkeypatch.setattr(writer.adapter, "get_turns_json", original)
    # Terminal delivery is not a retry queue. A duplicate notification after
    # the capture failure cannot publish a response from a stale association.
    await writer._exchange_recorder.stream_finished("stream", status, None)
    terminal = await backend.reader.get(part(), record.id)
    assert isinstance(terminal, ConversationRecordV2)
    assert terminal.model_dump_json() == frozen


@pytest.mark.anyio
async def test_completed_leaf_with_pending_root_saves_latest_model_on_disconnect(
    backend: _Backend,
) -> None:
    # A terminal inputless descendant is a coherent checkpoint even if an
    # old root still has its original pending status. Do not "repair" that
    # fixture status: restore already admits this completed position.
    from shinychat._history_types import (
        CapturedMessage,
        StateEntry,
        new_conversation_record_v2,
    )
    from test_history_controller import _stored_message

    record = new_conversation_record_v2(
        title="Completed inputless descendant",
        id="c_pending_root",
        client_info={},
    )
    record.nodes[record.root_id].state["shinychat:turns"] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    leaf = record.open_inputless_exchange()
    record.append_message(
        leaf,
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "completed"), icon=None
        ),
    )
    record.nodes[leaf].state["shinychat:turns"] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "assistant", "content": "completed"}],
    )
    await backend.store.put(part(), record)
    writer, _ = _make_controller(store=backend.store)
    await writer.switch_to(record.id)
    assert not writer._exchange_recorder.source_isolated
    assert not writer._exchange_recorder.read_only
    latest: list[TurnDict] = [
        {"role": "assistant", "content": "completed"},
        {"role": "assistant", "content": "latest model-only change"},
    ]
    writer.adapter.set_turns_json(latest)

    assert await writer._exchange_recorder.flush_pending()

    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(record.id)
    assert viewer.adapter.get_turns_json() == latest


PREFIX: list[TurnDict] = [
    {"role": "user", "content": "prefix question"},
    {"role": "assistant", "content": "prefix answer"},
]
SAVED_PROMPT = "saved prompt"


class _PromptClient:
    """A turn-level client with a chatlas-style `system_prompt` property."""

    def __init__(self) -> None:
        self.system_prompt: str | None = "live prompt"
        self.turns: list[dict[str, Any]] = []

    def get_turns(self) -> list[dict[str, Any]]:
        return [dict(turn) for turn in self.turns]

    def set_turns(self, turns: list[dict[str, Any]]) -> None:
        self.turns = [dict(turn) for turn in turns]


class _PromptAdapter(TurnsAdapter):
    """The real `TurnsAdapter` over a prompt-capable client.

    The recorder registers system-prompt hooks only for a `TurnsAdapter`
    whose client exposes a prompt, so a plain fake adapter would not exercise
    the prompt entries these tests assert.
    """

    def __init__(self) -> None:
        self.client = _PromptClient()
        super().__init__(self.client)


def _prompt_adapter() -> Any:
    """A `_PromptAdapter` typed as `Any`.

    `_make_controller` annotates its adapter as the turn-level fake. The real
    `TurnsAdapter` is what these tests need, so pass it through untyped.
    """
    return _PromptAdapter()


def _branch_turns(question: str, answer: str) -> list[TurnDict]:
    return [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]


def _legacy_structural_record(conv_id: str) -> ConversationRecordV2:
    """A pending structural root holding the shared prefix and saved prompt.

    The root has no input and no messages, so it is a structural base rather
    than an accepted request. Two terminal children each own only their own
    turn delta. The active leaf is the first child.
    """
    record = new_conversation_record_v2(
        title="Legacy branches", id=conv_id, client_info={}
    )
    root = record.nodes[record.root_id]
    root.state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=cast(JsonValue, PREFIX)
    )
    root.state[SYSTEM_PROMPT_STATE_KEY] = StateEntry(
        kind="system_prompt", version=1, mode="snapshot", data=SAVED_PROMPT
    )
    for exchange_id, label in (
        ("n_0001", "A"),
        ("n_0002", "B"),
    ):
        record.set_active_leaf(record.root_id)
        record.open_exchange(
            exchange_id, _stored_message("user", f"branch {label}")
        )
        record.nodes[exchange_id].state[TURNS_STATE_KEY] = StateEntry(
            kind="turns",
            version=1,
            mode="delta",
            data=cast(
                JsonValue, _branch_turns(f"branch {label}", f"answer {label}")
            ),
        )
        record.append_message(
            exchange_id,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", f"answer {label}"), icon=None
            ),
        )
    record.set_active_leaf("n_0001")
    return record


async def _select_leaf(backend: _Backend, conv_id: str, leaf: str) -> None:
    """Move the saved active pointer to ``leaf`` without touching any node."""
    record = await backend.reader.get(part(), conv_id)
    assert isinstance(record, ConversationRecordV2)
    record.set_active_leaf(leaf)
    await backend.store.put(part(), record)


def _assert_pending_nodes_store_no_model_state(
    record: ConversationRecordV2,
) -> None:
    pending = [
        node_id
        for node_id, node in record.nodes.items()
        if node.status == "pending"
    ]
    assert pending
    for node_id in pending:
        node = record.nodes[node_id]
        assert node.messages == []
        assert TURNS_STATE_KEY not in node.state
        assert SYSTEM_PROMPT_STATE_KEY not in node.state


@pytest.mark.anyio
async def test_legacy_structural_root_restores_one_terminal_sibling(
    backend: _Backend,
) -> None:
    conv_id = "c_legacy_siblings"
    await backend.store.put(part(), _legacy_structural_record(conv_id))

    viewer, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await viewer.switch_to(conv_id)

    assert viewer.adapter.get_turns_json() == [
        *PREFIX,
        *_branch_turns("branch A", "answer A"),
    ]
    assert viewer.adapter.get_system_prompt() == SAVED_PROMPT
    assert not viewer._exchange_recorder.read_only
    assert not viewer._exchange_recorder.source_isolated


@pytest.mark.anyio
async def test_model_only_disconnect_snapshot_serves_both_siblings(
    backend: _Backend,
) -> None:
    conv_id = "c_legacy_disconnect"
    await backend.store.put(part(), _legacy_structural_record(conv_id))
    writer, _ = _make_controller(store=backend.store, adapter=_prompt_adapter())
    await writer.switch_to(conv_id)
    branch_a = [*PREFIX, *_branch_turns("branch A", "answer A")]
    assert writer.adapter.get_turns_json() == branch_a
    assert writer.adapter.get_system_prompt() == SAVED_PROMPT

    latest = [
        *branch_a,
        {"role": "assistant", "content": "model-only update"},
    ]
    writer.adapter.set_turns_json(latest)
    assert await writer._exchange_recorder.flush_pending()

    saved = await _saved(backend, conv_id)
    updated = saved.nodes["n_0001"].state[TURNS_STATE_KEY]
    assert updated.mode == "snapshot"
    assert updated.data == latest
    assert saved.nodes["n_0001"].state[SYSTEM_PROMPT_STATE_KEY].data == (
        SAVED_PROMPT
    )
    assert saved.nodes["n_0002"].state[TURNS_STATE_KEY].mode == "delta"
    assert saved.nodes[saved.root_id].state[TURNS_STATE_KEY].data == PREFIX

    await _select_leaf(backend, conv_id, "n_0002")
    old_sibling, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await old_sibling.switch_to(conv_id)
    assert old_sibling.adapter.get_turns_json() == [
        *PREFIX,
        *_branch_turns("branch B", "answer B"),
    ]
    assert old_sibling.adapter.get_system_prompt() == SAVED_PROMPT

    await _select_leaf(backend, conv_id, "n_0001")
    updated_branch, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await updated_branch.switch_to(conv_id)
    assert updated_branch.adapter.get_turns_json() == latest
    assert updated_branch.adapter.get_system_prompt() == SAVED_PROMPT


@pytest.mark.anyio
async def test_live_partial_response_then_new_input_then_rename_stores_no_pending_model_state(
    backend: _Backend,
) -> None:
    values = {"v": "old"}

    def save_values(out: dict[str, Any]) -> None:
        out["v"] = values["v"]

    writer, _ = _make_controller(
        store=backend.store,
        adapter=_prompt_adapter(),
        save_callbacks=[save_values],
    )
    transcript, old_id = await _open_stream(writer)
    conv_id = _live(writer._exchange_recorder).id
    # The client retains the partial assistant turn of the open response.
    writer.adapter.set_turns_json(
        [
            *writer.adapter.get_turns_json(),
            {"role": "assistant", "content": "partial old"},
        ]
    )
    await _chunk(transcript, _assistant_message(_text("partial old")))
    # A legacy writer may have left model entries on the unresolved node. No
    # save may store them: the old response has no coherent model state.
    legacy_old = _live(writer._exchange_recorder).nodes[old_id]
    legacy_old.state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "assistant", "content": "legacy partial"}],
    )
    legacy_old.state[SYSTEM_PROMPT_STATE_KEY] = StateEntry(
        kind="system_prompt",
        version=1,
        mode="snapshot",
        data="legacy prompt",
    )

    values["v"] = "new"
    new_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )

    saved = await _saved(backend, conv_id)
    _assert_pending_nodes_store_no_model_state(saved)
    assert saved.active_leaf == new_id
    new_input = saved.nodes[new_id].input
    assert new_input is not None
    assert new_input.content == "second"
    # Sparse values: the old node inherits the root's "old" and records none.
    assert saved.nodes[new_id].state[VALUES_STATE_KEY].data == {"v": "new"}
    assert "partial old" not in saved.model_dump_json()
    assert "legacy" not in saved.model_dump_json()

    await writer.rename(conv_id, "Renamed live")

    renamed = await _saved(backend, conv_id)
    assert renamed.title == "Renamed live"
    assert renamed.title_source == "user"
    _assert_pending_nodes_store_no_model_state(renamed)
    assert "partial old" not in renamed.model_dump_json()
    assert "legacy" not in renamed.model_dump_json()

    # The older response may finish after another input was accepted. Its
    # actual checkpoint is saved without settling the newer pending leaf.
    terminal_model: list[TurnDict] = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "finished old"},
    ]
    writer.adapter.set_turns_json(terminal_model)
    await _chunk(transcript, _assistant_message(_text("finished old")))
    await _end_stream(transcript)
    terminal = await _saved(backend, conv_id)
    assert terminal.active_leaf == new_id
    assert terminal.nodes[new_id].status == "pending"
    assert terminal.nodes[new_id].messages == []
    assert TURNS_STATE_KEY not in terminal.nodes[new_id].state
    assert terminal.nodes[old_id].status == "ok"
    assert terminal.nodes[old_id].state[TURNS_STATE_KEY].data == terminal_model


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("unsupported", "error"),
    [(float("nan"), ValueError), (object(), TypeError)],
    ids=["nonfinite", "non-json"],
)
async def test_unsupported_retained_client_turn_blocks_new_input_admission(
    backend: _Backend,
    unsupported: Any,
    error: type[Exception],
) -> None:
    writer, _ = _make_controller(store=backend.store, adapter=_prompt_adapter())
    transcript, old_id = await _open_stream(writer)
    recorder = writer._exchange_recorder
    conv_id = _live(recorder).id
    await _chunk(transcript, _assistant_message(_text("partial old")))
    supported = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "partial old"},
    ]
    writer.adapter.set_turns_json(
        [*supported, {"role": "assistant", "content": unsupported}]
    )
    before = (await _saved(backend, conv_id)).model_dump_json()

    with pytest.raises(error):
        await transcript.record_accepted_input_and_notify(
            _stored_message("user", "second")
        )

    live = _live(recorder)
    assert set(live.nodes) == {live.root_id, old_id}
    assert live.active_leaf == old_id
    assert (await _saved(backend, conv_id)).model_dump_json() == before

    # Once the client turns are supported again, the same input is admitted.
    writer.adapter.set_turns_json(supported)
    new_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "second")
    )
    saved = await _saved(backend, conv_id)
    assert saved.active_leaf == new_id
    new_input = saved.nodes[new_id].input
    assert new_input is not None
    assert new_input.content == "second"
    _assert_pending_nodes_store_no_model_state(saved)


async def _complete_append(
    writer: Any, transcript: Any, exchange_id: str, text: str
) -> None:
    from shinychat._chat_transcript import TranscriptEntry
    from test_history_stream_persistence import _sent

    transcript.set_capture_callbacks(
        on_message_committed=writer._exchange_recorder.message_committed,
        on_accepted_input=writer._exchange_recorder.accepted_input,
        on_stream_started=writer._exchange_recorder.stream_started,
        on_stream_updated=writer._exchange_recorder.stream_updated,
        on_stream_finished=writer._exchange_recorder.stream_finished,
    )
    await transcript.append(
        TranscriptEntry(message=_stored_message("assistant", text)),
        exchange_id=exchange_id,
        send=_sent,
    )


@pytest.mark.anyio
async def test_complete_assistant_append_restores_full_model_and_settles(
    backend: _Backend,
) -> None:
    from test_history_stream_persistence import _open_input

    writer, _ = _make_controller(store=backend.store)
    transcript, exchange_id = await _open_input(writer)
    expected = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "complete"},
    ]
    writer.adapter.set_turns_json(expected)
    await _complete_append(writer, transcript, exchange_id, "complete")
    recorder = writer._exchange_recorder
    assert await recorder.response_settled()
    record = _live(recorder)
    assert await recorder.settle_bookmark_state_id(
        record.id, exchange_id, "complete-bookmark"
    ) == (True, None)
    saved = await _saved(backend, record.id)
    assert saved.response_count == 1
    assert saved.bookmark_state_id == "complete-bookmark"
    assert saved.nodes[exchange_id].status == "ok"
    assert [
        m.as_stored_message().content for m in saved.nodes[exchange_id].messages
    ] == ["complete"]
    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(record.id)
    assert viewer.adapter.get_turns_json() == expected
    assert not viewer._exchange_recorder.read_only


@pytest.mark.anyio
@pytest.mark.parametrize("second", ["append", "stream"])
async def test_independent_response_preserves_previous_checkpoint_and_isolates_reload(
    backend: _Backend,
    second: str,
) -> None:
    from test_history_stream_persistence import _open_input, _start_stream

    writer, _ = _make_controller(store=backend.store)
    transcript, exchange_id = await _open_input(writer)
    first_model = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "first"},
    ]
    writer.adapter.set_turns_json(first_model)
    await _complete_append(writer, transcript, exchange_id, "first")
    recorder = writer._exchange_recorder
    record = _live(recorder)
    first = record.nodes[exchange_id].model_dump(
        exclude={"children", "selected_child"}
    )
    second_model = [*first_model, {"role": "assistant", "content": "second"}]
    writer.adapter.set_turns_json(second_model)
    if second == "append":
        await _complete_append(writer, transcript, exchange_id, "second")
    else:
        await _start_stream(transcript, exchange_id)
        await _chunk(transcript, _assistant_message(_text("second")))
        async with recorder.lock:
            await recorder.rename_active_locked(
                record.id, "metadata during response"
            )
        saved = await _saved(backend, record.id)
        assert (
            saved.nodes[exchange_id].model_dump(
                exclude={"children", "selected_child"}
            )
            == first
        )
        assert saved.active_leaf is not None
        assert saved.nodes[saved.active_leaf].status == "pending"
        viewer, _ = _make_controller(store=backend.reader)
        await viewer.switch_to(record.id)
        assert viewer._exchange_recorder.read_only
        assert viewer.adapter.get_turns_json() == first_model
        with pytest.raises(RuntimeError, match="read-only"):
            await viewer.rename(record.id, "viewer overwrite")
        with pytest.raises(RuntimeError, match="read-only"):
            await viewer.delete(record.id)
        assert not await viewer._exchange_recorder.flush_pending()
        await _end_stream(transcript)
    saved = await _saved(backend, record.id)
    assert (
        saved.nodes[exchange_id].model_dump(
            exclude={"children", "selected_child"}
        )
        == first
    )
    assert saved.active_leaf is not None
    assert saved.active_leaf != exchange_id
    assert saved.nodes[saved.active_leaf].input is None
    assert saved.nodes[saved.active_leaf].status == "ok"
    assert [
        m.as_stored_message().content
        for m in saved.nodes[saved.active_leaf].messages
    ] == ["second"]
    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(record.id)
    assert viewer.adapter.get_turns_json() == second_model
    assert not viewer._exchange_recorder.read_only


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["capture", "store"])
async def test_complete_append_failure_keeps_live_display_and_safe_saved_checkpoint(
    backend: _Backend,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_history_stream_persistence import _open_input

    writer, _ = _make_controller(store=backend.store)
    transcript, exchange_id = await _open_input(writer)
    recorder = writer._exchange_recorder
    record = _live(recorder)
    before = (await _saved(backend, record.id)).model_dump_json()
    expected = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "live"},
    ]
    writer.adapter.set_turns_json(expected)
    if failure == "capture":

        def unavailable() -> Any:
            raise ValueError("capture failed")

        monkeypatch.setattr(writer.adapter, "get_turns_json", unavailable)
    else:
        backend.control.failures.append(ValueError("store failed"))
    with pytest.raises(ValueError, match=f"{failure} failed"):
        await _complete_append(writer, transcript, exchange_id, "live")
    assert [
        m.as_stored_message().content
        for m in record.nodes[exchange_id].messages
    ] == ["live"]
    assert record.nodes[exchange_id].status == (
        "pending" if failure == "capture" else "ok"
    )
    assert transcript.read()[-1].message.content == "live"
    assert record.response_count == 0
    assert (await _saved(backend, record.id)).model_dump_json() == before
    if failure == "capture":
        assert not await recorder.response_settled()
        assert not await recorder.flush_pending()
        async with recorder.lock:
            await recorder.rename_active_locked(record.id, "metadata")
        saved = await _saved(backend, record.id)
        assert saved.nodes[exchange_id].status == "pending"
        assert saved.nodes[exchange_id].messages == []
        assert TURNS_STATE_KEY not in saved.nodes[exchange_id].state
    else:
        assert record.nodes[exchange_id].state[TURNS_STATE_KEY].data == expected


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["user", "system"])
async def test_non_assistant_output_does_not_open_independent_response_child(
    backend: _Backend,
    role: str,
) -> None:
    from shinychat._chat_transcript import TranscriptEntry
    from test_history_stream_persistence import _open_input

    writer, _ = _make_controller(store=backend.store)
    transcript, exchange_id = await _open_input(writer)
    await _complete_append(writer, transcript, exchange_id, "first")
    recorder = writer._exchange_recorder
    record = _live(recorder)
    before = set(record.nodes)
    await recorder.message_committed(
        exchange_id,
        TranscriptEntry(message=_stored_message(role, "display only")),
    )
    assert set(record.nodes) == before
    assert record.active_leaf == exchange_id
    assert record.nodes[exchange_id].status == "ok"


@pytest.mark.anyio
async def test_initial_bookmark_into_unresolved_source_scrubs_pending_siblings(
    backend: _Backend,
) -> None:
    writer, _ = _make_controller(
        store=backend.store, adapter=_prompt_adapter()
    )
    writer.adapter.set_system_prompt(SAVED_PROMPT)
    transcript, coherent_id = await _open_stream(writer)
    coherent_model = [
        *writer.adapter.get_turns_json(),
        {"role": "assistant", "content": "coherent answer"},
    ]
    writer.adapter.set_turns_json(coherent_model)
    await _chunk(transcript, _assistant_message(_text("coherent answer")))
    await _end_stream(transcript)
    record = _live(writer._exchange_recorder)
    record.set_active_leaf(record.root_id)
    pending_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "unfinished sibling")
    )
    from test_history_stream_persistence import _start_stream

    await _start_stream(transcript, pending_id)
    source = await _saved(backend, record.id)
    source.nodes[pending_id].messages.append(
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "unsafe legacy partial"), icon=None
        )
    )
    source.nodes[pending_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "assistant", "content": "unsafe legacy model"}],
    )
    await backend.store.put(part(), source)
    frozen = source.model_dump_json()

    viewer, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await viewer._restore_initial_exchange_record(source, node_id=coherent_id)

    local = _live(viewer._exchange_recorder)
    assert viewer._exchange_recorder.source_isolated
    assert viewer._exchange_recorder.read_only
    assert local.active_leaf == coherent_id
    assert viewer.adapter.get_turns_json() == coherent_model
    assert viewer.adapter.get_system_prompt() == SAVED_PROMPT
    assert (
        local.nodes[coherent_id].messages == source.nodes[coherent_id].messages
    )
    assert local.nodes[pending_id].input is None
    assert local.nodes[pending_id].messages == []
    assert local.nodes[pending_id].state == {}
    await viewer.handle_navigate(0, "next", request_id="unsafe-sibling")
    assert local.active_leaf == record.root_id
    assert not await viewer._exchange_recorder.flush_pending()
    assert source.model_dump_json() == frozen
    assert (await _saved(backend, record.id)).model_dump_json() == frozen

    terminal_model: list[TurnDict] = [{"role": "assistant", "content": "writer finished"}]
    writer.adapter.set_turns_json(terminal_model)
    await _chunk(transcript, _assistant_message(_text("writer finished")))
    await _end_stream(transcript)
    saved = await _saved(backend, record.id)
    assert saved.nodes[pending_id].status == "ok"
    assert saved.nodes[pending_id].state[TURNS_STATE_KEY].data == terminal_model
    assert source.model_dump_json() == frozen


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [KeyboardInterrupt, BaseException])
async def test_ended_stream_drops_association_on_fatal_capture(
    backend: _Backend,
    failure: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    await _open_stream(writer)
    recorder = writer._exchange_recorder
    assert recorder._stream_exchanges

    def fatal() -> Any:
        raise failure("fatal model capture")

    monkeypatch.setattr(writer.adapter, "get_turns_json", fatal)
    with pytest.raises(failure, match="fatal model capture"):
        await recorder.stream_finished("stream", "ok", None)
    assert recorder._stream_exchanges == {}
