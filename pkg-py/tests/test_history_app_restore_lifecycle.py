"""Unified ``on_restore`` and checkpoint-only ``on_save`` lifecycle (nr6b), plus
the ordinary app-restore failure policy (w2zh).

Position changes (load, switch, browse, and the retained-parent rewind before
edit/retry/regenerate) all dispatch through the single ``_restore_app_state``
point. An ordinary ``Exception`` from an ``on_restore`` callback keeps the
conversation displayed but view-only (``app_restore_failed``); cancellation
and other fatal errors keep the full restore cleanup.
"""

import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from _history_test_helpers import replay_exchange_record
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_transcript import TranscriptEntry
from shinychat._history_store import (
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    HISTORY_ERROR_NOT_SENT,
    PREPARATION_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
)
from test_history_controller import (
    _FakeChat,
    _make_controller,
    _make_v2_navigation_controller,
    _make_v2_resubmit_real_chat,
    _RealChatSession,
    _restore_target,
    _seed_resubmit_transcript,
    _spy_send_actions,
    _stored_message,
    _wire_resubmit_capture,
    part,
)


def _values(controller: Any, node_id: str) -> dict[str, Any] | None:
    record = controller._exchange_recorder.record
    entry = record.nodes[node_id].state.get(VALUES_STATE_KEY)
    return None if entry is None else cast(dict[str, Any], entry.data)


def _read_only_actions(chat: _FakeChat) -> list[dict[str, Any]]:
    return [a for a in chat.actions if a["type"] == "history_update"]


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_on_navigate_is_removed_from_public_api() -> None:
    from shinychat import _history
    from shinychat import types as shinychat_types

    assert not hasattr(_history.ChatHistory, "on_navigate")
    assert not hasattr(shinychat_types, "HistoryNavigateContext")


# ---------------------------------------------------------------------------
# Unified on_restore: branch regression and restore-before-provider ordering
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_west_east_branch_values_follow_selected_position() -> None:
    """Completing west stores west; an east branch stores east without
    touching west; browsing back restores west; a follow-up from west does
    not overwrite west with the stale east state."""
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
        chat = Chat("lifecycle_west_east", history=False)
    controller.chat = chat  # type: ignore[assignment]
    _wire_resubmit_capture(controller, chat)

    events: list[tuple[Any, ...]] = []

    def restore_callback(values: dict[str, Any]) -> None:
        events.append(("restore", dict(values)))
        live["filter"] = str(values.get("filter", "all"))

    controller._restore_callbacks.append(restore_callback)

    async def drive_exchange(text: str, tool_filter: str) -> str:
        exchange_id = await chat._transcript.record_accepted_input_and_notify(
            _stored_message("user", text)
        )
        stream_id = f"stream-{exchange_id}"

        async def _sent() -> bool:
            return True

        await chat._transcript.start_stream(
            stream_id=stream_id,
            entry=TranscriptEntry(message=_stored_message("assistant", "")),
            owner_task=None,
            exchange_id=exchange_id,
            send=_sent,
        )
        events.append(("provider", live["filter"]))
        live["filter"] = tool_filter
        await chat._transcript.end_stream(
            stream_id=stream_id,
            status="ok",  # type: ignore[arg-type]
            error=None,
            send=_sent,
        )
        await controller.on_response()
        return exchange_id

    ex_west = await drive_exchange("west", "west")
    record = recorder.record
    assert record is not None
    root_id = record.root_id
    # The first input captures the app's starting position, before tools run.
    assert _values(controller, root_id) == {"filter": "all"}
    assert _values(controller, ex_west) == {"filter": "west"}

    await controller.handle_edit(0, "east", request_id="edit-1")
    assert events[-1] == ("restore", {"filter": "all"})
    assert live["filter"] == "all"
    ex_east = await drive_exchange("east", "east")
    assert events[-1] == ("provider", "all")
    assert _values(controller, root_id) == {"filter": "all"}
    assert _values(controller, ex_west) == {"filter": "west"}
    assert _values(controller, ex_east) == {"filter": "east"}

    await controller.handle_navigate(0, "prev", request_id="nav-prev")
    assert record.active_leaf == ex_west
    assert live["filter"] == "west"
    # Browsing back restored west; the restored west state is not captured
    # back over west, and a follow-up from west keeps both branches intact.
    await drive_exchange("west follow-up", "west-2")
    assert _values(controller, ex_west) == {"filter": "west"}
    assert _values(controller, ex_east) == {"filter": "east"}

    # Every position recreation dispatched on_restore with its own values,
    # and the edit's restore ran before the replacement provider work.
    restores = [e for e in events if e[0] == "restore"]
    assert restores == [
        ("restore", {"filter": "all"}),
        ("restore", {"filter": "west"}),
    ]
    edit_index = events.index(("restore", {"filter": "all"}))
    assert events[edit_index + 1] == ("provider", "all")


@pytest.mark.anyio
async def test_on_restore_fires_for_sibling_browse() -> None:
    """Sibling browse dispatches on_restore with the target's values."""
    controller, _fake_chat, _adapter, _store, first, _second = (
        _make_v2_navigation_controller()
    )
    record = controller._exchange_recorder.record
    assert record is not None
    record.nodes[first].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"tab": "sibling"}
    )
    calls: list[dict[str, Any]] = []
    controller._restore_callbacks.append(lambda v: calls.append(dict(v)))

    await controller.handle_navigate(2, "prev", request_id="nav-1")
    assert calls == [{"tab": "sibling"}]


# ---------------------------------------------------------------------------
# Ordinary failure: read-only retention and stop at first failure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ordinary_restore_failure_keeps_record_read_only_and_stops() -> (
    None
):
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)

    target = _restore_target()
    later_calls: list[str] = []

    def failing(_values: dict[str, Any]) -> None:
        raise RuntimeError("app state boom")

    def later(_values: dict[str, Any]) -> None:
        later_calls.append("later")

    controller._restore_callbacks.extend([failing, later])
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await replay_exchange_record(controller, target)

    # The first failure stopped dispatch; nothing masked it.
    assert later_calls == []
    # The conversation is retained and view-only, not cleared.
    assert recorder.record is target
    assert recorder.read_only is True
    assert recorder.read_only_reason == "app_restore_failed"
    notifier.assert_not_awaited()
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == ["question", "first reply", "second reply"]
    update = _read_only_actions(fake_chat)[-1]
    assert update["active_read_only"] is True
    assert update["active_read_only_reason"] == "app_restore_failed"


@pytest.mark.anyio
async def test_ordinary_browse_restore_failure_marks_writable_record_read_only() -> (
    None
):
    """A writable sibling browse whose on_restore raises an ordinary error
    moves and persists the leaf, shows the target, and goes view-only."""
    controller, fake_chat, adapter, store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    assert recorder.read_only is False

    later_calls: list[str] = []
    save_calls: list[str] = []

    def failing(_values: dict[str, Any]) -> None:
        raise RuntimeError("nav boom")

    controller._restore_callbacks.extend(
        [failing, lambda _values: later_calls.append("later")]
    )
    controller._save_callbacks.append(lambda _values: save_calls.append("save"))

    with pytest.warns(
        UserWarning, match="on_restore callback failed"
    ) as caught:
        await controller.handle_navigate(2, "prev", request_id="nav-fail")

    # The browse moved and persisted the sibling leaf before the restore.
    assert record.active_leaf == original
    assert store.put_calls[-1][1].active_leaf == original
    # The target is displayed with its model context; no continuation turn.
    assert [
        message["segments"][0]["content"]
        for message in fake_chat.restored_messages
    ] == ["first", "custom prefix", "original", "original reply"]
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "original"},
    ]
    # The warning carries the raw cause for developers.
    assert any(
        "RuntimeError('nav boom')" in str(warning.message) for warning in caught
    )
    # The first failure stopped dispatch.
    assert later_calls == []
    # The record is view-only with the specific reason.
    assert recorder.read_only is True
    assert recorder.read_only_reason == "app_restore_failed"
    update = _read_only_actions(fake_chat)[-1]
    assert update["active_read_only"] is True
    assert update["active_read_only_reason"] == "app_restore_failed"
    # Later on_save checkpoints are suppressed on the view-only record.
    assert await controller.save() is False
    assert save_calls == []


@pytest.mark.anyio
async def test_read_only_retention_reports_app_failure_not_model_context() -> (
    None
):
    controller, _store = _make_controller()
    fake_chat = cast(_FakeChat, controller.chat)
    recorder = controller._exchange_recorder
    assert recorder is not None

    def failing(_values: dict[str, Any]) -> None:
        raise ValueError("no")

    controller._restore_callbacks.append(failing)
    with pytest.warns(UserWarning):
        await replay_exchange_record(controller, _restore_target())
    assert recorder.record is not None
    original = recorder.record.active_leaf
    assert original is not None
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.resubmit(
            original,
            kind="edit",
            request_id="r",
            message_index=0,
        )
    failed_id = recorder.record.active_leaf
    assert failed_id is not None and failed_id != original
    failed = recorder.record.nodes[failed_id]
    assert failed.status == "error"
    assert failed.checkpoint == "invalid"
    assert failed.error is not None
    assert failed.error.message == HISTORY_ERROR_NOT_SENT
    assert recorder.read_only_reason == "app_restore_failed"
    update = _read_only_actions(fake_chat)[-1]
    assert update["active_read_only_reason"] == "app_restore_failed"
    assert update["active_can_resubmit"] is True


# ---------------------------------------------------------------------------
# Read-only browsing: stays read-only, no retry, display-only still runs
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_only_browsing_stays_read_only_without_retry() -> None:
    controller, fake_chat, _adapter, _store, _first, _second = (
        _make_v2_navigation_controller()
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    assert recorder.record is not None
    recorder.mark_read_only("app_restore_failed")

    calls: list[dict[str, Any]] = []
    controller._restore_callbacks.append(lambda v: calls.append(dict(v)))

    await controller.handle_navigate(2, "prev", request_id="nav-1")

    # Display-only output still dispatches on browse, but the read-only
    # state is neither cleared by a sibling callback succeeding nor
    # reclassified: the reason still explains the same failure.
    assert len(calls) == 1
    assert recorder.read_only is True
    assert recorder.read_only_reason == "app_restore_failed"
    update = _read_only_actions(fake_chat)[-1]
    assert update["active_read_only"] is True


# ---------------------------------------------------------------------------
# Retained-parent rewind: restore before send, provider kickoff suppressed
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("message_index", [0, 2])
async def test_failed_retained_parent_restore_keeps_edit_without_dispatch(
    request: pytest.FixtureRequest,
    message_index: int,
    tmp_path: Path,
) -> None:
    controller, chat, adapter, _store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="lifecycle_parent_fail")
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "ok"
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    sent = _spy_send_actions(chat)
    store = FileConversationStore(tmp_path)
    controller.store = store
    assert controller.partition is not None
    await store.put(controller.partition, record)
    adapter.turns.append({"role": "assistant", "content": "fresh model close"})
    record.nodes[first].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"value": "first"}
    )
    values_seen: list[dict[str, Any]] = []
    submission_sequence = chat._normal_user_submission_sequence

    def failing(values: dict[str, Any]) -> None:
        values_seen.append(dict(values))
        if message_index == 0:
            values["region"]
        raise RuntimeError("retained parent app restore failed")

    controller._restore_callbacks.append(failing)

    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(message_index, "edited", request_id="req")

    failed_id = record.active_leaf
    assert failed_id is not None and failed_id not in (first, target)
    failed = record.nodes[failed_id]
    parent_id = record.root_id if message_index == 0 else first
    prefix = [] if message_index == 0 else ["first", "reply one"]
    assert failed.parent_id == parent_id
    assert failed.status == "error"
    assert failed.checkpoint == "invalid"
    assert failed.error is not None
    assert failed.error.message == HISTORY_ERROR_NOT_SENT
    assert failed.state[PREPARATION_STATE_KEY].data == {
        "terminal": True,
        "accepted": False,
        "app_values": "complete",
    }
    # No on_save callbacks: the complete observed snapshot is {}, not
    # the retained parent's values masquerading as a failed capture.
    assert failed.state[VALUES_STATE_KEY].data == {}
    assert [
        cast(Any, entry.message).segments[0].content
        for entry in chat._transcript.read()
    ] == [*prefix, "edited"]
    assert chat._normal_user_submission_sequence == submission_sequence
    assert chat._transcript.open_exchange_id is None
    stored = await store.get(controller.partition, record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.active_leaf == failed_id
    assert tuple(stored.path_node_ids()) == tuple(record.path_node_ids())
    assert stored is not record
    assert stored.nodes[target].state == record.nodes[target].state
    assert stored.nodes[first].input is not None
    original_input = stored.nodes[target].input
    assert original_input is not None
    assert original_input.content == "second"
    # Outgoing model-only close capture still preserves the branch's suffix.
    assert stored.nodes[target].state["shinychat:turns"].mode == "delta"
    assert stored.nodes[target].state["shinychat:turns"].data == [
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "fresh model close"},
    ]
    assert adapter.turns == (
        [{"role": "system", "content": "bootstrap"}]
        if message_index == 0
        else [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
        ]
    )
    assert values_seen == ([{}] if message_index == 0 else [{"value": "first"}])

    # Reopening preserves the selected failed version and its own app facts.
    reloaded, _reload_store = _make_controller()
    reload_chat = cast(_FakeChat, reloaded.chat)
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        reloaded._restore_callbacks.append(failing)
        await replay_exchange_record(reloaded, stored)
    assert reloaded._exchange_recorder.record is not None
    assert reloaded._exchange_recorder.record.active_leaf == failed_id
    assert reloaded._exchange_recorder.source_isolated is False
    assert [
        m["segments"][0]["content"] for m in reload_chat.restored_messages
    ] == [*prefix, "edited"]
    assert values_seen[-1] == {}

    # Projection is presentation, not provider kickoff: it uses the staged ID
    # without a browser echo; accepted-input publication is still unchanged.
    projections = [a for a in sent if a["type"] == "history_edit_projection"]
    assert len(projections) == 1
    assert projections[0]["exchange_id"] == failed_id
    assert projections[0]["submission_mode"] == "server"
    assert sent[-1]["type"] == "history_update"
    assert sent[-1]["active_read_only"] is True
    assert sent[-1]["active_read_only_reason"] == "app_restore_failed"
    assert recorder.read_only is True

    # An intentional Retry that fails again creates another version, leaving
    # the first failed node and the original branch unchanged.
    first_failure = failed.model_copy(deep=True)
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.resubmit(
            failed_id,
            kind="retry",
            request_id="req-2",
            message_index=message_index,
        )
    retry_id = record.active_leaf
    assert retry_id is not None and retry_id != failed_id
    assert record.nodes[retry_id].parent_id == parent_id
    assert record.nodes[retry_id].checkpoint == "invalid"
    assert record.nodes[failed_id] == first_failure
    assert chat._normal_user_submission_sequence == submission_sequence


@pytest.mark.anyio
async def test_successful_retained_parent_restore_still_sends_projection(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="lifecycle_parent_ok")
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "ok"
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    sent = _spy_send_actions(chat)
    controller._restore_callbacks.append(lambda _v: None)

    await controller.handle_edit(2, "second edited", request_id="req")

    assert sent[-1]["type"] == "history_edit_projection"
    assert recorder.read_only is False


# ---------------------------------------------------------------------------
# Full cleanup: metadata failure and fatal/cancel errors
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_metadata_failure_after_app_failure_takes_full_cleanup() -> None:
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)

    events: list[str] = []

    def failing(_values: dict[str, Any]) -> None:
        events.append("app restore")
        raise RuntimeError("app state boom")

    controller._restore_callbacks.append(failing)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]
    original_update = controller.send_history_update
    updates = 0

    async def broken_update() -> None:
        nonlocal updates
        updates += 1
        events.append("metadata")
        if updates == 1:
            raise RuntimeError("metadata delivery failed")
        await original_update()

    controller.send_history_update = broken_update  # type: ignore[method-assign]

    with (
        pytest.warns(UserWarning),
        pytest.raises(RuntimeError, match="metadata delivery failed"),
    ):
        await replay_exchange_record(controller, _restore_target())

    assert events[:2] == ["app restore", "metadata"]
    # Metadata never confirmed the read-only state, so the conversation is
    # cleared like any other failed restore, not left writable-but-stale.
    assert recorder.record is None
    assert recorder.read_only is False
    assert fake_chat.clear_messages_calls >= 1
    notifier.assert_awaited()


@pytest.mark.anyio
async def test_fatal_restore_error_takes_full_cleanup_without_read_only() -> (
    None
):
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)

    def cancelled(_values: dict[str, Any]) -> None:
        raise asyncio.CancelledError()

    controller._restore_callbacks.append(cancelled)
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await replay_exchange_record(controller, _restore_target())

    assert recorder.record is None
    assert recorder.read_only is False
    assert recorder.read_only_reason is None
    assert fake_chat.clear_messages_calls >= 1
    notifier.assert_awaited()
    assert not any(
        a["type"] == "history_update" and a.get("active_read_only")
        for a in fake_chat.actions
    )


@pytest.mark.anyio
async def test_fatal_rewind_error_takes_full_cleanup(
    request: pytest.FixtureRequest,
) -> None:
    controller, chat, _adapter, _store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id="lifecycle_fatal_rewind")
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    record.nodes[target].status = "ok"
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)

    def cancelled(_values: dict[str, Any]) -> None:
        raise asyncio.CancelledError()

    controller._restore_callbacks.append(cancelled)

    with pytest.raises(asyncio.CancelledError):
        await controller.handle_edit(2, "second edited", request_id="req")

    assert recorder.record is None
    assert recorder.read_only is False


# ---------------------------------------------------------------------------
# Wire: reason is explanation only, emitted with active_read_only
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_history_update_reason_is_emitted_only_when_read_only() -> None:
    controller, _ = _make_controller()
    recorder = controller._exchange_recorder
    assert recorder is not None
    fake_chat = cast(_FakeChat, controller.chat)

    await controller.send_history_update()
    assert "active_read_only" not in fake_chat.actions[-1]
    assert "active_read_only_reason" not in fake_chat.actions[-1]

    recorder.install_restored_record(
        _restore_target(), read_only=True, read_only_reason="model_unavailable"
    )
    await controller.send_history_update()
    assert fake_chat.actions[-1]["active_read_only"] is True
    assert (
        fake_chat.actions[-1]["active_read_only_reason"] == "model_unavailable"
    )

    recorder.reset()
    await controller.send_history_update()
    assert "active_read_only_reason" not in fake_chat.actions[-1]


# ---------------------------------------------------------------------------
# on_save: checkpoint-only capture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_on_save_does_not_capture_on_rename_retitle_or_browse() -> None:
    captures: list[int] = []

    def save_callback(values: dict[str, Any]) -> None:
        captures.append(1)
        values["tab"] = "x"

    controller, _chat, _adapter, _store, original, _replacement = (
        _make_v2_navigation_controller()
    )
    controller._save_callbacks.append(save_callback)
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    before = len(captures)

    assert await recorder.retitle_active_locked(record, "llm title")
    await controller.rename(record.id, "renamed")
    assert len(captures) == before

    await controller.handle_navigate(2, "prev", request_id="nav-1")
    assert record.active_leaf == original
    assert len(captures) == before


@pytest.mark.anyio
async def test_explicit_save_still_captures_selected_position() -> None:
    captures: list[int] = []

    def save_callback(values: dict[str, Any]) -> None:
        captures.append(1)
        values["tab"] = "x"

    controller, _ = _make_controller(save_callbacks=[save_callback])
    recorder = controller._exchange_recorder
    assert recorder is not None
    recorder.install_restored_record(_restore_target())
    before = len(captures)

    assert await controller.save() is True
    assert len(captures) == before + 1


@pytest.mark.anyio
async def test_explicit_save_on_read_only_record_does_not_capture() -> None:
    controller, _ = _make_controller(
        save_callbacks=[lambda values: values.update(tab="x")]
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    recorder.install_restored_record(_restore_target(), read_only=True)
    assert await controller.save_current() is False


# ---------------------------------------------------------------------------
# Regression: load and switch restore but never capture; New chat neither
# captures the outgoing conversation nor restores anything (nr6b).
# ---------------------------------------------------------------------------


def _valued_record(record_id: str, tab: str) -> Any:
    record = _restore_target(id=record_id)
    assert record.active_leaf is not None
    record.nodes[record.active_leaf].state[VALUES_STATE_KEY] = StateEntry(
        kind="values",
        version=1,
        mode="snapshot",
        data={"tab": tab},
    )
    return record


@pytest.mark.anyio
async def test_load_and_switch_restore_target_values_without_capturing() -> (
    None
):
    captures: list[str] = []
    restores: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        captures.append("save")
        values["tab"] = "live"

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    controller._restore_callbacks.append(lambda v: restores.append(dict(v)))
    first = _valued_record("c_load_first", "one")
    second = _valued_record("c_load_second", "two")
    await controller.store.put(part(), first)
    await controller.store.put(part(), second)

    # Page load / bookmark restore: the selected position's values restore.
    await replay_exchange_record(controller, first)
    assert restores == [{"tab": "one"}]
    assert captures == []

    # Switch: the target restores; the outgoing conversation never captures.
    await controller.switch_to(second.id)
    assert restores == [{"tab": "one"}, {"tab": "two"}]
    assert captures == []
    assert first.active_leaf is not None
    assert first.nodes[first.active_leaf].state[VALUES_STATE_KEY].data == {
        "tab": "one"
    }


@pytest.mark.anyio
async def test_new_chat_neither_captures_outgoing_nor_restores() -> None:
    captures: list[str] = []
    restores: list[dict[str, Any]] = []

    def save_callback(values: dict[str, Any]) -> None:
        captures.append("save")
        values["tab"] = "live"

    controller, _ = _make_controller(
        store=InMemoryConversationStore(), save_callbacks=[save_callback]
    )
    controller._restore_callbacks.append(lambda v: restores.append(dict(v)))
    active = _valued_record("c_new_chat_active", "saved")
    await controller.store.put(part(), active)
    await replay_exchange_record(controller, active)
    captures.clear()
    restores.clear()

    await controller.new_chat()

    # The outgoing conversation keeps its saved values, nothing captured,
    # and New chat has no saved target, so no restore fires.
    assert captures == []
    assert restores == []
    assert active.active_leaf is not None
    assert active.nodes[active.active_leaf].state[VALUES_STATE_KEY].data == {
        "tab": "saved"
    }
    stored = await controller.store.get(part(), active.id)
    assert isinstance(stored, ConversationRecordV2)
    assert stored.nodes[active.active_leaf].state[VALUES_STATE_KEY].data == {
        "tab": "saved"
    }


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["browse", "edit"])
async def test_in_session_restore_callback_transcript_matches_operation(
    request: pytest.FixtureRequest, operation: str
) -> None:
    if operation == "edit":
        controller, chat, adapter, _store, first, target = (
            _make_v2_resubmit_real_chat(request, chat_id="callback_phase_edit")
        )
        await _seed_resubmit_transcript(chat, first, target)
    else:
        controller, _fake, adapter, _store, first, target = (
            _make_v2_navigation_controller()
        )
        session = _RealChatSession()
        with session_context(cast(Any, session)):
            chat = Chat("callback_phase_browse", history=False)
        request.addfinalizer(chat.destroy)
        controller.chat = chat
        record = controller._exchange_recorder.record
        assert record is not None
        await controller._replay_exchange_display(
            record, tuple(record.path_node_ids())
        )
    _wire_resubmit_capture(controller, chat)
    _spy_send_actions(chat)
    record = controller._exchange_recorder.record
    assert record is not None
    outgoing = chat.messages()
    observations: list[tuple[Any, Any, Any, dict[str, Any]]] = []

    def observe(_values: dict[str, Any]) -> None:
        observations.append(
            (
                chat.messages(),
                list(adapter.turns),
                record.active_leaf,
                dict(_values),
            )
        )

    controller._restore_callbacks.append(observe)
    if operation == "edit":
        await controller.handle_edit(2, "replacement", request_id="phase")
        expected_turns = [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
        ]
        # An edit prepares unaccepted input against the retained parent.
        # Its restore callback must see that parent's accepted prefix.
        expected_messages = outgoing[:2]
        expected_leaf = record.active_leaf
    else:
        await controller.handle_navigate(2, "prev", request_id="phase")
        expected_turns = [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "original"},
        ]
        expected_messages = outgoing
        expected_leaf = first
    assert observations == [
        (expected_messages, expected_turns, expected_leaf, {})
    ]
    if operation == "edit":
        # The callback saw the one staged node that was later accepted.
        assert expected_leaf is not None
        assert expected_leaf not in (first, target)
        node = record.nodes[expected_leaf]
        assert node.parent_id == first
        assert node.input is not None
        assert node.input.content == "replacement"
