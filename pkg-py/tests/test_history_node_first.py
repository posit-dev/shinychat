"""Focused unit tests for the node-first failed-edit core (shinychat#zcv8).

Covers the success path through the real guarded Chat seam, terminal
failure attachment, recovery (explicit Retry from a failed position),
fail-closed envelope validation, complete-vs-unavailable app values, and
the terminal browsing/reload handling. Storage/admission boundary cases
live in test_history_node_first_boundaries.py.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from _history_test_helpers import replay_exchange_record
from shiny import reactive
from shinychat._chat_transcript import StagedInputAdmission
from shinychat._history_store import FileConversationStore
from shinychat._history_types import (
    HISTORY_ERROR_NOT_SENT,
    PREPARATION_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
    node_is_terminal_incomplete,
)
from test_history_controller import (
    _FakeAdapter,
    _FakeChat,
    _make_controller,
    _make_v2_resubmit_real_chat,
    _seed_resubmit_transcript,
    _spy_send_actions,
    _stored_message,
    _wire_resubmit_capture,
    part,
)


def _preparation_data(node: Any) -> dict[str, Any]:
    entry = node.state.get(PREPARATION_STATE_KEY)
    assert entry is not None
    assert isinstance(entry.data, dict)
    return cast(dict[str, Any], entry.data)


def _actions_of_list(
    actions: list[dict[str, Any]], action_type: str
) -> list[dict[str, Any]]:
    return [a for a in actions if a["type"] == action_type]


# ---------------------------------------------------------------------------
# Success path: staged once, admitted once, through the real Chat seam
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_edit_success_stages_then_admits_exactly_once(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_success")
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    sent = _spy_send_actions(chat)
    record = controller._exchange_recorder.record
    assert record is not None

    await controller.handle_edit(2, "replacement", request_id="req-1")

    sibling = record.active_leaf
    assert sibling is not None and sibling not in (first, target)
    node = record.nodes[sibling]
    assert node.parent_id == first
    assert node.input is not None
    assert node.input.content == "replacement"
    assert node.status == "pending"
    assert record.children_of(first) == [target, sibling]
    # The original branch is preserved untouched.
    target_input = record.nodes[target].input
    assert target_input is not None
    assert target_input.content == "second"

    # The projection carries the staged identity and server submission
    # mode; the accepted input was committed under that same ID.
    projections = [a for a in sent if a["type"] == "history_edit_projection"]
    assert projections == [
        {
            "type": "history_edit_projection",
            "requestId": "req-1",
            "index": 2,
            "content": "replacement",
            "attachments": [],
            "submission_mode": "server",
            "exchange_id": sibling,
        }
    ]
    transcript_ids = [
        entry.exchange_id for entry in chat._transcript.read()
    ]
    assert transcript_ids[-1] == sibling
    with reactive.isolate():
        latest = chat.user_input()
        assert latest is not None
        assert latest.text == "replacement"
        submission = chat._normal_user_submission()
        assert submission is not None
        assert str(submission[1].content) == "replacement"

    # A replayed admission of the same staged ID is rejected before any
    # capture, commit, or accepted-input signal.
    with pytest.raises(RuntimeError, match="already admitted"):
        await chat._transcript.record_staged_input_and_notify(
            StagedInputAdmission(sibling),
            node.input.model_copy(deep=True),
        )
    assert record.children_of(first) == [target, sibling]


# ---------------------------------------------------------------------------
# Failure attachment: restore throw and post-restore capture failure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_edit_restore_failure_attaches_terminal_node(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_restore")
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None
    recorder = controller._exchange_recorder

    def failing(_values: dict[str, Any]) -> None:
        raise RuntimeError("edit-time restore broke")

    controller._restore_callbacks.append(failing)
    sent = _spy_send_actions(chat)

    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(2, "replacement", request_id="req-2")

    staged = record.active_leaf
    assert staged is not None and staged not in (first, target)
    node = record.nodes[staged]
    assert node.parent_id == first
    assert node.status == "error"
    assert node.error is not None
    assert node.error.message == HISTORY_ERROR_NOT_SENT
    assert node.checkpoint == "invalid"
    assert node_is_terminal_incomplete(node)
    assert _preparation_data(node) == {
        "terminal": True,
        "accepted": False,
        # No save callbacks are registered, so the one automatic capture
        # records the observed (empty) values as complete.
        "app_values": "complete",
    }
    assert node.input is not None
    assert node.input.content == "replacement"
    # The restriction names the app restore failure; it is resolvable.
    assert recorder.read_only
    assert recorder.read_only_reason == "app_restore_failed"
    # No accepted-input signal ever fired for the failed attempt.
    with reactive.isolate():
        assert chat.user_input() is None
        assert chat._normal_user_submission() is None
    # The transcript shows the parent prefix plus the failed row.
    assert [
        cast(Any, entry.message).segments[0].content
        for entry in chat._transcript.read()
    ] == ["first", "reply one", "replacement"]
    # The original branch is preserved.
    assert record.nodes[target].input is not None

    # Client settlement: failed-row metadata, read-only + resubmit flag.
    metadata = _actions_of_list(sent, "update_exchange_metadata")[-1]["data"]
    assert metadata[2]["status"] == "error"
    assert metadata[2]["error_message"] == HISTORY_ERROR_NOT_SENT
    assert metadata[2]["preparation_failed"] is True
    assert metadata[2]["retryable"] is True
    update = _actions_of_list(sent, "history_update")[-1]
    assert update["active_read_only"] is True
    assert update["active_read_only_reason"] == "app_restore_failed"
    assert update["active_can_resubmit"] is True


class _PoisonableAdapter(_FakeAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.poisoned = False

    def get_turns_json(
        self, *, include_system_prompt: bool = False
    ) -> list[dict[str, Any]]:
        if self.poisoned:
            raise RuntimeError("Injected live model capture failure")
        return super().get_turns_json(
            include_system_prompt=include_system_prompt
        )

    def set_turns_json(self, turns: list[Any]) -> None:
        super().set_turns_json(turns)
        self.poisoned = False


@pytest.mark.anyio
async def test_edit_capture_failure_after_restore_attaches_terminal_node(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_capture")
    )
    poisoned_adapter = _PoisonableAdapter()
    poisoned_adapter.turns = adapter.turns
    controller.adapter = poisoned_adapter  # type: ignore[assignment]
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None
    recorder = controller._exchange_recorder

    def poison(_values: dict[str, Any]) -> None:
        # on_restore returns normally after poisoning the live model, so
        # the required post-restore capture fails.
        poisoned_adapter.poisoned = True

    controller._restore_callbacks.append(poison)

    with pytest.warns(UserWarning, match="edit preparation failed"):
        await controller.handle_edit(2, "replacement", request_id="req-3")

    staged = record.active_leaf
    assert staged is not None and staged not in (first, target)
    node = record.nodes[staged]
    assert node_is_terminal_incomplete(node)
    assert _preparation_data(node)["app_values"] == "complete"
    # The complete failed-position snapshot records its own values entry,
    # even though it equals the inherited (empty) values: a sparse
    # capture would have recorded nothing and been mistaken for
    # unavailable.
    assert VALUES_STATE_KEY in node.state
    assert node.state[VALUES_STATE_KEY].data == {}
    assert recorder.read_only_reason == "terminal_incomplete"
    with reactive.isolate():
        assert chat.user_input() is None


@pytest.mark.anyio
async def test_failed_position_values_unavailable_when_save_throws(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_saveerr")
    )
    poisoned_adapter = _PoisonableAdapter()
    poisoned_adapter.turns = adapter.turns
    controller.adapter = poisoned_adapter  # type: ignore[assignment]
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None

    def broken_save(_values: dict[str, Any]) -> None:
        raise RuntimeError("on_save broke")

    controller._save_callbacks.append(broken_save)
    controller._restore_callbacks.append(
        lambda _values: setattr(poisoned_adapter, "poisoned", True)
    )

    with pytest.warns(UserWarning):
        await controller.handle_edit(2, "replacement", request_id="req-4")

    staged = record.active_leaf
    assert staged is not None
    node = record.nodes[staged]
    assert node_is_terminal_incomplete(node)
    assert _preparation_data(node)["app_values"] == "unavailable"
    # Unavailable means no observed values: nothing is recorded that a
    # later restore could mistake for the failed position's own values.
    assert VALUES_STATE_KEY not in node.state


# ---------------------------------------------------------------------------
# Recovery: explicit Retry from the failed position
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_retry_from_failed_recovers_and_creates_new_sibling(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_retry")
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None
    recorder = controller._exchange_recorder

    broken = {"value": True}

    def flaky(_values: dict[str, Any]) -> None:
        if broken["value"]:
            raise RuntimeError("edit-time restore broke")

    controller._restore_callbacks.append(flaky)

    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(2, "replacement", request_id="req-5")

    failed = record.active_leaf
    assert failed is not None
    failed_node = record.nodes[failed].model_copy(deep=True)
    assert recorder.read_only_reason == "app_restore_failed"

    # The developer fixes the app; an explicit Retry revalidates, restores
    # the valid parent, clears only the resolved restriction, and creates
    # a NEW sibling — the failed node is never rewritten.
    broken["value"] = False
    await controller.resubmit(
        failed, kind="retry", request_id="req-6", message_index=2
    )

    sibling = record.active_leaf
    assert sibling is not None and sibling not in (first, target, failed)
    assert record.nodes[sibling].parent_id == first
    assert record.nodes[sibling].status == "pending"
    assert record.children_of(first) == [target, failed, sibling]
    assert record.nodes[failed].model_dump() == failed_node.model_dump()
    assert not recorder.read_only
    with reactive.isolate():
        latest = chat.user_input()
        assert latest is not None
        assert latest.text == "replacement"


@pytest.mark.anyio
async def test_retry_from_failed_skips_poisoned_outgoing_close_capture(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_poison")
    )
    poisoned_adapter = _PoisonableAdapter()
    poisoned_adapter.turns = adapter.turns
    controller.adapter = poisoned_adapter  # type: ignore[assignment]
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None
    recorder = controller._exchange_recorder

    broken = {"value": True}

    def maybe_poison(_values: dict[str, Any]) -> None:
        if broken["value"]:
            poisoned_adapter.poisoned = True

    controller._restore_callbacks.append(maybe_poison)

    with pytest.warns(UserWarning, match="edit preparation failed"):
        await controller.handle_edit(2, "replacement", request_id="req-7")

    failed = record.active_leaf
    assert failed is not None
    assert recorder.read_only_reason == "terminal_incomplete"
    assert poisoned_adapter.poisoned

    # The developer fixes the app, but the live model is still poisoned.
    # The retry must NOT close-capture the failed position's live model:
    # it restores the valid parent (which clears the poison via
    # set_turns) and admits a new sibling.
    broken["value"] = False
    await controller.resubmit(
        failed, kind="retry", request_id="req-8", message_index=2
    )

    sibling = record.active_leaf
    assert sibling is not None and sibling != failed
    assert record.nodes[sibling].parent_id == first
    assert record.nodes[sibling].status == "pending"
    assert not poisoned_adapter.poisoned
    assert not recorder.read_only
    assert poisoned_adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]


@pytest.mark.anyio
async def test_retry_from_failed_stays_refused_for_unrelated_restrictions(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, adapter, store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_refused")
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    record = controller._exchange_recorder.record
    assert record is not None
    recorder = controller._exchange_recorder

    controller._restore_callbacks.append(
        lambda _values: (_ for _ in ()).throw(RuntimeError("broke"))
    )
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(2, "replacement", request_id="req-9")

    failed = record.active_leaf
    assert failed is not None
    # A source-isolated record never recovers through resubmit.
    recorder.install_restored_record(
        record, read_only=True, source_isolated=True,
        read_only_reason="interrupted",
    )
    with pytest.raises(RuntimeError, match="interrupted"):
        await controller.resubmit(
            failed, kind="retry", request_id="req-10", message_index=2
        )
    # A model-unavailable restriction is not cleared by resubmits either.
    recorder.install_restored_record(
        record, read_only=True, read_only_reason="model_unavailable"
    )
    with pytest.raises(RuntimeError, match="model context is unavailable"):
        await controller.resubmit(
            failed, kind="retry", request_id="req-11", message_index=2
        )


# ---------------------------------------------------------------------------
# Fail-closed envelope validation
# ---------------------------------------------------------------------------


def _record_with_failed_leaf(
    *, envelope: StateEntry | None, checkpoint: Any = "invalid", status: Any = "error"
) -> tuple[Any, str, str]:
    record = new_conversation_record_v2(
        id="c_envelope_guard", title="guard", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.open_exchange("original", _stored_message("user", "B"))
    record.finish_exchange("original", "ok", None)
    record.nodes["original"].checkpoint = "valid"
    record.set_active_leaf(root_id)
    record.open_exchange("failed", _stored_message("user", "B-prime"))
    record.finish_exchange("failed", status, "err")
    record.nodes["failed"].checkpoint = checkpoint
    if envelope is not None:
        record.nodes["failed"].state[PREPARATION_STATE_KEY] = envelope
    return record, root_id, "failed"


VALID_ENVELOPE = StateEntry(
    kind="input_preparation",
    version=1,
    mode="snapshot",
    data={"terminal": True, "accepted": False, "app_values": "complete"},
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "envelope",
    [
        StateEntry(
            kind="input_preparation",
            version=2,
            mode="snapshot",
            data={"terminal": True, "accepted": False, "app_values": "complete"},
        ),
        StateEntry(
            kind="input_preparation",
            version=1,
            mode="delta",
            data={"terminal": True, "accepted": False, "app_values": "complete"},
        ),
        StateEntry(
            kind="input_preparation",
            version=1,
            mode="snapshot",
            data={"terminal": True, "accepted": True, "app_values": "complete"},
        ),
        StateEntry(
            kind="input_preparation",
            version=1,
            mode="snapshot",
            data={"terminal": True, "accepted": False, "app_values": "partial"},
        ),
        StateEntry(
            kind="input_preparation",
            version=1,
            mode="snapshot",
            data={"terminal": True, "accepted": False},
        ),
        StateEntry(
            kind="other_kind",
            version=1,
            mode="snapshot",
            data={"terminal": True, "accepted": False, "app_values": "complete"},
        ),
    ],
    ids=["version", "mode", "accepted", "app_values", "missing-key", "kind"],
)
async def test_malformed_preparation_envelope_fails_closed(
    envelope: StateEntry,
) -> None:
    from shinychat import _history_plan

    record, _root, failed = _record_with_failed_leaf(envelope=envelope)
    node = record.nodes[failed]
    # A malformed marker never classifies the node as a known terminal
    # position...
    assert not node_is_terminal_incomplete(node)
    # ...and any planning against the record fails closed before mutation.
    with pytest.raises(ValueError, match="preparation"):
        _history_plan.validate_active_path_state(record)
    controller, _ = _make_controller()
    with pytest.raises(ValueError, match="preparation"):
        controller._prepare_exchange_restore(record.model_copy(deep=True))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "checkpoint,status",
    [("valid", "error"), (None, "error"), ("candidate", "error"), ("invalid", "pending")],
    ids=["valid", "legacy-none", "candidate", "pending"],
)
async def test_valid_envelope_with_wrong_position_fails_closed(
    checkpoint: Any, status: Any
) -> None:
    """A valid marker on a non-terminal node is contradictory: it is not a
    continuation checkpoint, not a terminal failure, and never restored or
    admitted."""
    from shinychat import _history_plan

    record, _root, failed = _record_with_failed_leaf(
        envelope=VALID_ENVELOPE.model_copy(deep=True),
        checkpoint=checkpoint,
        status=status,
    )
    node = record.nodes[failed]
    assert not node_is_terminal_incomplete(node)
    with pytest.raises(ValueError, match="not a terminal failed submission"):
        _history_plan.validate_active_path_state(record)
    controller, _ = _make_controller()
    with pytest.raises(ValueError, match="not a terminal failed submission"):
        controller._prepare_exchange_restore(record.model_copy(deep=True))


# ---------------------------------------------------------------------------
# Terminal browsing and reload
# ---------------------------------------------------------------------------


def _record_with_browsable_failure() -> tuple[Any, str, str]:
    record = new_conversation_record_v2(
        id="c_browse_failed", title="browse", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.open_exchange("original", _stored_message("user", "B"))
    record.finish_exchange("original", "ok", None)
    record.nodes["original"].checkpoint = "valid"
    record.nodes["original"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "B"}],
    )
    record.set_active_leaf(root_id)
    record.open_exchange("failed", _stored_message("user", "B-prime"))
    record.finish_exchange("failed", "error", HISTORY_ERROR_NOT_SENT)
    record.nodes["failed"].checkpoint = "invalid"
    record.nodes["failed"].state[PREPARATION_STATE_KEY] = (
        VALID_ENVELOPE.model_copy(deep=True)
    )
    record.nodes["failed"].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "failed"}
    )
    return record, "original", "failed"


@pytest.mark.anyio
async def test_failed_leaf_loads_browsable_not_source_isolated() -> None:
    controller, _ = _make_controller()
    record, original, failed = _record_with_browsable_failure()
    restores: list[dict[str, Any]] = []
    controller._restore_callbacks.append(lambda v: restores.append(dict(v)))

    await replay_exchange_record(controller, record)

    recorder = controller._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == failed
    # A known terminal incomplete position is not an interrupted producer:
    # no source isolation, but it is view-only as terminal incomplete.
    assert not recorder.source_isolated
    assert recorder.read_only
    assert recorder.read_only_reason == "terminal_incomplete"
    # The failed position's own observed values restore.
    assert restores == [{"tab": "failed"}]
    # Sibling navigation includes the failed leaf (explicit positions).
    assert recorder.record.checkpoint_siblings(failed) == [original, failed]


@pytest.mark.anyio
async def test_failed_leaf_without_values_skips_restore_on_load() -> None:
    controller, _ = _make_controller()
    record, _original, failed = _record_with_browsable_failure()
    # Unavailable app values: no own entry, never inherited.
    del record.nodes[failed].state[VALUES_STATE_KEY]
    record.nodes[failed].state[PREPARATION_STATE_KEY] = StateEntry(
        kind="input_preparation",
        version=1,
        mode="snapshot",
        data={"terminal": True, "accepted": False, "app_values": "unavailable"},
    )
    restores: list[dict[str, Any]] = []
    controller._restore_callbacks.append(lambda v: restores.append(dict(v)))

    await replay_exchange_record(controller, record)

    assert restores == []
    assert controller._exchange_recorder.read_only_reason == (
        "terminal_incomplete"
    )


@pytest.mark.anyio
async def test_browse_between_failed_and_original() -> None:
    controller, _ = _make_controller()
    record, original, failed = _record_with_browsable_failure()
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    fake = cast(_FakeChat, controller.chat)

    # Failed -> original: explicit sibling navigation works.
    await controller.handle_navigate(0, "prev", request_id="nav-1")
    assert recorder.record is not None
    assert recorder.record.active_leaf == original
    # Original -> failed: display-only, marked terminal incomplete again.
    await controller.handle_navigate(0, "next", request_id="nav-2")
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "terminal_incomplete"
    update = _actions_of_list(fake.actions, "history_update")[-1]
    assert update["active_read_only"] is True
    assert update["active_read_only_reason"] == "terminal_incomplete"
    assert update["active_can_resubmit"] is True


@pytest.mark.anyio
async def test_failed_edit_survives_file_store_reload(
    tmp_path: Any,
) -> None:
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store)
    record, original, failed = _record_with_browsable_failure()
    await store.put(part(), record)

    await replay_exchange_record(controller, record)
    await controller.save_current()

    reloaded, _ = _make_controller(store=store)
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restores: list[dict[str, Any]] = []
    reloaded._restore_callbacks.append(lambda v: restores.append(dict(v)))
    await replay_exchange_record(reloaded, stored)

    recorder = reloaded._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "terminal_incomplete"
    failed_node = recorder.record.nodes[failed]
    assert node_is_terminal_incomplete(failed_node)
    assert _preparation_data(failed_node)["app_values"] == "complete"
    assert recorder.record.checkpoint_siblings(failed) == [original, failed]


# ---------------------------------------------------------------------------
# Admission guard strength
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_staged_admission_requires_owned_transaction(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="node_first_guard")
    )
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)

    admission = StagedInputAdmission("staged-x")
    message = _stored_message("user", "x")
    # No transaction at all.
    with pytest.raises(RuntimeError, match="owned history transaction"):
        await chat._record_accepted_user_input_with_capture(
            message, staged_admission=admission
        )
    # A transaction object the chat does not own.
    with pytest.raises(RuntimeError, match="owned history transaction"):
        await chat._record_accepted_user_input_with_capture(
            message, staged_admission=admission, transaction=object()
        )
    # The capability was not consumed by the rejections.
    assert not admission.committed
