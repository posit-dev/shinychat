"""Real Chat admission for ordinary follow-ups from a selected not-sent position.

A failed (terminal incomplete) position is browsable and saveable as a
display, but it is never a continuation checkpoint. These tests drive a
live ``Chat`` with real Shiny effects: the browser input payload goes through
the production input handler, the reactive input is set, and the flush runs
the real accepted-input effect. Nothing is admitted, committed, dispatched to
the provider, or written to the store, and explicit save or response
settlement leaves the failed node exactly as it was stored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from shiny import reactive
from shiny.input_handler import input_handlers
from shiny.session import session_context
from shinychat import Chat
from shinychat._history_controller import HistoryController
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
)
from shinychat._history_types import VALUES_STATE_KEY, ConversationRecordV2
from test_chat_history import _LiveSession, _make_initialized_live_v2_chat
from test_history_node_first import _record_with_browsable_failure

FAILED = "failed"


async def _live_failed_chat(
    tmp_path: Path, chat_id: str, request: pytest.FixtureRequest
) -> tuple[
    Chat,
    _LiveSession,
    HistoryController,
    FileConversationStore,
    ConversationPartition,
    list[str],
]:
    """A live Chat switched onto a stored record whose selected leaf is failed."""
    chat, session, _client, store = await _make_initialized_live_v2_chat(
        tmp_path, chat_id
    )
    request.addfinalizer(chat.destroy)
    record, _original, failed = _record_with_browsable_failure()
    assert failed == FAILED
    partition = ConversationPartition(chat_id=chat.id, scope="test")
    await store.put(partition, record)
    controller = chat.history._controller
    assert controller is not None

    provider_calls: list[str] = []

    @chat.on_user_submit
    async def _provider(text: str) -> None:
        provider_calls.append(text)

    with session_context(cast(Any, session)), reactive.isolate():
        await controller.switch_to(record.id)
    await reactive.flush()

    recorder = controller._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == FAILED
    assert not recorder.read_only
    assert recorder.read_only_reason is None
    assert recorder.selected_not_sent
    assert not recorder.continuation_allowed
    return chat, session, controller, store, partition, provider_calls


def _submit_browser_followup(
    chat: Chat, session: _LiveSession, text: str
) -> None:
    """Send a browser follow-up through the production input handler."""
    handler = cast(Any, input_handlers["shinychat.userInput"])
    payload = {"text": text, "attachments": [], "client_message_id": "c-1"}
    value = handler(payload, chat.user_input_id, session)
    cast(Any, session.input[chat.user_input_id])._set(value)


async def _stored(
    store: FileConversationStore, partition: ConversationPartition
) -> ConversationRecordV2:
    record = await store.get(partition, "c_browse_failed")
    assert isinstance(record, ConversationRecordV2)
    return record


def _assert_nothing_accepted(chat: Chat, provider_calls: list[str]) -> None:
    with reactive.isolate():
        assert chat.user_input() is None
        assert chat._normal_user_submission() is None
    assert chat._transcript.open_exchange_id is None
    assert provider_calls == []


@pytest.mark.anyio
async def test_ordinary_followup_from_selected_not_sent_is_rejected_at_real_chat(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    (
        chat,
        session,
        controller,
        store,
        partition,
        provider_calls,
    ) = await _live_failed_chat(
        tmp_path, "admission_followup_rejected", request
    )
    recorder = controller._exchange_recorder
    before = (await _stored(store, partition)).model_dump()
    transcript_before = chat._transcript.read()

    _submit_browser_followup(chat, session, "follow-up from failure")
    await reactive.flush()

    _assert_nothing_accepted(chat, provider_calls)
    assert chat._transcript.read() == transcript_before
    assert recorder.record is not None
    assert recorder.record.active_leaf == FAILED
    assert (await _stored(store, partition)).model_dump() == before


@pytest.mark.anyio
async def test_explicit_save_does_not_capture_promote_or_rewrite_selected_not_sent(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    (
        chat,
        _session,
        controller,
        store,
        partition,
        provider_calls,
    ) = await _live_failed_chat(tmp_path, "admission_explicit_save", request)
    save_calls: list[dict[str, Any]] = []
    chat.history.on_save(lambda values: save_calls.append(dict(values)))
    before = (await _stored(store, partition)).model_dump()

    saved = await chat.history.save()

    assert saved is False
    assert save_calls == []
    assert controller._exchange_recorder.record is not None
    assert controller._exchange_recorder.record.model_dump() == before
    assert (await _stored(store, partition)).model_dump() == before
    failed = (await _stored(store, partition)).nodes[FAILED]
    assert failed.not_sent is True
    assert failed.checkpoint == "invalid"
    assert failed.state[VALUES_STATE_KEY].data == {"tab": "failed"}
    _assert_nothing_accepted(chat, provider_calls)


@pytest.mark.anyio
async def test_response_settlement_does_not_capture_or_rewrite_selected_not_sent(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    (
        chat,
        _session,
        controller,
        store,
        partition,
        provider_calls,
    ) = await _live_failed_chat(tmp_path, "admission_settlement", request)
    save_calls: list[dict[str, Any]] = []
    chat.history.on_save(lambda values: save_calls.append(dict(values)))
    before = (await _stored(store, partition)).model_dump()

    # The private settlement entry point a completed response would trigger.
    await controller.on_response()
    await reactive.flush()

    assert save_calls == []
    assert controller._exchange_recorder.record is not None
    assert controller._exchange_recorder.record.model_dump() == before
    assert (await _stored(store, partition)).model_dump() == before
    _assert_nothing_accepted(chat, provider_calls)
