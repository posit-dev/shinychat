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
    monkeypatch.setattr(writer.adapter, "get_turns_json", original)
    await writer._exchange_recorder.stream_finished("stream", status, None)
    terminal = await backend.reader.get(part(), record.id)
    assert isinstance(terminal, ConversationRecordV2)
    assert terminal.nodes[exchange_id].status == status
    assert [
        m.as_stored_message().content
        for m in terminal.nodes[exchange_id].messages
    ] == ["live response"]
    viewer, _ = _make_controller(store=backend.reader)
    await viewer.switch_to(record.id)
    assert viewer.adapter.get_turns_json() == original()
    assert not viewer._exchange_recorder.read_only


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
