from __future__ import annotations

import asyncio
import warnings
from typing import TYPE_CHECKING, Any

from ._chat_types import HistoryUpdateAction
from ._history_bridge import BookmarkBridge
from ._history_client import TurnsAdapter, turn_fallback_markdown
from ._history_store import ConversationStore
from ._history_title import (
    MAX_TITLE_LEN,
    TitleFn,
    fallback_title,
    generate_title,
)
from ._history_types import ConversationRecord, new_conversation_record

if TYPE_CHECKING:
    from ._chat import Chat


def extend_record_linear(
    record: ConversationRecord,
    turns: list[dict[str, Any]],
    ui_messages: list[dict[str, Any]],
    *,
    ui_offset: int,
) -> None:
    """
    Append turns beyond the record's current path as new linear nodes, and
    attach the not-yet-saved UI messages (everything past `ui_offset`) to the
    new nodes: each user message goes to the next new user-turn node; all
    other messages go to the last appended node.
    """
    existing = len(record.path_node_ids())
    new_turns = turns[existing:]
    if not new_turns:
        return

    new_node_ids = [record.append_linear(t) for t in new_turns]
    user_nodes = [
        nid
        for nid in new_node_ids
        if record.nodes[nid].turn.get("role") == "user"
    ]

    for message in ui_messages[ui_offset:]:
        if message.get("role") == "user" and user_nodes:
            target = user_nodes.pop(0)
        else:
            target = new_node_ids[-1]
        node = record.nodes[target]
        node.ui = [*(node.ui or []), message]


class HistoryController:
    """Session-scoped orchestrator for conversation history."""

    def __init__(
        self,
        *,
        chat: Chat,
        adapter: TurnsAdapter,
        store: ConversationStore,
        title_fn: TitleFn | None,
        title_enabled: bool,
        raw_client: Any,
    ):
        self.chat = chat
        self.adapter = adapter
        self.store = store
        self.title_fn = title_fn
        self.title_enabled = title_enabled
        self.raw_client = raw_client

        self.scope: str | None = None
        self.record: ConversationRecord | None = None  # None => unsaved draft
        self.baseline_values: dict[str, Any] = {}
        self.ui_offset = 0  # messages already attached to nodes
        self.bridge: BookmarkBridge | None = None
        self._title_task: asyncio.Task[None] | None = None
        # replay_ui pulses chat.messages, which fires the reactive save effect
        # once redundantly (the UI was just restored, nothing new to persist).
        # Setting this flag causes on_response to skip the first call after a
        # replay, then clear itself so subsequent real responses are saved.
        self._suppress_next_save: bool = False

    # -- save -----------------------------------------------------------

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response."""
        if self._suppress_next_save:
            self._suppress_next_save = False
            return
        assert self.scope is not None
        turns = self.adapter.get_turns_json()
        messages = self.chat._messages_for_bookmark()

        first_save = self.record is None
        if first_save:
            self.record = new_conversation_record(title=fallback_title(turns))
            self.record.client_info = self.adapter.client_info()

        record = self.record
        assert record is not None
        extend_record_linear(record, turns, messages, ui_offset=self.ui_offset)
        self.ui_offset = len(messages)
        if self.bridge is not None:
            record.values = await self.bridge.capture()
        await self.store.put(self.scope, record)
        await self.send_history_update()

        if first_save and self.title_enabled:
            self._title_task = asyncio.create_task(self.retitle(turns))
            self._title_task.add_done_callback(title_task_done)

    async def retitle(self, turns: list[dict[str, Any]]) -> None:
        target = self.record  # capture before the slow LLM call
        if target is None or target.title_source == "user":
            return
        title = await generate_title(self.title_fn, self.raw_client, turns)
        if (
            title is None
            or self.record is not target
            or target.title_source == "user"
        ):
            return  # conversation switched away or user renamed mid-call
        target.title = title
        target.title_source = "llm"
        assert self.scope is not None
        await self.store.put(self.scope, target)
        await self.send_history_update()

    def cancel_pending(self) -> None:
        """Cancel in-flight background work (e.g. titling) at teardown."""
        if self._title_task is not None and not self._title_task.done():
            self._title_task.cancel()

    async def save_current(self) -> None:
        """Persist the active conversation if it has ever been saved."""
        if self.record is None or self.scope is None:
            return
        turns = self.adapter.get_turns_json()
        messages = self.chat._messages_for_bookmark()
        extend_record_linear(
            self.record, turns, messages, ui_offset=self.ui_offset
        )
        self.ui_offset = len(messages)
        if self.bridge is not None:
            self.record.values = await self.bridge.capture()
        await self.store.put(self.scope, self.record)

    # -- switch / new ----------------------------------------------------

    async def switch_to(self, conv_id: str) -> None:
        assert self.scope is not None
        if self.record is not None and conv_id == self.record.id:
            return
        # Load BEFORE mutating anything: a failed load must leave the
        # current conversation untouched.
        target = await self.store.get(self.scope, conv_id)
        if target is None:
            raise RuntimeError(f"Conversation {conv_id!r} no longer exists.")

        await self.save_current()
        self.adapter.set_turns_json(target.path_turns())
        await self.replay_ui(target)
        if self.bridge is not None:
            await self.bridge.restore(target.values)
        self.record = target
        await self.send_history_update()

    async def new_chat(self) -> None:
        await self.save_current()
        self.adapter.set_turns_json([])
        await self.chat.clear_messages()
        self.ui_offset = 0
        if self.bridge is not None:
            await self.bridge.restore(self.baseline_values)
        self.record = None
        await self.send_history_update()

    async def replay_ui(self, record: ConversationRecord) -> None:
        await self.chat.clear_messages()
        for node_id in record.path_node_ids():
            node = record.nodes[node_id]
            stored = node.ui or [
                {
                    "role": node.turn.get("role", "assistant"),
                    "segments": [
                        {
                            "content": turn_fallback_markdown(node.turn),
                            "content_type": "markdown",
                        }
                    ],
                }
            ]
            for message_dict in stored:
                await self.chat._restore_bookmark_message(message_dict)
        self.ui_offset = len(self.chat._messages_for_bookmark())
        self._suppress_next_save = True

    # -- list mutations ----------------------------------------------------

    async def rename(self, conv_id: str, title: str) -> None:
        assert self.scope is not None
        title = " ".join(title.split())[:MAX_TITLE_LEN]
        if not title:
            return
        record = (
            self.record
            if self.record is not None and self.record.id == conv_id
            else await self.store.get(self.scope, conv_id)
        )
        if record is None:
            return
        record.title = title
        record.title_source = "user"
        await self.store.put(self.scope, record)
        await self.send_history_update()

    async def delete(self, conv_id: str) -> None:
        assert self.scope is not None
        await self.store.delete(self.scope, conv_id)
        if self.record is not None and self.record.id == conv_id:
            # Deleting the active conversation acts like "New chat"
            # (without re-saving the deleted record).
            self.record = None
            self.adapter.set_turns_json([])
            await self.chat.clear_messages()
            self.ui_offset = 0
            if self.bridge is not None:
                await self.bridge.restore(self.baseline_values)
        await self.send_history_update()

    # -- protocol ----------------------------------------------------------

    async def send_history_update(self) -> None:
        assert self.scope is not None
        metas = await self.store.list(self.scope)
        action: HistoryUpdateAction = {
            "type": "history_update",
            "enabled": True,
            "conversations": [m.model_dump(mode="json") for m in metas],
            "active_id": self.record.id if self.record is not None else None,
        }
        await self.chat._send_action(action)


def title_task_done(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        warnings.warn(f"Background retitle failed: {exc}", stacklevel=1)
