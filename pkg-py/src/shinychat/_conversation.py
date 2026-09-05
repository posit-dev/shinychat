from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from ._attachments import Attachment, validate_attachments
from ._chat_types import ChatMessage, StoredMessage
from ._history_client import _validate_mapping_keys, as_turns_adapter
from ._history_state import _ExchangeState
from ._history_store import ConversationPartition, ConversationStore
from ._history_types import (
    CapturedMessage,
    ConversationRecordV2,
    check_schema_version,
    new_conversation_record_v2,
)
from ._utils import private_random_id


class Conversation:
    """Continue exchange-tree history without a Shiny session.

    Use `create()` or `load()` with the app's store, resolved chat ID,
    and trusted owner scope. The caller authorizes access and serializes the
    entire load/work/save operation with other writers, including the app.
    A partition is a storage namespace, not an authorization check.

    The client supplies ``get_turns()`` and ``set_turns()`` (for example, a
    chatlas Chat). Shinychat records its turns independently of the Markdown
    appended for display. This class never invokes the model or starts a
    worker. It uses the same exchange records and turn capture/restore as
    Shiny's history controller. Only v2 exchange-tree records are supported.
    """

    def __init__(
        self,
        store: ConversationStore,
        partition: ConversationPartition,
        client: Any,
        record: ConversationRecordV2,
    ) -> None:
        self._store = store
        self._partition = partition
        self._state = _ExchangeState(as_turns_adapter(client))
        self._state.record = record
        self._exchange_id: str | None = None

    @property
    def _record(self) -> ConversationRecordV2:
        assert self._state.record is not None
        return self._state.record

    @classmethod
    async def create(
        cls,
        store: ConversationStore,
        partition: ConversationPartition,
        *,
        client: Any,
        title: str = "New chat",
    ) -> Conversation:
        """Create and save a conversation with the client's initial turns."""
        adapter = as_turns_adapter(client)
        conversation = cls(
            store,
            partition,
            client,
            new_conversation_record_v2(
                title=title, client_info=adapter.client_info()
            ),
        )
        await conversation._state._capture_state("n_0000", "root_close")
        conversation._record.finish_exchange("n_0000", "ok", None)
        await conversation.save()
        return conversation

    @classmethod
    async def load(
        cls,
        store: ConversationStore,
        partition: ConversationPartition,
        conversation_id: str,
        *,
        client: Any,
        exchange_id: str | None = None,
    ) -> Conversation:
        """Load the selected branch and restore its provider turns.

        Missing, unsupported, or malformed history raises before changing
        the client. Incompatible provider turns also raise: a worker must
        not silently continue with an incomplete model context.

        Pass ``exchange_id`` to load an earlier, completed checkpoint after
        interrupted work. Loading does not change the saved selection;
        the next exchange or explicit `save()` persists it.
        """
        record = await store.get(partition, conversation_id)
        if record is None:
            raise ValueError(f"Conversation {conversation_id!r} was not found.")
        if not isinstance(record, ConversationRecordV2):
            raise ValueError(
                "Conversation requires exchange-tree history (v2)."
            )
        if record.id != conversation_id:
            raise ValueError(
                "Stored conversation ID does not match the requested ID."
            )
        conversation = cls(
            store, partition, client, record.model_copy(deep=True)
        )
        if exchange_id is not None:
            conversation._record.set_active_leaf(exchange_id)
        await conversation._restore(conversation._record)
        return conversation

    @property
    def id(self) -> str:
        """The stable conversation ID, shared with Shiny's history UI."""
        return self._record.id

    @property
    def active_leaf(self) -> str:
        """The selected exchange ID; pass it to `select()` to return here."""
        assert self._record.active_leaf is not None
        return self._record.active_leaf

    @property
    def values(self) -> dict[str, Any]:
        """Application values shared with ``chat.history.on_save/on_restore``.

        Use an application-owned key and version its payload, for example
        ``values["deputy"] = {"version": 1, "run_id": run_id}``. Values must
        be JSON-serializable. They belong to the conversation, not a branch.
        Call `save()` after changes outside an exchange.
        """
        return self._record.values

    async def _restore(self, record: ConversationRecordV2) -> None:
        if check_schema_version(record.schema_version) != 2:
            raise ValueError(
                "Conversation requires exchange-tree history (v2)."
            )
        node_ids = tuple(record.path_node_ids())
        if not node_ids:
            raise ValueError("Exchange-tree record has no active path.")
        self._require_captured_turns(record)
        planned = self._state._preflight_rewind_state(record, node_ids)
        await self._state._rewind_state(planned)
        self._state.record = record

    @staticmethod
    def _require_captured_turns(record: ConversationRecordV2) -> None:
        assert record.active_leaf is not None
        selected = record.nodes[record.active_leaf]
        if (
            selected.status == "pending"
            or "shinychat:turns" not in selected.state
        ):
            raise ValueError(
                "Selected exchange has incomplete provider state. "
                "Select an earlier exchange with captured turns."
            )

    async def select(self, exchange_id: str) -> None:
        """Select and save an existing exchange, restoring its provider turns.

        The next `exchange()` adds a child here. Existing descendants
        remain available, so selecting an earlier exchange and submitting
        new input creates an alternative continuation.

        Selection is applied to the client before saving. If persistence
        fails, retry `save()` or discard this handle and load it again.
        """
        self._require_idle()
        target = self._record.model_copy(
            deep=True, update={"values": self.values}
        )
        target.set_active_leaf(exchange_id)
        await self._restore(target)
        await self.save()

    def _require_idle(self) -> None:
        if self._exchange_id is not None:
            raise RuntimeError("An exchange is already in progress.")

    @asynccontextmanager
    async def exchange(
        self, input: str, *, attachments: list[Attachment] | None = None
    ) -> AsyncIterator[str]:
        """Record one user input and the work performed in this context.

        Yields its exchange ID. Input is saved before work starts; each
        `append_message()` saves display output. On exit, save provider
        turns and mark the exchange completed, failed, or cancelled. Errors
        propagate to the caller; persisted errors use Shiny's safe summary.
        Process termination leaves the last saved checkpoint pending.

        The caller sends input to the model, including any attachments.
        Call this method before compacting turns so the changed model
        context is captured on the new exchange, leaving its parent intact.
        """
        self._require_idle()
        if not isinstance(input, str):
            raise TypeError("Input must be a Markdown string.")
        self._require_captured_turns(self._record)
        message = StoredMessage.from_chat_message(
            ChatMessage(input, role="user", attachments=attachments)
        )
        validate_attachments(message.attachments)
        exchange_id = private_random_id()
        self._exchange_id = exchange_id
        try:
            target = self._record.model_copy(
                deep=True, update={"values": self.values}
            )
            target.open_exchange(exchange_id, message)
            await self._save_record(target)
            self._state.record = target
            try:
                yield exchange_id
            except BaseException as error:
                status = (
                    "cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else "error"
                )
                try:
                    await self._finish(exchange_id, status)
                except BaseException as save_error:
                    raise error from save_error
                raise
            else:
                await self._finish(exchange_id, "ok")
        finally:
            self._exchange_id = None

    async def append_message(self, content: str) -> None:
        """Save an assistant Markdown message in the current exchange.

        This does not change provider turns. Call it repeatedly to checkpoint
        separate messages; it does not stream or replace an earlier message.
        """
        if self._exchange_id is None:
            raise RuntimeError("append_message() requires an exchange context.")
        if not isinstance(content, str):
            raise TypeError("Content must be a Markdown string.")
        message = StoredMessage.from_chat_message(ChatMessage(content))
        # A checkpoint is still pending until the exchange context exits.
        target = self._record.model_copy(
            deep=True, update={"values": self.values}
        )
        target.append_stream_message(
            self._exchange_id,
            CapturedMessage.from_stored_message(message, icon=None),
        )
        await self._save_record(target)
        self._state.record = target

    async def _finish(
        self, exchange_id: str, status: Literal["ok", "error", "cancelled"]
    ) -> None:
        self._record.finish_exchange(exchange_id, status, None)
        try:
            await self._state._capture_state(exchange_id, "stream_finish")
        except BaseException:
            self._record.finish_exchange(exchange_id, "error", None)
            raise
        finally:
            await self.save()

    async def save(self) -> None:
        """Save application values and the latest display/state checkpoint.

        Provider turns are captured when the exchange context exits. Saving
        alone does not capture model work or complete an exchange.
        """
        await self._save_record(self._record)

    async def _save_record(self, record: ConversationRecordV2) -> None:
        _validate_mapping_keys(record.values)
        json.dumps(record.values, allow_nan=False)
        # Store implementations may retain references. Give them a snapshot,
        # so further work cannot change a saved checkpoint without a put().
        await self._store.put(self._partition, record.model_copy(deep=True))
