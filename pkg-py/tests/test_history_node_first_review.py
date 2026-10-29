"""Regressions for the independent node-first review's P1/P2 findings.

Unavailable values are not ordinary sparse inheritance. Baseline writers can
pin parent values onto an unavailable failed child while preserving its opaque
preparation marker; that valid marker remains authoritative on a new reader.
Bookmarks identify display positions, including known terminal failures, not
just model-continuation checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, cast
from unittest.mock import MagicMock, patch

import pytest
from shiny import reactive
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_types import ChatMessage
from shinychat._history_controller import HistoryController
from shinychat._history_plan import (
    resolve_path_values,
    validate_active_path_state,
)
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    HISTORY_ERROR_NOT_SENT,
    PREPARATION_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
    node_is_terminal_incomplete,
)
from shinychat.types import HistoryOptions
from test_chat_history import (
    _capture_history_effects,
    _history_updates,
    _LiveSession,
    _MockClient,
)
from test_history_controller import _stored_message

CHAT_ID = "node_first_review"
PARTITION = ConversationPartition(chat_id=CHAT_ID, scope="test")
OLD_VALUES: dict[str, Any] = {"region": "old-parent"}
NEW_VALUES = {"region": "new-parent"}


@pytest.fixture(params=["file", "memory"])
def review_store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> ConversationStore:
    if request.param == "file":
        return FileConversationStore(dir=tmp_path)
    return InMemoryConversationStore()


def _record(
    *, availability: str = "unavailable", failed_parent: str | None = None
) -> ConversationRecordV2:
    record = new_conversation_record_v2(
        id="c_review", title="Review", client_info={}
    )
    root = record.root_id
    record.nodes[root].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.nodes[root].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data=OLD_VALUES.copy()
    )
    record.open_exchange("original", _stored_message("user", "original"))
    record.append_message(
        "original",
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "original reply"), icon=None
        ),
    )
    record.finish_exchange("original", "ok", None)
    record.nodes["original"].checkpoint = "valid"
    record.nodes["original"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "original reply"},
        ],
    )
    record.set_active_leaf(root)
    record.open_exchange("ordinary", _stored_message("user", "ordinary"))
    record.finish_exchange("ordinary", "ok", None)
    record.nodes["ordinary"].checkpoint = "valid"
    record.set_active_leaf(root if failed_parent is None else failed_parent)
    record.open_exchange("failed", _stored_message("user", "replacement"))
    record.finish_exchange("failed", "error", HISTORY_ERROR_NOT_SENT)
    record.nodes["failed"].checkpoint = "invalid"
    record.nodes["failed"].state[PREPARATION_STATE_KEY] = StateEntry(
        kind="input_preparation",
        version=1,
        mode="snapshot",
        data={"terminal": True, "accepted": False, "app_values": availability},
    )
    if availability == "complete":
        record.nodes["failed"].state[VALUES_STATE_KEY] = StateEntry(
            kind="values", version=1, mode="snapshot", data={}
        )
    return record


@dataclass
class _View:
    chat: Chat
    controller: HistoryController
    session: _LiveSession
    handlers: dict[str, Callable[[], Awaitable[None]]]
    provider_inputs: list[str]

    async def initialize(self) -> None:
        with session_context(cast(Any, self.session)), reactive.isolate():
            await self.handlers["_init_history"]()

    async def stamp(self) -> dict[str, str]:
        # Run the registered production ChatHistory stamper through the
        # bookmark framework boundary, not a manually synthesized pointer.
        self.session.bookmark.bookmark_urls.append("?_state_id_=review")
        with session_context(cast(Any, self.session)), reactive.isolate():
            await self.session.bookmark.do_bookmark()
        values = self.session.bookmark.bookmark_states[-1]
        return cast(
            dict[str, str], values[f"{CHAT_ID}_history_exchange_pointer"]
        )


def _view(
    request: pytest.FixtureRequest,
    store: ConversationStore,
    *,
    pointer: dict[str, str] | None = None,
) -> _View:
    session = _LiveSession()
    session.bookmark.store = "server"
    if pointer is not None:
        session.bookmark._restore_context = MagicMock(
            active=True,
            values={f"{CHAT_ID}_history_exchange_pointer": pointer},
        )
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    provider_inputs: list[str] = []
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            CHAT_ID,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store, scope="test", restore_mode="none"
            ),
        )

        @chat.on_user_submit
        async def provider(text: str) -> None:
            provider_inputs.append(text)

    request.addfinalizer(chat.destroy)
    controller = chat.history._controller
    assert controller is not None
    return _View(chat, controller, session, handlers, provider_inputs)


async def _producer(
    request: pytest.FixtureRequest,
    store: ConversationStore,
    record: ConversationRecordV2,
) -> _View:
    await store.put(PARTITION, record)
    view = _view(request, store)
    await view.initialize()
    await view.controller._restore_initial_exchange_record(record)
    return view


async def _stored(store: ConversationStore) -> ConversationRecordV2:
    record = await store.get(PARTITION, "c_review")
    assert isinstance(record, ConversationRecordV2)
    return record


def _contents(chat: Chat) -> list[str]:
    return [str(message["content"]) for message in chat.messages()]


def _assert_unaccepted(view: _View) -> None:
    with reactive.isolate():
        assert view.chat.user_input() is None
        assert view.chat._normal_user_submission() is None
    assert view.chat._transcript.open_exchange_id is None
    assert view.provider_inputs == []


@pytest.mark.anyio
async def test_root_bookmark_recapture_preserves_unavailable_and_ordinary_values(
    request: pytest.FixtureRequest, review_store: ConversationStore
) -> None:
    record = _record()
    original = record.nodes["original"].model_dump()
    record.set_active_leaf(record.root_id)
    producer = await _producer(request, review_store, record)
    pointer = await producer.stamp()
    assert pointer == {"conversation_id": "c_review", "node_id": record.root_id}

    root_view = _view(request, review_store, pointer=pointer)
    observed: list[dict[str, Any]] = []
    root_view.chat.history.on_restore(
        lambda values: observed.append(dict(values))
    )
    root_view.chat.history.on_save(lambda values: values.update(NEW_VALUES))
    await root_view.initialize()
    assert observed == [OLD_VALUES]
    assert _contents(root_view.chat) == []
    assert root_view.controller._exchange_recorder.record is not None
    assert (
        root_view.controller._exchange_recorder.record.active_leaf
        == record.root_id
    )

    # Public save is strict and recaptures the valid bookmarked root.
    assert await root_view.chat.history.save()
    rewritten = await _stored(review_store)
    assert (
        rewritten.nodes[record.root_id].state[VALUES_STATE_KEY].data
        == NEW_VALUES
    )
    assert VALUES_STATE_KEY not in rewritten.nodes["failed"].state
    assert rewritten.nodes["failed"].state[PREPARATION_STATE_KEY].data == {
        "terminal": True,
        "accepted": False,
        "app_values": "unavailable",
    }
    assert (
        rewritten.nodes["ordinary"].state[VALUES_STATE_KEY].data == OLD_VALUES
    )
    assert resolve_path_values(rewritten, "ordinary") == OLD_VALUES
    # The original's causal/display/model facts are untouched; only its
    # formerly inherited app values may be anchored to preserve their meaning.
    original_after = rewritten.nodes["original"].model_dump()
    original_after["state"].pop(VALUES_STATE_KEY)
    assert original_after == original
    with pytest.raises(ValueError, match="unavailable"):
        resolve_path_values(rewritten, "failed")
    _assert_unaccepted(root_view)

    rewritten.set_active_leaf("failed")
    await review_store.put(PARTITION, rewritten)
    failed_view = _view(request, review_store)
    failed_observed: list[dict[str, Any]] = []
    failed_view.chat.history.on_restore(
        lambda values: failed_observed.append(dict(values))
    )
    await failed_view.initialize()
    await failed_view.controller._restore_initial_exchange_record(
        await _stored(review_store)
    )
    assert failed_observed == []
    assert _contents(failed_view.chat) == ["replacement"]
    assert failed_view.controller._exchange_recorder.read_only
    assert not failed_view.chat.history._history_submission_admitted()
    _assert_unaccepted(failed_view)


@pytest.mark.anyio
async def test_legacy_pinned_values_are_ignored_when_marker_says_unavailable(
    request: pytest.FixtureRequest, review_store: ConversationStore
) -> None:
    record = _record()
    # This is legitimate e4f2021e sparse-child pinning output: an old writer
    # recaptures the root, pins its old values onto every entryless child,
    # and preserves the opaque preparation envelope. Do not reject this
    # combination as malformed or replay the pin as an observed snapshot.
    record.nodes["failed"].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data=OLD_VALUES.copy()
    )
    await review_store.put(PARTITION, record)
    loaded = await _stored(review_store)
    validate_active_path_state(loaded)
    assert node_is_terminal_incomplete(loaded.nodes["failed"])
    view = _view(request, review_store)
    observed: list[dict[str, Any]] = []
    view.chat.history.on_restore(lambda values: observed.append(dict(values)))
    await view.initialize()
    await view.controller._restore_initial_exchange_record(loaded)
    assert observed == []
    assert _contents(view.chat) == ["replacement"]
    assert (
        view.controller._exchange_recorder.read_only_reason
        == "terminal_incomplete"
    )
    assert view.controller._can_resubmit_active()
    with pytest.raises(ValueError, match="unavailable"):
        resolve_path_values(loaded, "failed")
    _assert_unaccepted(view)

    # Browse away and back through the real rewind path: the legacy pin
    # must not reappear in on_restore on return to the failed position.
    await view.controller.handle_navigate(
        0, "prev", request_id="browse-original"
    )
    assert observed == [OLD_VALUES]
    observed.clear()
    await view.controller.handle_navigate(0, "next", request_id="browse-failed")
    assert observed == []
    assert _contents(view.chat) == ["replacement"]
    _assert_unaccepted(view)


@pytest.mark.anyio
async def test_complete_empty_failed_snapshot_is_restored_not_inherited(
    request: pytest.FixtureRequest, review_store: ConversationStore
) -> None:
    record = _record(availability="complete")
    await review_store.put(PARTITION, record)
    restored = _view(request, review_store)
    observed: list[dict[str, Any]] = []
    restored.chat.history.on_restore(
        lambda values: observed.append(dict(values))
    )
    await restored.initialize()
    await restored.controller._restore_initial_exchange_record(
        await _stored(review_store)
    )
    assert observed == [{}]
    live = restored.controller._exchange_recorder.record
    assert live is not None
    assert live.active_leaf == "failed"
    assert live.nodes["failed"].state[VALUES_STATE_KEY].data == {}
    assert resolve_path_values(live, "failed") == {}
    assert restored.controller._exchange_recorder.read_only
    _assert_unaccepted(restored)


@pytest.mark.anyio
async def test_complete_marker_without_own_snapshot_fails_closed_before_restore(
    request: pytest.FixtureRequest, review_store: ConversationStore
) -> None:
    record = _record(availability="complete")
    del record.nodes["failed"].state[VALUES_STATE_KEY]
    await review_store.put(PARTITION, record)
    view = _view(request, review_store)
    observed: list[dict[str, Any]] = []
    view.chat.history.on_restore(lambda values: observed.append(dict(values)))
    await view.initialize()
    with pytest.raises(ValueError, match="complete"):
        validate_active_path_state(await _stored(review_store))
    with (
        pytest.warns(UserWarning, match="complete"),
        pytest.raises(ValueError, match="complete"),
    ):
        await view.controller._restore_initial_exchange_record(
            await _stored(review_store)
        )
    assert observed == []
    assert view.controller._exchange_recorder.record is None
    assert (await _stored(review_store)).model_dump() == record.model_dump()
    _assert_unaccepted(view)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "availability, expected_restores",
    [("complete", [{}]), ("unavailable", [])],
)
async def test_failed_bookmark_restores_selected_display_without_admission(
    request: pytest.FixtureRequest,
    review_store: ConversationStore,
    availability: str,
    expected_restores: list[dict[str, Any]],
) -> None:
    record = _record(availability=availability, failed_parent="original")
    producer = await _producer(request, review_store, record)
    pointer = await producer.stamp()
    assert pointer == {"conversation_id": "c_review", "node_id": "failed"}
    before = (await _stored(review_store)).model_dump()
    restored = _view(request, review_store, pointer=pointer)
    observed: list[dict[str, Any]] = []
    restored.chat.history.on_restore(
        lambda values: observed.append(dict(values))
    )
    await restored.initialize()

    recorder = restored.controller._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == "failed"
    failed = recorder.record.nodes["failed"]
    assert node_is_terminal_incomplete(failed)
    assert not failed.is_checkpoint
    assert (
        failed.error is not None
        and failed.error.message == HISTORY_ERROR_NOT_SENT
    )
    assert recorder.read_only_reason == "terminal_incomplete"
    assert not recorder.source_isolated
    assert restored.controller._can_resubmit_active()
    assert not restored.chat.history._history_submission_admitted()
    assert observed == expected_restores
    assert _contents(restored.chat) == [
        "original",
        "original reply",
        "replacement",
    ]
    assert restored.controller.adapter.get_turns_json() == [
        {"role": "user", "content": "original"},
        {"role": "assistant", "content": "original reply"},
    ]
    update = _history_updates(restored.session)[-1]
    assert update["active_read_only"] is True
    assert update["active_can_resubmit"] is True
    metadata = [
        message["action"]["data"]
        for message in restored.session.messages
        if message["action"]["type"] == "update_exchange_metadata"
    ][-1]
    assert metadata[2]["preparation_failed"] is True
    assert metadata[2]["error_message"] == HISTORY_ERROR_NOT_SENT
    assert metadata[2]["retryable"] is True
    # The normal Chat seam remains closed at a terminal display position.
    await restored.chat._record_accepted_user_input_with_capture(
        ChatMessage(content="must not dispatch", role="user")
    )
    assert _contents(restored.chat) == [
        "original",
        "original reply",
        "replacement",
    ]
    assert (await _stored(review_store)).model_dump() == before
    _assert_unaccepted(restored)


@pytest.mark.anyio
async def test_pending_bookmark_is_not_promoted_or_written_by_restoring_view(
    request: pytest.FixtureRequest, review_store: ConversationStore
) -> None:
    record = _record()
    record.set_active_leaf(record.root_id)
    producer = await _producer(request, review_store, record)
    recorder = producer.controller._exchange_recorder
    assert recorder.record is not None
    async with producer.controller._exchange_mutation():
        recorder.stage_input_locked(
            "pending",
            record.root_id,
            _stored_message("user", "still producing"),
        )
        await recorder.persist_record_locked()
    pointer = await producer.stamp()
    assert pointer == {"conversation_id": "c_review", "node_id": "pending"}
    before = (await _stored(review_store)).model_dump()
    restored = _view(request, review_store, pointer=pointer)
    with pytest.warns(UserWarning, match="not a valid checkpoint"):
        await restored.initialize()
    assert restored.controller._exchange_recorder.record is None
    assert _contents(restored.chat) == []
    assert not restored.controller._can_resubmit_active()
    assert (await _stored(review_store)).model_dump() == before
    _assert_unaccepted(restored)
