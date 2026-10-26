"""Checkpoint validity is independent of provider outcome and display."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, AsyncIterator, cast

import pytest
from shiny import reactive
from shiny.session import session_context
from shinychat import Chat
from shinychat._history_recorder import _ModelCaptureError
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV2,
    ExchangeNode,
    StateEntry,
    new_conversation_record_v2,
    utcnow,
)
from test_history_checkpoint_models import _prompt_adapter
from test_history_controller import (
    _make_controller,
    _RealChatSession,
    _stored_message,
)
from test_history_stream_persistence import (
    _assistant_message,
    _Backend,
    _chunk,
    _end_stream,
    _open_stream,
    _saved,
    _start_stream,
    _text,
)
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


@pytest.mark.parametrize("status", ["ok", "error", "cancelled", "pending"])
def test_legacy_classification_is_explicitly_an_assumption(status: Any) -> None:
    node = ExchangeNode.model_validate(
        {
            "parent_id": "root",
            "created_at": "2026-10-22T00:00:00Z",
            "status": status,
        }
    )
    assert node.checkpoint is None
    assert node.checkpoint_state == (
        "candidate" if status == "pending" else "valid"
    )
    assert ExchangeNode(created_at=utcnow(), status="pending").is_checkpoint
    node.checkpoint = "invalid"
    assert not node.is_checkpoint
    assert node.model_dump(mode="json")["checkpoint"] == "invalid"


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["ok", "error", "cancelled"])
@pytest.mark.parametrize("app", ["unchanged", "raise", "unsupported"])
async def test_terminal_candidate_requires_reliable_app_settlement(
    backend: _Backend,
    status: Any,
    app: str,
) -> None:
    failing = False
    calls: list[str] = []

    def save(values: dict[str, Any]) -> None:
        calls.append("save")
        if failing and app == "raise":
            raise RuntimeError("app exploded")
        if failing and app == "unsupported":
            values["bad"] = object()

    writer, _ = _make_controller(store=backend.store, save_callbacks=[save])
    transcript, node_id = await _open_stream(writer)
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    previous_root = record.nodes[record.root_id].model_dump_json()
    await _chunk(transcript, _assistant_message(_text("local answer")))
    calls.clear()
    failing = True
    await _end_stream(transcript, status=None if status == "ok" else status)
    assert calls == []  # No on_save inside the still-running response task.
    assert record.nodes[node_id].checkpoint_state == "candidate"
    assert record.nodes[node_id].status == status
    if app == "unchanged":
        assert await recorder.response_settled()
        assert record.nodes[node_id].is_checkpoint
        assert VALUES_STATE_KEY not in record.nodes[node_id].state
    else:
        with pytest.warns(UserWarning, match="app-state values capture failed"):
            assert await recorder.response_settled()
        assert record.nodes[node_id].checkpoint_state == "invalid"

        async def unexpected_success(record: ConversationRecordV2) -> None:
            pytest.fail("success callback")

        writer.on_response_saved = unexpected_success
        await writer.on_response()
    assert record.nodes[record.root_id].model_dump_json() == previous_root
    assert (
        record.nodes[node_id].messages[-1].as_stored_message().content
        == "local answer"
    )
    saved = await _saved(backend, record.id)
    assert (
        saved.nodes[node_id].checkpoint_state
        == record.nodes[node_id].checkpoint_state
    )


@pytest.mark.anyio
async def test_model_failure_cannot_be_promoted_by_app_success(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer, _ = _make_controller(
        store=backend.store, save_callbacks=[lambda values: None]
    )
    transcript, node_id = await _open_stream(writer)
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    before = deepcopy(record.nodes[node_id].state)
    monkeypatch.setattr(
        writer.adapter,
        "get_turns_json",
        lambda: (_ for _ in ()).throw(ValueError("SDK failed")),
    )
    with pytest.raises(_ModelCaptureError, match="SDK failed"):
        await recorder.stream_finished("stream", "ok", None)
    assert record.nodes[node_id].status == "ok"
    assert record.nodes[node_id].checkpoint_state == "invalid"
    assert record.nodes[node_id].state == before
    assert recorder._stream_exchanges == {}
    assert not await recorder.response_settled()
    assert not await recorder.save_current()


@pytest.mark.anyio
async def test_new_input_supersedes_candidate_without_recapturing_its_model(
    backend: _Backend,
) -> None:
    writer, _ = _make_controller(
        store=backend.store, save_callbacks=[lambda values: None]
    )
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    frame = deepcopy(record.nodes[node_id].state)
    writer.adapter.set_turns_json([{"role": "user", "content": "new context"}])
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "next")
    )
    assert record.nodes[node_id].checkpoint_state == "invalid"
    assert record.nodes[node_id].state == frame
    assert not await recorder.response_settled()
    await _start_stream(transcript, second)
    await _end_stream(transcript)
    assert await recorder.response_settled()
    assert record.nodes[second].is_checkpoint
    assert not recorder.read_only  # Live follow-up remains available.


@pytest.mark.anyio
async def test_explicit_recapture_failure_preserves_all_frames_and_child_pins(
    backend: _Backend,
) -> None:
    failing = False

    def save(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("explicit app failed")
        values["saved"] = "old"

    writer, _ = _make_controller(
        store=backend.store, adapter=_prompt_adapter(), save_callbacks=[save]
    )
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    assert await recorder.response_settled()
    record = recorder.record
    assert record is not None
    record.set_active_leaf(node_id)
    child = record.open_inputless_exchange()
    record.nodes[child].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "assistant", "content": "child delta"}],
    )
    record.set_active_leaf(node_id)
    before = record.model_dump_json()
    durable = (await _saved(backend, record.id)).model_dump_json()
    writer.adapter.set_turns_json(
        [{"role": "assistant", "content": "replacement"}]
    )
    writer.adapter.set_system_prompt("changed")
    failing = True
    with pytest.raises(RuntimeError, match="explicit app failed"):
        await recorder.save_current()
    assert recorder.record is record
    assert record.model_dump_json() == before
    assert (await _saved(backend, record.id)).model_dump_json() == durable
    assert record.nodes[node_id].is_checkpoint
    assert record.nodes[child].state[TURNS_STATE_KEY].mode == "delta"
    assert SYSTEM_PROMPT_STATE_KEY not in record.nodes[child].state


@pytest.mark.anyio
async def test_required_custom_capture_hook_runs_at_settlement(
    backend: _Backend,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    recorder = writer._exchange_recorder
    calls: list[str] = []

    async def custom(context: Any) -> StateEntry:
        assert recorder.record is live
        calls.append(context.reason)
        raise RuntimeError("required hook failed")

    transcript, node_id = await _open_stream(writer)
    live = recorder.record
    recorder._register_capture_hook("app:required", custom)
    await _end_stream(transcript)
    assert calls == []
    with pytest.warns(UserWarning, match="required hook failed"):
        assert await recorder.response_settled()
    assert calls == ["node_close"]
    assert recorder.record is not None
    assert recorder.record.nodes[node_id].checkpoint_state == "invalid"


@pytest.mark.anyio
async def test_postflush_on_save_can_read_extended_task_result(
    backend: _Backend,
    request: pytest.FixtureRequest,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    recorder = writer._exchange_recorder
    session = _RealChatSession()
    with session_context(cast(Any, session)):
        chat = Chat("postflush_result", history=False)
    request.addfinalizer(chat.destroy)
    writer.chat = chat  # type: ignore[assignment]
    chat._transcript.set_capture_callbacks(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )
    chat._on_response_settled(writer.on_response)
    await chat._transcript.record_accepted_input_and_notify(
        _stored_message("user", "question")
    )
    results: list[str] = []

    def save(values: dict[str, Any]) -> None:
        result = chat.latest_message_stream.result()
        results.append(result)
        values["result"] = result

    writer._save_callbacks.append(save)

    async def response() -> AsyncIterator[str]:
        yield "answer"

    with session_context(cast(Any, session)), reactive.isolate():
        task = await chat.append_message_stream(response())
    assert task._task is not None
    await asyncio.wait_for(task._task, timeout=2)
    await reactive.flush()
    assert results == ["answer"]
    assert recorder.record is not None
    leaf = recorder.record.active_leaf
    assert leaf is not None
    assert recorder.record.nodes[leaf].is_checkpoint
    assert recorder.record.nodes[leaf].state[VALUES_STATE_KEY].data == {
        "result": "answer"
    }


def test_portable_checkpoint_classification_fixture() -> None:
    fixture = json.loads(
        (
            Path(__file__).parents[2]
            / "tests/shared/history-checkpoint-validity-matrix.json"
        ).read_text()
    )
    assert fixture["schema_version"] == 2
    for case in fixture["cases"]:
        node = ExchangeNode.model_validate(
            {"created_at": "2026-10-22T00:00:00Z", **case["node"]}
        )
        assert node.checkpoint_state == case["expected"], case["name"]
        assert (
            ExchangeNode.model_validate_json(
                node.model_dump_json()
            ).checkpoint_state
            == case["expected"]
        )
    record = new_conversation_record_v2(title="new writes", client_info={})
    record.open_exchange("request", _stored_message("user", "input"))
    serialized = json.loads(record.model_dump_json())
    assert serialized["schema_version"] == 2
    assert serialized["nodes"][record.root_id]["checkpoint"] == "valid"
    assert serialized["nodes"]["request"]["checkpoint"] == "candidate"


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["unchanged", "nonfinite", "raise"])
async def test_replaced_values_hook_is_a_required_validated_app_capture(
    backend: _Backend,
    outcome: str,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    transcript, node_id = await _open_stream(writer)
    recorder = writer._exchange_recorder
    calls: list[str] = []

    def capture(context: Any) -> StateEntry | None:
        calls.append(context.node_id)
        if outcome == "raise":
            raise RuntimeError("custom values hook failed")
        if outcome == "nonfinite":
            return StateEntry(
                kind="values",
                version=1,
                mode="snapshot",
                data={"invalid": float("nan")},
            )
        return None

    recorder._register_capture_hook(VALUES_STATE_KEY, capture)
    await _end_stream(transcript)
    assert recorder.record is not None
    assert recorder.record.nodes[node_id].checkpoint_state == "candidate"
    assert calls == []
    before = deepcopy(recorder.record.nodes[node_id].state)
    if outcome == "unchanged":
        assert await recorder.response_settled()
        assert recorder.record.nodes[node_id].is_checkpoint
    else:
        with pytest.warns(UserWarning, match="app-state values capture failed"):
            assert await recorder.response_settled()
        assert recorder.record.nodes[node_id].checkpoint_state == "invalid"
        assert recorder.record.nodes[node_id].state == before
    assert calls == [node_id]
