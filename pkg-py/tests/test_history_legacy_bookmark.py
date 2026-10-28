"""Legacy v1 bookmark stamp restore (shinychat#dmgt, plan §7.8, mechanism D6).

A bookmark written by a v1 server stamps only the conversation id, under the
legacy `{id}_history_conversation_id` key. Under the exchange-tree path,
`_init_history` reads that key when the v2 pointer is absent and opens the
stamped conversation at its active leaf — through the same open path a v2
pointer takes. Since the v1→v2 upgrade-on-read (shinychat#e0x2), a v1
record restores transparently; a record no released version can read still
fails visibly — it is never a silent no-restore.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, cast
from unittest.mock import MagicMock, patch

import pytest
from shiny import reactive
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    MAX_SCHEMA_VERSION,
    CapturedMessage,
    ConversationRecordV1,
    ConversationRecordV2,
    new_conversation_record,
    new_conversation_record_v2,
)
from shinychat.types import HistoryOptions
from test_chat_history import (
    _capture_history_effects,
    _history_updates,
    _LiveSession,
    _MockClient,
)


def _stored_message(role: str, content: str) -> StoredMessage:
    return StoredMessage(
        role=role,  # type: ignore[arg-type]
        segments=[StoredSegment(content=content, content_type="markdown")],
    )


def _target_record(id: str, *, with_exchange: bool = True):
    """A v2 record whose stored active leaf is a completed exchange."""
    target = new_conversation_record_v2(title="target", id=id, client_info={})
    if with_exchange:
        target.open_exchange("n_0001", _stored_message("user", "restore me"))
        target.append_message(
            "n_0001",
            CapturedMessage.from_stored_message(
                _stored_message("assistant", "restored reply"), icon=None
            ),
        )
        target.finish_exchange("n_0001", "ok", None)
        target.nodes["n_0001"].checkpoint = "valid"
    return target


async def _make_legacy_bookmark_chat(
    chat_id: str,
    session: _LiveSession,
    store: InMemoryConversationStore,
    restore_values: dict[str, Any],
) -> tuple[Chat, dict[str, Callable[[], Awaitable[None]]]]:
    session.bookmark.store = "server"
    session.bookmark._restore_context = MagicMock(
        active=True, values=restore_values
    )
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}
    with (
        patch.object(reactive, "effect", _capture_history_effects(handlers)),
        session_context(cast(Any, session)),
    ):
        chat = Chat(
            chat_id,
            client=cast(Any, _MockClient()),
            history=HistoryOptions(
                store=store,
                scope="test",
                restore_mode="bookmark",
            ),
        )
    return chat, handlers


@pytest.mark.anyio
async def test_v2_legacy_stamp_restores_conversation_at_active_leaf() -> None:
    """A v1 bookmark (conversation id only) restores at the record's leaf."""
    chat_id = "legacy_stamp_active_leaf"
    session = _LiveSession()
    store = InMemoryConversationStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, _target_record("c_target"))
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {f"{chat_id}_history_conversation_id": "c_target"},
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None

        with (
            session_context(cast(Any, session)),
            reactive.isolate(),
        ):
            await handlers["_init_history"]()

        assert chat.history._initial_history_initialized
        assert recorder.record is not None
        assert recorder.record.id == "c_target"
        # The legacy stamp carries no node: the conversation opens at its
        # stored active leaf (the completed exchange), not the root.
        assert recorder.record.active_leaf == "n_0001"
        assert controller._active_id_now() == "c_target"
        updates = _history_updates(session)
        assert len(updates) == 1
        assert updates[0]["active_id"] == "c_target"
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_pointer_stamp_takes_precedence_over_legacy_stamp() -> None:
    """When both keys exist, the v2 pointer wins."""
    chat_id = "legacy_stamp_precedence"
    session = _LiveSession()
    store = InMemoryConversationStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, _target_record("c_pointer"))
    await store.put(partition, _target_record("c_legacy"))
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {
            f"{chat_id}_history_exchange_pointer": {
                "conversation_id": "c_pointer",
                "node_id": "n_0000",
            },
            f"{chat_id}_history_conversation_id": "c_legacy",
        },
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None

        with (
            session_context(cast(Any, session)),
            reactive.isolate(),
        ):
            await handlers["_init_history"]()

        assert chat.history._initial_history_initialized
        assert recorder.record is not None
        assert recorder.record.id == "c_pointer"
        # The pointer named the root, so the leaf is the root — and the
        # legacy-stamped conversation stayed closed.
        assert recorder.record.active_leaf == "n_0000"
        assert controller._active_id_now() == "c_pointer"
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_legacy_stamp_unknown_conversation_fails_visibly() -> None:
    """A bookmark can outlive its record; restore fails visibly (§3.8)."""
    chat_id = "legacy_stamp_unknown_conversation"
    session = _LiveSession()
    store = InMemoryConversationStore()
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {f"{chat_id}_history_conversation_id": "c_missing"},
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        notification = MagicMock()

        with (
            patch("shiny.ui.notification_show", notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(
                UserWarning,
                match=(
                    r"Could not load conversation 'c_missing': "
                    r"Bookmark conversation is unavailable"
                ),
            ),
        ):
            await handlers["_init_history"]()

        notification.assert_called_once()
        assert chat.history._initial_history_initialized
        assert recorder.record is None
        assert controller._active_id_now() is None
    finally:
        chat.destroy()


@pytest.mark.parametrize("bogus", ["", 123, {"conversation_id": "c_target"}])
@pytest.mark.anyio
async def test_v2_legacy_stamp_bogus_value_fails_visibly(bogus: Any) -> None:
    """Corrupt legacy stamps warn loudly instead of restoring nothing."""
    chat_id = "legacy_stamp_bogus_value"
    session = _LiveSession()
    store = InMemoryConversationStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(partition, _target_record("c_target"))
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {f"{chat_id}_history_conversation_id": bogus},
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        notification = MagicMock()

        with (
            patch("shiny.ui.notification_show", notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(
                UserWarning,
                match=r"Could not load conversation: Bookmark pointer is invalid",
            ),
        ):
            await handlers["_init_history"]()

        notification.assert_called_once()
        assert chat.history._initial_history_initialized
        assert recorder.record is None
        assert controller._active_id_now() is None
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_legacy_stamp_unsupported_record_fails_loudly():
    """A record no released version can read fails visibly — never silently.

    Originally pinned the pre-read-gate v1 failure (shinychat#e0x2); v1
    records now restore through the upgrade-on-read, so the loud-failure
    guarantee is pinned with a record from a newer, unsupported schema
    version instead — the same never-silent-no-restore contract: the
    restore surfaces a warning naming the conversation and a notification.
    """
    chat_id = "legacy_stamp_unsupported_record"
    session = _LiveSession()

    class _FutureSchemaStore(InMemoryConversationStore):
        """Simulates a downgrade against a store written by a future version."""

        async def get(self, partition: Any, conv_id: str) -> Any:
            record = await super().get(partition, conv_id)
            if record is not None:
                cast(Any, record).schema_version = MAX_SCHEMA_VERSION + 1
            return record

    store = _FutureSchemaStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(
        partition, new_conversation_record(title="future", id="c_future")
    )
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {f"{chat_id}_history_conversation_id": "c_future"},
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        notification = MagicMock()

        with (
            patch("shiny.ui.notification_show", notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(
                UserWarning,
                match=(
                    r"Could not load conversation 'c_future': "
                    r"Unsupported conversation record schema version: 3"
                ),
            ),
        ):
            await handlers["_init_history"]()

        notification.assert_called_once()
        assert chat.history._initial_history_initialized
        assert recorder.record is None
        assert controller._active_id_now() is None
    finally:
        chat.destroy()


@pytest.mark.anyio
async def test_v2_legacy_stamp_v1_record_restores_after_upgrade_on_read():
    """A v1-stamped conversation fully restores once the read-gate lands.

    Originally pinned as a strict xfail until shinychat#e0x2 landed the
    v1→v2 upgrade-on-read (the companion test above held the loud-failure
    pin for the pre-gate behavior). The legacy stamp now opens the v1
    record through the same path a v2 pointer takes: it is upgraded in
    memory at the active leaf, installed as the recorder's record, and
    becomes the active conversation.
    """
    chat_id = "legacy_stamp_v1_record_upgraded"
    session = _LiveSession()
    store = InMemoryConversationStore()
    partition = ConversationPartition(chat_id=chat_id, scope="test")
    await store.put(
        partition, new_conversation_record(title="legacy", id="c_v1")
    )
    chat, handlers = await _make_legacy_bookmark_chat(
        chat_id,
        session,
        store,
        {f"{chat_id}_history_conversation_id": "c_v1"},
    )
    try:
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None

        with (
            session_context(cast(Any, session)),
            reactive.isolate(),
        ):
            await handlers["_init_history"]()

        assert chat.history._initial_history_initialized
        assert recorder.record is not None
        assert isinstance(recorder.record, ConversationRecordV2)
        assert not isinstance(recorder.record, ConversationRecordV1)
        assert recorder.record.schema_version == 2
        assert recorder.record.id == "c_v1"
        assert recorder.record.title == "legacy"
        # The pointerless v1 record upgrades at the synthesized root — the
        # same shape a fresh v2 record has.
        assert recorder.record.active_leaf == "n_0000"
        assert controller._active_id_now() == "c_v1"
    finally:
        chat.destroy()
