"""Regression tests for selected not-sent eligibility and browse recovery."""

from typing import Any, cast

import pytest
from shiny import reactive
from shinychat._chat_transcript import TranscriptEntry
from shinychat._chat_types import ReadOnlyReason
from shinychat._history import ChatHistory
from shinychat._history_store import InMemoryConversationStore
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    StateEntry,
)
from test_history_controller import (
    _FakeAdapter,
    _FakeChat,
    _make_controller,
    _make_v2_navigation_controller,
    _make_v2_resubmit_real_chat,
    _seed_resubmit_transcript,
    _stored_message,
    _wire_resubmit_capture,
)
from test_history_node_first import _record_with_browsable_failure
from test_history_node_first_review import _view
from test_history_system_prompt import _make_prompt_controller


@pytest.mark.anyio
async def test_recovery_selected_not_sent_blocks_submission_without_record_lock() -> (
    None
):
    controller, _ = _make_controller()
    record, _original, failed = _record_with_browsable_failure()
    recorder = controller._exchange_recorder
    recorder.install_restored_record(record)
    history = ChatHistory(cast(Any, controller.chat))
    history._controller = controller
    history._initial_history_initialized = True

    # A selected-node restriction is derived even without a record-wide flag.
    assert not recorder.read_only
    assert not history._history_submission_admitted()
    assert record.active_leaf == failed


@pytest.mark.anyio
async def test_recovery_selected_not_sent_publishes_position_capabilities() -> (
    None
):
    controller, _ = _make_controller()
    record, _original, _failed = _record_with_browsable_failure()
    controller._exchange_recorder.install_restored_record(record)

    await controller.send_history_update()
    action = cast(_FakeChat, controller.chat).actions[-1]
    assert action["active_read_only"] is True
    assert "active_read_only_reason" not in action
    assert action["active_can_resubmit"] is True


@pytest.mark.anyio
async def test_recovery_pending_staged_retry_is_admitted_through_chat(
    request: pytest.FixtureRequest,
) -> None:
    view = _view(request, InMemoryConversationStore())
    await view.initialize()
    record, original, failed = _record_with_browsable_failure()
    await view.controller._restore_initial_exchange_record(record)
    recorder = view.controller._exchange_recorder
    selected = recorder.record
    assert selected is not None
    # Exercise admission with no conversation-wide restriction: once a
    # replacement is staged, eligibility must follow the pending selection.
    recorder.install_restored_record(selected)
    staged_observations: list[tuple[str, bool, bool]] = []

    def observe_pending(_values: dict[str, Any]) -> None:
        leaf = selected.active_leaf
        assert leaf is not None
        node = selected.nodes[leaf]
        staged_observations.append(
            (
                node.status,
                node.not_sent is True,
                view.chat.history._history_submission_admitted(),
            )
        )

    view.controller._restore_callbacks.append(observe_pending)
    await view.controller.handle_resubmit(0, "retry", request_id="retry-failed")

    staged = selected.active_leaf
    assert staged is not None and staged not in (original, failed)
    assert selected.nodes[staged].parent_id == selected.root_id
    assert staged_observations == [("pending", False, True)]
    assert selected.nodes[failed].not_sent is True
    with reactive.isolate():
        user_input = view.chat.user_input()
        assert user_input is not None and user_input.text == "B-prime"
    assert view.chat._transcript.open_exchange_id == staged


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("not_sent", "checkpoint", "status"),
    [
        (None, "invalid", "error"),
        (True, "valid", "error"),
        (True, "invalid", "ok"),
    ],
)
async def test_recovery_other_errors_are_not_selected_not_sent(
    not_sent: bool | None, checkpoint: Any, status: Any
) -> None:
    controller, _ = _make_controller()
    record, _original, failed = _record_with_browsable_failure()
    record.nodes[failed].not_sent = not_sent
    record.nodes[failed].checkpoint = checkpoint
    record.nodes[failed].status = status
    controller._exchange_recorder.install_restored_record(record)
    history = ChatHistory(cast(Any, controller.chat))
    history._controller = controller
    history._initial_history_initialized = True

    assert history._history_submission_admitted()


@pytest.mark.anyio
async def test_recovery_selected_not_sent_suppresses_direct_capture() -> None:
    controller, _ = _make_controller()
    record, _original, failed = _record_with_browsable_failure()
    recorder = controller._exchange_recorder
    recorder.install_restored_record(record)
    before = record.model_dump()

    captured = await recorder.capture_state_locked(failed, "node_close")

    assert captured is False
    assert record.model_dump() == before


@pytest.mark.anyio
async def test_recovery_selected_not_sent_suppresses_content_and_stream() -> (
    None
):
    controller, store = _make_controller()
    record, _original, failed = _record_with_browsable_failure()
    recorder = controller._exchange_recorder
    recorder.install_restored_record(record)
    before = record.model_dump()
    writes = len(store.put_calls)
    entry = TranscriptEntry(message=_stored_message("assistant", "poison"))

    await recorder.message_committed(None, entry)
    await recorder.stream_started("new-stream", None, entry)
    await recorder.stream_updated("new-stream", entry)
    await recorder.stream_finished("new-stream", "ok", None)

    assert record.model_dump() == before
    assert record.active_leaf == failed
    assert len(store.put_calls) == writes


@pytest.mark.anyio
async def test_recovery_selected_not_sent_does_not_record_followup_input() -> (
    None
):
    controller, store = _make_controller()
    record, _original, _failed = _record_with_browsable_failure()
    recorder = controller._exchange_recorder
    recorder.install_restored_record(record)
    before = record.model_dump()
    writes = len(store.put_calls)

    committed: list[bool] = []
    with pytest.raises(RuntimeError, match="not-sent position"):
        await recorder.accepted_input(
            "followup",
            _stored_message("user", "no"),
            lambda: committed.append(True),
        )

    assert committed == []
    assert record.model_dump() == before
    assert len(store.put_calls) == writes


@pytest.mark.anyio
async def test_recovery_app_failed_browse_reapplies_model_before_clearing() -> (
    None
):
    controller, chat, adapter, store, original, outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    recorder.mark_read_only("app_restore_failed")
    before = record.nodes[outgoing].model_dump()
    adapter.turns = [{"role": "user", "content": "poisoned outgoing"}]
    observed: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    record.nodes[original].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "original"}
    )
    controller._restore_callbacks.append(
        lambda values: observed.append((dict(values), list(adapter.turns)))
    )

    await controller.handle_navigate(2, "prev", request_id="recover")

    expected_turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    assert record.active_leaf == original
    assert adapter.turns == expected_turns
    assert observed == [({"tab": "original"}, expected_turns)]
    assert record.nodes[outgoing].model_dump() == before
    assert not recorder.read_only
    assert chat.actions[-1].get("active_read_only", False) is False
    assert len(store.put_calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["app_restore_failed", "model_unavailable"])
async def test_recovery_app_callback_may_replace_live_model_context(
    reason: ReadOnlyReason,
) -> None:
    controller, chat, adapter, _store, original, outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    recorder.mark_read_only(reason)
    record.nodes[original].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "original"}
    )
    target_state = record.nodes[original].model_dump()["state"]
    outgoing_state = record.nodes[outgoing].model_dump()["state"]
    adapter.turns = [{"role": "user", "content": "untrusted outgoing"}]
    callback_inputs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    app_state: dict[str, Any] = {}
    model_override = [{"role": "user", "content": "model-only app context"}]

    def restore(values: dict[str, Any]) -> None:
        callback_inputs.append((dict(values), list(adapter.turns)))
        app_state.update(values)
        adapter.set_turns_json(model_override)

    controller._restore_callbacks.append(restore)

    await controller.handle_navigate(2, "prev", request_id="app-model-override")

    assert callback_inputs == [
        (
            {"tab": "original"},
            [
                {"role": "system", "content": "bootstrap"},
                {"role": "user", "content": "first"},
                {"role": "user", "content": "original"},
            ],
        )
    ]
    assert app_state == {"tab": "original"}
    assert adapter.turns == model_override
    assert record.active_leaf == original
    assert record.nodes[original].model_dump()["state"] == target_state
    assert record.nodes[outgoing].model_dump()["state"] == outgoing_state
    assert not recorder.read_only
    assert recorder.continuation_allowed
    assert chat.actions[-1].get("active_read_only", False) is False


@pytest.mark.anyio
@pytest.mark.parametrize("reason", ["app_restore_failed", "model_unavailable"])
@pytest.mark.parametrize(
    ("source_prompt", "expected_prompt", "prompt_calls"),
    [(None, "live override", []), ("different", "recorded", ["recorded"])],
)
async def test_recovery_app_failed_browse_keeps_prompt_override_and_custom_hook(
    source_prompt: str | None,
    expected_prompt: str,
    prompt_calls: list[str],
    reason: ReadOnlyReason,
) -> None:
    source, _chat, _adapter, _store, original, outgoing = (
        _make_v2_navigation_controller()
    )
    record = source._exchange_recorder.record
    assert record is not None
    record.nodes[record.root_id].state[TURNS_STATE_KEY].data = []
    record.nodes[original].state[TURNS_STATE_KEY].data = [
        {"role": "user", "content": "model-only original"}
    ]
    record.nodes[record.root_id].state[SYSTEM_PROMPT_STATE_KEY] = StateEntry(
        kind="system_prompt", version=1, mode="snapshot", data="recorded"
    )
    if source_prompt is not None:
        record.nodes[outgoing].state[SYSTEM_PROMPT_STATE_KEY] = StateEntry(
            kind="system_prompt", version=1, mode="snapshot", data=source_prompt
        )
    record.nodes["exchange-first"].state["app:custom"] = StateEntry(
        kind="custom", version=1, mode="snapshot", data={"ready": True}
    )
    controller, client = _make_prompt_controller(prompt="live override")
    recorder = controller._exchange_recorder
    recorder.install_restored_record(
        record, read_only=True, read_only_reason=reason
    )
    controller._active_id.set(record.id)
    events: list[str] = []
    recorder._register_rewind_hook(
        "app:custom", lambda _ctx: events.append("custom")
    )
    controller._restore_callbacks.append(
        lambda _values: events.append("restore")
    )
    client.turns = [{"role": "user", "content": "poisoned"}]

    await controller.handle_navigate(2, "prev", request_id="recover-prompt")

    assert record.active_leaf == original
    assert client.turns == [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "model-only original"},
    ]
    assert client.system_prompt == expected_prompt
    assert client.prompt_calls() == prompt_calls
    assert events == ["custom", "restore"]
    assert not recorder.read_only


@pytest.mark.anyio
async def test_recovery_unavailable_target_model_cannot_clear_app_failure() -> (
    None
):
    controller, _chat, adapter, _store, original, _outgoing = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[original].state[TURNS_STATE_KEY].kind = "unsupported"
    recorder.mark_read_only("app_restore_failed")
    adapter.turns = [{"role": "user", "content": "poisoned"}]
    restores: list[dict[str, Any]] = []
    controller._restore_callbacks.append(lambda v: restores.append(dict(v)))

    await controller.handle_navigate(2, "prev", request_id="unavailable")

    assert record.active_leaf == original
    assert restores == [{}]
    assert adapter.turns == [{"role": "user", "content": "poisoned"}]
    assert recorder.read_only
    assert recorder.read_only_reason == "app_restore_failed"
    assert not recorder.continuation_allowed
    assert not controller._can_resubmit_active()


@pytest.mark.anyio
async def test_recovery_unavailable_detour_keeps_app_failure_recoverable() -> (
    None
):
    controller, chat, adapter, _store, unavailable, compatible = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[unavailable].state[TURNS_STATE_KEY].kind = "unsupported"
    record.nodes[unavailable].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "unavailable"}
    )
    record.nodes[compatible].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "compatible"}
    )
    compatible_state = record.nodes[compatible].model_dump()["state"]
    sentinel_turns = [{"role": "user", "content": "poisoned outgoing"}]
    adapter.turns = list(sentinel_turns)
    recorder.mark_read_only("app_restore_failed")
    observations: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    controller._restore_callbacks.append(
        lambda values: observations.append((dict(values), list(adapter.turns)))
    )

    await controller.handle_navigate(2, "prev", request_id="unavailable-detour")

    assert record.active_leaf == unavailable
    assert adapter.turns == sentinel_turns
    assert observations == [({"tab": "unavailable"}, sentinel_turns)]
    assert recorder.read_only_reason == "app_restore_failed"
    assert not recorder.continuation_allowed
    assert chat.actions[-1]["active_read_only_reason"] == "app_restore_failed"

    await controller.handle_navigate(2, "next", request_id="compatible-return")

    restored_turns = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "replacement"},
    ]
    assert record.active_leaf == compatible
    assert adapter.turns == restored_turns
    assert observations[-1] == ({"tab": "compatible"}, restored_turns)
    assert record.nodes[compatible].model_dump()["state"] == compatible_state
    assert not recorder.read_only
    assert recorder.continuation_allowed
    assert chat.actions[-1].get("active_read_only", False) is False


@pytest.mark.anyio
async def test_recovery_retry_after_unavailable_detour_restores_parent(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, _store, first, unavailable = (
        _make_v2_resubmit_real_chat(request, chat_id="unavailable_detour_retry")
    )
    await _seed_resubmit_transcript(chat, first, unavailable)
    _wire_resubmit_capture(controller, chat)
    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    sentinel_turns = [{"role": "user", "content": "poisoned outgoing"}]
    broken = True
    observations: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    def restore(values: dict[str, Any]) -> None:
        observations.append((dict(values), list(adapter.turns)))
        if broken:
            adapter.turns = list(sentinel_turns)
            raise ValueError("app restore failed")

    controller._restore_callbacks.append(restore)
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(2, "replacement", request_id="fail-edit")
    failed = record.active_leaf
    assert failed is not None and failed not in (first, unavailable)
    assert record.nodes[failed].not_sent is True
    assert recorder.read_only_reason == "app_restore_failed"
    assert adapter.turns == sentinel_turns
    with reactive.isolate():
        assert chat.user_input() is None

    broken = False
    record.nodes[unavailable].state[TURNS_STATE_KEY].kind = "unsupported"
    await controller.handle_navigate(2, "prev", request_id="unavailable-detour")
    assert record.active_leaf == unavailable
    assert adapter.turns == sentinel_turns
    assert recorder.read_only_reason == "app_restore_failed"
    assert not recorder.continuation_allowed

    await controller.handle_navigate(2, "next", request_id="return-failed")
    assert record.active_leaf == failed
    assert adapter.turns == sentinel_turns
    assert recorder.read_only_reason == "app_restore_failed"
    assert controller._can_resubmit_active()
    assert not recorder.continuation_allowed

    await controller.resubmit(
        failed, kind="retry", request_id="retry", message_index=2
    )

    submitted_id = record.active_leaf
    assert submitted_id is not None and submitted_id not in (first, unavailable)
    submitted_node = record.nodes[submitted_id]
    assert submitted_node.parent_id == first
    assert submitted_node.input is not None
    assert submitted_node.input.content == "replacement"
    restored_parent = [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert observations[-1] == ({}, restored_parent)
    assert adapter.turns == restored_parent
    assert not recorder.read_only
    assert recorder.continuation_allowed
    with reactive.isolate():
        submitted = chat.user_input()
        assert submitted is not None and submitted.text == "replacement"


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["app_failure", "not_sent"])
async def test_recovery_successful_callback_cannot_clear_invalid_live_model(
    source: str,
) -> None:
    if source == "app_failure":
        controller, _chat, adapter, _store, _original, _outgoing = (
            _make_v2_navigation_controller()
        )
        recorder = controller._exchange_recorder
        recorder.mark_read_only("app_restore_failed")
        message_index = 2
    else:
        controller, _store = _make_controller()
        record, _original, _failed = _record_with_browsable_failure()
        recorder = controller._exchange_recorder
        recorder.install_restored_record(record)
        controller._active_id.set(record.id)
        adapter = cast(_FakeAdapter, controller.adapter)
        message_index = 0
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    record = recorder.record
    callback_calls: list[bool] = []
    invalid = object()

    def poison_model(_values: dict[str, Any]) -> None:
        callback_calls.append(True)
        adapter.turns = [{"role": "user", "content": invalid}]

    controller._restore_callbacks.append(poison_model)
    with pytest.warns(
        UserWarning, match="could not validate the restored model"
    ):
        await controller.handle_navigate(
            message_index, "prev", request_id="invalid-model"
        )

    assert callback_calls == [True]
    # The selected display remains available, but an invalid live context
    # is never certified or used for ordinary continuation.
    assert recorder.record is record
    assert recorder.read_only
    assert recorder.read_only_reason == (
        "app_restore_failed" if source == "app_failure" else "model_unavailable"
    )
    assert not recorder.continuation_allowed
    assert adapter.turns == [{"role": "user", "content": invalid}]
    assert controller._active_id_now() == record.id
