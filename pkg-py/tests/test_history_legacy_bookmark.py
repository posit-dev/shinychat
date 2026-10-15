"""Legacy v1 bookmark stamp restore (shinychat#dmgt, plan §7.8, mechanism D6).

A bookmark written by a v1 server stamps only the conversation id, under the
legacy `{id}_history_conversation_id` key. Under the exchange-tree path,
`_init_history` reads that key when the v2 pointer is absent and opens the
stamped conversation at its active leaf — through the same open path a v2
pointer takes, so the restore works transparently once the v1→v2
upgrade-on-read lands (shinychat#e0x2). Until then, a v1 record fails
visibly at the schema check; it is never a silent no-restore.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, cast
from unittest.mock import MagicMock, patch

import pytest
import shinychat._history as history_module
from shiny import reactive
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    CapturedMessage,
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
        patch.object(history_module, "_EXCHANGE_TREE_HISTORY_V2", True),
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
async def test_v2_legacy_stamp_v1_record_fails_loudly_before_upgrade_on_read():
    """Pre-shinychat#e0x2 pin: a v1 record fails visibly at the schema check.

    Until the v1→v2 upgrade-on-read lands (shinychat#e0x2), opening a v1
    record under the v2 path raises in `HistoryController._get_record`. The
    bookmark restore must surface that failure — naming the conversation —
    never a silent no-restore. The companion xfail test below holds the
    full-restore assertion for once the read-gate exists.
    """
    chat_id = "legacy_stamp_v1_record"
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
        notification = MagicMock()

        with (
            patch("shiny.ui.notification_show", notification),
            session_context(cast(Any, session)),
            reactive.isolate(),
            pytest.warns(
                UserWarning,
                match=(
                    r"Could not load conversation 'c_v1': "
                    r"Conversation record schema does not match the active "
                    r"history path"
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
@pytest.mark.xfail(
    reason=(
        "v1→v2 upgrade-on-read lands with shinychat#e0x2; until then a v1 "
        "record fails loudly at the schema check (pinned by "
        "test_v2_legacy_stamp_v1_record_fails_loudly_before_upgrade_on_read)"
    ),
    strict=True,
)
async def test_v2_legacy_stamp_v1_record_restores_after_upgrade_on_read():
    """Full restore of a v1-stamped conversation once the read-gate lands."""
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
        assert recorder.record.id == "c_v1"
        assert controller._active_id_now() == "c_v1"
    finally:
        chat.destroy()
