from __future__ import annotations

import asyncio
import dataclasses
import warnings
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from ._attachments import Attachment, validate_attachments
from ._chat_types import (
    HistoryNavigateAction,
    HistoryUpdateAction,
    UpdateInputAction,
    UpdateSiblingsAction,
)
from ._history_bookmark import delete_bookmark_state, extract_state_id
from ._history_client import (
    TurnsAdapter,
    as_turns_adapter,
    turn_fallback_markdown,
)
from ._history_store import (
    ConversationPartition,
    ConversationStore,
    resolve_store,
)
from ._history_title import (
    MAX_TITLE_LEN,
    TitleFn,
    fallback_title,
    generate_title,
)

# NB: shiny is imported lazily inside methods throughout this module; a
# top-level import would be circular (shiny.ui._chat imports shinychat).
from ._history_types import (
    ConversationRecord,
    check_schema_version,
    new_conversation_id,
    new_conversation_record,
)

if TYPE_CHECKING:
    from htmltools import HTML, Tag, TagList
    from shiny import reactive
    from shiny.module import ResolvedId
    from shiny.reactive._reactives import Effect_

    from ._chat import Chat
    from ._chat_types import ChatGreeting


@dataclasses.dataclass(frozen=True)
class HistoryInputIds:
    """All Shiny input IDs owned by the history feature for a given chat."""

    browser_token: ResolvedId
    current_id: ResolvedId
    url_id: ResolvedId
    select: ResolvedId
    new: ResolvedId
    rename: ResolvedId
    delete: ResolvedId
    message_edit: ResolvedId
    message_navigate: ResolvedId

    @classmethod
    def for_chat(cls, chat_id: ResolvedId) -> HistoryInputIds:
        from shiny.module import ResolvedId as RID

        return cls(
            browser_token=RID(f"{chat_id}_history_browser_token"),
            current_id=RID(f"{chat_id}_history_current_id"),
            url_id=RID(f"{chat_id}_history_url_id"),
            select=RID(f"{chat_id}_history_select"),
            new=RID(f"{chat_id}_history_new"),
            rename=RID(f"{chat_id}_history_rename"),
            delete=RID(f"{chat_id}_history_delete"),
            message_edit=RID(f"{chat_id}_message_edit"),
            message_navigate=RID(f"{chat_id}_message_navigate"),
        )

    def all_ids(self) -> list[ResolvedId]:
        return [getattr(self, f.name) for f in dataclasses.fields(self)]


class HistoryOptions:
    """
    Configuration for :class:`~shinychat.Chat` conversation history.

    Pass an instance to ``Chat(history=...)``.

    Parameters
    ----------
    restore_mode
        How a previous conversation is reloaded when the page opens.
        ``"browser"`` (the default) stores the active conversation ID in
        localStorage so it survives page reloads without changing the URL.
        ``"url"`` keeps the active conversation ID as a plain
        ``?shinychat_conversation_id=<id>`` query parameter so users can
        bookmark or share a link to a specific conversation; no Shiny server
        bookmarking is required.
        ``"none"`` disables automatic restore entirely.
        ``"bookmark"`` participates in Shiny server bookmarking: after every
        LLM response a fresh server bookmark is minted and the address bar
        updates to ``?_state_id_=...``. Requires ``bookmark_store="server"``
        in the Shiny app. On in-session conversation switches, navigates to
        the target conversation's bookmark URL if one exists. Use this mode
        when the app uses Shiny bookmarks to capture full input state
        alongside the chat.

        The ``values`` dict captured by ``@chat.history.on_save`` callbacks
        is restored by ``@chat.history.on_restore`` in every restore mode,
        including ``"bookmark"``. Callbacks run after the target conversation
        becomes active. Raw Shiny input values (sliders, text boxes, etc.) are
        not synced automatically; use ``on_restore`` to update them on both
        page-load restores and in-session switches.
    store
        Where conversations are persisted. ``"auto"`` (the default) picks
        ``FileConversationStore`` in most environments and defers to the
        platform on Posit Connect. ``"memory"`` keeps conversations in
        process only (useful for testing). ``"file"`` always uses the file
        system. Pass a fully-constructed ``ConversationStore`` instance for
        custom back-ends.
    scope
        Storage namespace for conversations. A string or a callable that
        returns a string. When ``None`` (the default) the authenticated
        ``session.user`` is used; for unauthenticated sessions a
        per-browser localStorage token is used instead.

        Pass a shared string to allow multiple users to share history —
        for example ``session.groups[0]`` to scope by group, or a
        constant like ``"global"`` to share across all users.
    title
        Controls how a new conversation is named. ``"auto"`` (the default)
        generates a title from the first exchange using the LLM. Pass a
        ``TitleFn`` callable to use custom logic instead. Pass ``None`` to
        skip LLM titling entirely — the conversation keeps its initial
        timestamp-based name.
    """

    def __init__(
        self,
        restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = "browser",
        store: "ConversationStore | Literal['auto', 'memory', 'file']" = "auto",
        scope: "str | Callable[..., str] | None" = None,
        title: "TitleFn | Literal['auto'] | None" = "auto",
        max_store_mb: float | None = 100.0,
    ) -> None:
        self.restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = (
            restore_mode
        )
        self.store: "ConversationStore | Literal['auto', 'memory', 'file']" = (
            store
        )
        self.scope: "str | Callable[..., str] | None" = scope
        self.title: "TitleFn | Literal['auto'] | None" = title
        self.max_store_mb: float | None = max_store_mb


def extend_record_linear(
    record: ConversationRecord,
    turn_groups: list[list[dict[str, Any]]],
    ui_messages: list[dict[str, Any]],
    *,
    ui_offset: int,
) -> None:
    """
    Append turn groups beyond the record's current path as new linear nodes,
    and attach the not-yet-saved UI messages (everything past `ui_offset`) to
    the new nodes: each user message goes to the next new user-turn node; all
    other messages go to the last appended node.

    Each group is one or more turns that form a single exchange unit — e.g. a
    tool-call round (assistant-request, user-result, assistant-text) is one
    group, matching the single combined UI message produced by streaming.
    """
    existing = len(record.path_node_ids())
    new_groups = turn_groups[existing:]

    new_node_ids = [record.append_linear(g) for g in new_groups]
    user_nodes = [
        nid
        for nid in new_node_ids
        if record.nodes[nid].turns[0].get("role") == "user"
    ]

    # When a later save brings UI messages but no new turn groups (e.g. a
    # streamed reply arriving after a synchronous side-channel append),
    # attach them to the current leaf instead of dropping them.
    fallback = new_node_ids[-1] if new_node_ids else record.current_leaf
    if fallback is None:
        return  # empty record and no new groups: nothing to attach to

    for message in ui_messages[ui_offset:]:
        if message.get("role") == "user" and user_nodes:
            target = user_nodes.pop(0)
        else:
            target = fallback
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
        client: Any,
        save_callbacks: "list[Callable[[dict[str, Any]], None]] | None" = None,
        restore_callbacks: "list[Callable[[dict[str, Any]], None]] | None" = None,
        max_store_bytes: int | None = None,
    ):
        self.chat = chat
        self.adapter = adapter
        self.store = store
        self.title_fn = title_fn
        self.title_enabled = title_enabled
        self.client = client
        # List references: mutations to the originals (e.g. registering new
        # callbacks after _start()) are visible here because we share the same
        # list object, not a copy.
        self._save_callbacks: list[Callable[[dict[str, Any]], None]] = (
            save_callbacks if save_callbacks is not None else []
        )
        self._restore_callbacks: list[Callable[[dict[str, Any]], None]] = (
            restore_callbacks if restore_callbacks is not None else []
        )

        self.partition: ConversationPartition | None = None
        self.record: ConversationRecord | None = None  # None => unsaved draft
        # Active conversation identity, separate from `record`: an
        # identified draft (submitted but not yet saved) has an ID and no
        # record. All record/identity mutations go through
        # activate_record()/clear_active() so that when a record exists, its
        # `id` equals the active ID.
        from shiny import reactive

        self._active_id: "reactive.Value[str | None]" = reactive.Value(None)
        self.ui_offset = 0  # messages already attached to nodes
        # Set by enable() when restore_mode="url"; called with the new
        # conversation id (or None) after any switch that changes the active
        # conversation.
        self.on_active_id_change: (
            Callable[[str | None], Awaitable[None]] | None
        ) = None
        # Internal hook: fired after every save. bookmark mode uses it to mint.
        self.on_response_saved: (
            Callable[[ConversationRecord], Awaitable[None]] | None
        ) = None
        # Internal hook: fired in switch_to before the in-session swap.
        # Return True to skip the swap (caller has already navigated).
        self.on_pre_switch: (
            Callable[[ConversationRecord], Awaitable[bool]] | None
        ) = None
        # Internal hook: fired before a conversation is removed from the store.
        self.on_evict: Callable[[str], Awaitable[None]] | None = None
        # Internal hook: fired whenever it's known whether the active
        # conversation is a restore (True) or a fresh/new one (False) - at
        # the initial restore decision, and again on every new_chat(). Lets
        # greeting generation defer to this instead of racing the client's
        # independent `{id}_greeting_requested` request.
        self.on_settled: Callable[[bool], Awaitable[None]] | None = None
        self.max_store_bytes: int | None = max_store_bytes
        self._title_task: asyncio.Task[None] | None = None
        self._over_budget_warned: bool = False

    # -- active conversation identity --------------------------------------

    def conversation_id(self) -> str | None:
        """
        Reactive read of the active conversation ID: ``None`` for an empty
        draft, otherwise the ID the eventual ``ConversationRecord`` will (or
        already does) carry. Allocated at first user submission for
        ``chat_app()`` apps, or at first save for standalone history use.

        Like any reactive read, this requires a reactive context;
        non-reactive callers must wrap it in ``shiny.reactive.isolate()``.
        """
        return self._active_id()

    def _active_id_now(self) -> str | None:
        # Non-reactive read: controller methods run both inside and outside
        # reactive contexts.
        from shiny import reactive

        with reactive.isolate():
            return self._active_id()

    async def ensure_conversation_id(self) -> str:
        """
        Return the active conversation ID, allocating one when the active
        conversation is an empty draft. Repeated calls for the same active
        conversation return the same ID.
        """
        id = self._active_id_now()
        if id is None:
            id = new_conversation_id()
            await self._set_active_id(id)
        return id

    async def activate_record(self, record: ConversationRecord) -> None:
        """
        Activate a stored record. This (with ``clear_active()``) is the
        shared operation every restore/switch/init/delete/new-chat path must
        use, so that ``record`` and the active ID never move independently:
        when ``record`` is not ``None``, the active ID must equal
        ``record.id``.
        """
        self.record = record
        await self._set_active_id(record.id)

    async def clear_active(self) -> None:
        self.record = None
        await self._set_active_id(None)

    async def _set_active_id(self, id: str | None) -> None:
        # Single writer for the active ID; notifies on_active_id_change only
        # on an actual change (e.g. first save after ensure_conversation_id()
        # does not re-fire).
        if self._active_id_now() == id:
            return
        self._active_id.set(id)
        if self.on_active_id_change is not None:
            await self.on_active_id_change(id)

    async def _get_record(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | None:
        record = await self.store.get(partition, conv_id)
        if record is not None:
            check_schema_version(record.schema_version)
        return record

    async def _put_record(
        self, partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        check_schema_version(record.schema_version)
        await self.store.put(partition, record)

    # -- save -----------------------------------------------------------

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response.

        The server-side message accumulator and recorded turns are read before
        writing the record. Reads and writes are separated by awaits
        (``store.put``, eviction, bookmark mint), but this is safe without an
        explicit lock because Shiny serializes reactive flushes behind a
        single process-wide ``reactive.lock()`` for the full duration of
        effect execution.
        """
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        turn_groups = self.adapter.get_turns_grouped()
        messages = self.chat._messages_for_bookmark()

        first_save = self.record is None
        if not first_save:
            record = self.record
            if record is None:
                raise RuntimeError("HistoryController not initialized")
            stored_ui = [
                m
                for nid in record.path_node_ids()
                for m in (record.nodes[nid].ui or [])
            ]
            # Idempotent + truncation guard. A restore may trigger the
            # response effect while the server still has the restored
            # conversation. Never let that state overwrite the record. Skip
            # when there are no new turn groups and the server message list is
            # no longer than what's already stored.
            if len(turn_groups) <= len(record.path_node_ids()) and len(
                messages
            ) <= len(stored_ui):
                return

        if first_save:
            turns_flat = self.adapter.get_turns_json()
            # Adopt the active ID allocated at submission time (or allocate
            # one now for standalone history users), so the saved record
            # carries the identity model work was already tagged with.
            new_record = new_conversation_record(
                title=fallback_title(turns_flat),
                id=await self.ensure_conversation_id(),
            )
            new_record.client_info = self.adapter.client_info()
            await self.activate_record(new_record)

        record = self.record
        if record is None:
            raise RuntimeError("HistoryController not initialized")
        extend_record_linear(
            record, turn_groups, messages, ui_offset=self.ui_offset
        )
        record.response_count += 1
        self._capture_app_state(record)
        await self._put_record(self.partition, record)
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(record)
        self.ui_offset = len(messages)
        await self.send_history_update()
        await self._send_sibling_metadata()

        # Wait for the second response before titling: gives the LLM/custom
        # title_fn more context than a single exchange, and avoids spending
        # a call on conversations abandoned after one message. response_count
        # (not turn/node counts) drives this, since a single response's
        # turn-group count isn't fixed across client types.
        if (
            self.title_enabled
            and record.title_source is None
            and record.response_count == 2
        ):
            turns_flat = self.adapter.get_turns_json()
            self._title_task = asyncio.create_task(self.retitle(turns_flat))
            self._title_task.add_done_callback(title_task_done)

    async def retitle(self, turns: list[dict[str, Any]]) -> None:
        target = self.record  # capture before the slow LLM call
        if target is None or target.title_source == "user":
            return
        title = await generate_title(self.title_fn, self.client, turns)
        if (
            title is None
            or self.record is not target
            or target.title_source == "user"
        ):
            return  # conversation switched away or user renamed mid-call
        target.title = title
        target.title_source = "llm"
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        await self._put_record(self.partition, target)
        await self.send_history_update()

    def cancel_pending(self) -> None:
        """Cancel in-flight background work (e.g. titling) at teardown."""
        if self._title_task is not None and not self._title_task.done():
            self._title_task.cancel()

    async def notify_settled(self, restored: bool) -> None:
        """Called whenever it's known whether the active conversation is a restore."""
        if self.on_settled is not None:
            await self.on_settled(restored)

    async def _evict_one(self, conv_id: str) -> None:
        assert self.partition is not None
        if self.on_evict is not None:
            await self.on_evict(conv_id)
        await self.store.delete(self.partition, conv_id)

    async def _evict_if_needed(self) -> None:
        if self.max_store_bytes is None or self.partition is None:
            return
        metas = await self.store.list(self.partition)
        total = sum(m.size_bytes for m in metas)
        if total <= self.max_store_bytes:
            return
        for meta in reversed(metas):  # oldest first
            if self.record is not None and meta.id == self.record.id:
                continue
            total -= meta.size_bytes
            await self._evict_one(meta.id)
            if total <= self.max_store_bytes:
                break
        if total > self.max_store_bytes and not self._over_budget_warned:
            self._over_budget_warned = True
            warnings.warn(
                "Chat history for this partition remains over the "
                f"{self.max_store_bytes}-byte limit after evicting all "
                "evictable conversations — the active conversation alone "
                "exceeds the limit.",
                stacklevel=1,
            )

    async def save(self) -> bool:
        """Persist app state for the active conversation."""
        if not await self.save_current():
            return False
        record = self.record
        assert record is not None
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(record)
        await self.send_history_update()
        await self._send_sibling_metadata()
        return True

    async def save_current(self) -> bool:
        """Persist the active conversation if it has ever been saved."""
        if self.record is None or self.partition is None:
            return False
        turn_groups = self.adapter.get_turns_grouped()
        messages = self.chat._messages_for_bookmark()
        extend_record_linear(
            self.record, turn_groups, messages, ui_offset=self.ui_offset
        )
        self._capture_app_state(self.record)
        await self._put_record(self.partition, self.record)
        self.ui_offset = len(messages)
        return True

    def _capture_app_state(self, record: ConversationRecord) -> None:
        values: dict[str, Any] = {}
        for cb in self._save_callbacks:
            cb(values)
        record.values = values

    def _restore_app_state(self, values: dict[str, Any]) -> None:
        for cb in self._restore_callbacks:
            cb(values)

    # -- switch / new ----------------------------------------------------

    async def switch_to(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        if self.record is not None and conv_id == self.record.id:
            return
        # Load BEFORE mutating anything: a failed load must leave the
        # current conversation untouched.
        target = await self._get_record(self.partition, conv_id)
        if target is None:
            raise RuntimeError(f"Conversation {conv_id!r} no longer exists.")

        await self.save_current()
        if self.on_pre_switch is not None:
            skip = await self.on_pre_switch(target)
            if skip:
                return
        self.adapter.set_turns_json(target.path_turns())
        await self.replay_ui(target)
        await self.activate_record(target)
        self._restore_app_state(target.values or {})
        await self._send_sibling_metadata()
        await self.send_history_update()

    async def new_chat(self) -> None:
        await self.save_current()
        self.adapter.set_turns_json([])
        await self.chat.clear_messages()
        self.ui_offset = 0
        # Announce the cleared state even when the active ID is already None:
        # in URL/bookmark restore modes the browser may still carry a stale
        # conversation param (e.g. after a failed restore) that only
        # on_active_id_change(None) clears.
        was_identified = self._active_id_now() is not None
        await self.clear_active()
        if not was_identified and self.on_active_id_change is not None:
            await self.on_active_id_change(None)
        # A fresh chat is never a restore: resolve the greeting the same way
        # the initial settle does, so it doesn't just rely on a stale/absent
        # cached value from that first resolution.
        await self.notify_settled(False)
        await self.send_history_update()

    async def replay_ui(self, record: ConversationRecord) -> None:
        await self.chat.clear_messages()
        # A restored conversation is never a "new chat" — the app's
        # greeting doesn't belong here, regardless of `persistent`.
        await self.chat.set_greeting(None)
        restored_count = 0
        for node_id in record.path_node_ids():
            node = record.nodes[node_id]
            stored = node.ui or [
                {
                    "role": node.turns[-1].get("role", "assistant"),
                    "segments": [
                        {
                            "content": turn_fallback_markdown(node.turns[-1]),
                            "content_type": "markdown",
                        }
                    ],
                }
            ]
            for message_dict in stored:
                # Records written while #272 was active could contain
                # browser-supplied dependency URLs. Keep their rendered
                # content for compatibility, but never replay those URLs.
                safe_message = {
                    **message_dict,
                    "segments": [
                        {
                            key: value
                            for key, value in segment.items()
                            if key != "html_deps"
                        }
                        for segment in message_dict.get("segments", [])
                    ],
                }
                await self.chat._restore_bookmark_message(safe_message)
                restored_count += 1
        # The restored messages are already in the server-side accumulator, so
        # start the offset after the messages restored into the record.
        self.ui_offset = restored_count

    # -- list mutations ----------------------------------------------------

    async def rename(self, conv_id: str, title: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        title = " ".join(title.split())[:MAX_TITLE_LEN]
        if not title:
            return
        record = (
            self.record
            if self.record is not None and self.record.id == conv_id
            else await self._get_record(self.partition, conv_id)
        )
        if record is None:
            return
        record.title = title
        record.title_source = "user"
        await self._put_record(self.partition, record)
        await self.send_history_update()

    async def delete(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        if self.on_evict is not None:
            await self.on_evict(conv_id)
        await self.store.delete(self.partition, conv_id)
        if self.record is not None and self.record.id == conv_id:
            await self.clear_active()
            self.adapter.set_turns_json([])
            await self.chat.clear_messages()
            self.ui_offset = 0
        await self.send_history_update()

    # -- branch navigation --------------------------------------------------

    async def _send_sibling_metadata(self) -> None:
        if self.record is None:
            return
        sibling_meta = self.record.path_sibling_metadata()
        if not sibling_meta:
            # No "clear all badges" payload is needed. A badge only exists at a
            # fork point (a node with >1 sibling), and forks are permanent:
            # navigating between siblings keeps that node's sibling count > 1,
            # and nothing prunes nodes from a record. So a path that currently
            # has no forks never had one, meaning there is no stale badge to
            # clear — empty here always means the client already shows none.
            return
        data: dict[int, dict[str, int]] = {}
        msg_idx = 0
        for nid in self.record.path_node_ids():
            n_ui = self.record.nodes[nid].ui_message_count()
            if nid in sibling_meta:
                idx, total = sibling_meta[nid]
                data[msg_idx] = {"index": idx, "total": total}
            msg_idx += n_ui
        if data:
            action: UpdateSiblingsAction = {
                "type": "update_siblings",
                "data": data,
            }
            await self.chat._send_action(action)

    async def handle_navigate(self, message_index: int, direction: str) -> None:
        if direction not in ("prev", "next"):
            return
        if self.record is None:
            return
        node_id, _ = self.record.node_id_for_message_index(message_index)
        siblings = self.record.siblings_of(node_id)
        current_pos = siblings.index(node_id)

        if direction == "prev":
            if current_pos == 0:
                return
            target = siblings[current_pos - 1]
        else:
            if current_pos == len(siblings) - 1:
                return
            target = siblings[current_pos + 1]

        leaf = self.record.subtree_leaf(target)
        self.record.set_current_leaf(leaf)
        self.adapter.set_turns_json(self.record.path_turns())
        await self.replay_ui(self.record)
        await self._send_sibling_metadata()
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        await self._put_record(self.partition, self.record)
        await self.send_history_update()

    async def handle_edit(
        self,
        message_index: int,
        content: str,
        attachments: "list[dict[str, Any]] | None" = None,
    ) -> None:
        if self.record is None:
            return

        node_id, _ = self.record.node_id_for_message_index(message_index)
        fork_parent = self.record.nodes[node_id].parent

        # Branching happens implicitly: truncating current_leaf here means the next
        # append_linear (from the resubmit's on_response) creates a sibling under
        # fork_parent, not a child of the old leaf. We don't call branch_from here
        # because there's no new turn content yet — that arrives via on_response.
        self.record.set_current_leaf(fork_parent)
        self.adapter.set_turns_json(self.record.path_turns())
        await self.replay_ui(self.record)
        await self._send_sibling_metadata()
        action: UpdateInputAction = {
            "type": "update_input",
            "value": content,
            "submit": True,
        }
        if attachments is not None:
            # Same normalize-then-validate pattern as the regular (non-edit)
            # send path in _input_handler.py and Chat.update_user_input —
            # never trust client-side attachment validation alone.
            parsed = [Attachment.model_validate(a) for a in attachments]
            validate_attachments(parsed)
            action["attachments"] = [
                {
                    "mime": a.mime,
                    "data_url": a.data_url,
                    "name": a.name,
                    "size": a.size,
                }
                for a in parsed
            ]
            # Edits always replace the attachment set — the client's staged
            # tray is a single source of truth, never a delta to append.
            action["attachment_mode"] = "set"
        await self.chat._send_action(action)

    # -- protocol ----------------------------------------------------------

    async def send_navigate(
        self,
        url: str | None,
        active_id: str | None,
        *,
        reload: bool = False,
    ) -> None:
        action: HistoryNavigateAction = {
            "type": "history_navigate",
            "url": url,
            "active_id": active_id,
        }
        if reload:
            action["reload"] = True
        await self.chat._send_action(action)

    async def send_history_update(self) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        metas = await self.store.list(self.partition)
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


async def do_bookmark_with_cleanup(
    bookmark: Any, on_bookmarked: Callable[[str], Awaitable[None]]
) -> None:
    cancel = bookmark.on_bookmarked(on_bookmarked)
    try:
        await bookmark.do_bookmark()
    finally:
        cancel()


class ChatHistory:
    """Namespace for chat history configuration and lifecycle on a `Chat` instance."""

    def __init__(
        self, chat: "Chat", config: HistoryOptions | None = None
    ) -> None:
        self._chat = chat
        self._started: bool = False
        self._controller: HistoryController | None = None
        self._save_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        self._restore_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        # Session-level registrations made by `_start()`, tracked so they can
        # be released when the owning Chat is destroyed (e.g. same-id
        # reconstruction) instead of leaking until session end.
        self._effects: "list[Effect_]" = []
        self._session_end_cancel: "Callable[[], None] | None" = None
        self._on_session_end: "Callable[[], None] | None" = None
        cfg = config if config is not None else HistoryOptions()
        self._store: "ConversationStore | Literal['auto', 'memory', 'file']" = (
            cfg.store
        )
        self._scope: "str | Callable[..., str] | None" = cfg.scope
        self._title: "TitleFn | Literal['auto'] | None" = cfg.title
        self._restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = (
            cfg.restore_mode
        )
        self._max_store_mb: float | None = cfg.max_store_mb

    def enable(self) -> None:
        """Enable chat history for the current session. No-op if already started."""
        if not self._started:
            self._start()

    def _teardown(self) -> None:
        """
        Release session-level registrations when the owning `Chat` is destroyed
        or replaced by a same-id reconstruction.

        Destroys the history input effects — which otherwise keep answering the
        shared input ids and retain the old controller for the rest of the
        session — unregisters the session-end callback, and runs the cleanup
        that session end would have run. No-op if history never started; safe
        to call more than once.
        """
        for effect in self._effects:
            effect.destroy()
        self._effects.clear()
        cancel = self._session_end_cancel
        self._session_end_cancel = None
        if cancel is not None:
            cancel()
        on_end = self._on_session_end
        self._on_session_end = None
        if on_end is not None:
            on_end()

    def conversation_id(self) -> str | None:
        """
        Reactive read of the active conversation ID.

        Returns ``None`` when history is disabled (or hasn't started for this
        session) or the active conversation is an empty draft; otherwise the
        ID allocated at the first user submission, which the saved
        conversation record carries. The ID is stable across client swaps
        (``chat.client.set()``) and is retained when a response fails or is
        cancelled, so a retry keeps the same identity.

        Like any reactive read, this must be called inside a reactive context
        (e.g. a ``@reactive.effect`` or ``@render.*`` function); non-reactive
        callers must wrap it in ``shiny.reactive.isolate()``.
        """
        controller = self._controller
        if controller is None:
            return None
        return controller.conversation_id()

    async def save(self) -> bool:
        """
        Persist the active conversation and its app state.

        Returns ``False`` before history has started or when there is no saved
        active conversation. Storage and bookmark errors propagate to the caller.
        """
        controller = self._controller
        if controller is None:
            return False
        return await controller.save()

    def on_save(
        self, fn: "Callable[[dict[str, Any]], None]"
    ) -> "Callable[[dict[str, Any]], None]":
        """
        Decorator. Register a callback fired whenever the active conversation is saved.

        The callback receives a mutable ``values`` dict; write any per-conversation
        app state you want to persist into it. Fires on each LLM response (to
        capture fresh state) and when the user switches to a different conversation::

            @chat.history.on_save
            def _(values):
                values["selected_tab"] = current_tab()

        Multiple callbacks can be registered and run in registration order.
        Safe to call before ``enabled = True``.
        """
        self._save_callbacks.append(fn)
        return fn

    def on_restore(
        self, fn: "Callable[[dict[str, Any]], None]"
    ) -> "Callable[[dict[str, Any]], None]":
        """
        Decorator. Register a callback fired when a conversation is loaded.

        Fires on page-load restores in every ``restore_mode``, including
        ``"bookmark"``, and on in-session conversation switches. The target
        conversation is active before callbacks run. Use it to sync auxiliary
        UI state — active tabs, model selectors, etc. — to match the restored
        conversation. Raw Shiny input values are not synced automatically;
        call the appropriate ``ui.update_*()`` functions here.

        The callback receives the ``values`` dict that was captured by the
        corresponding ``on_save`` callback::

            @chat.history.on_restore
            def _(values):
                ui.update_navs("tabs", selected=values.get("selected_tab"))

        Multiple callbacks can be registered and run in registration order.
        Safe to call before ``enabled = True``.

        """
        self._restore_callbacks.append(fn)
        return fn

    def setup_greeting(
        self,
        greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any]",
    ) -> None:
        """
        Wire `greeting` resolution to fire once history's restore decision is
        settled (at startup, and again on every `new_chat()`), instead of
        racing the client's independent `{id}_greeting_requested` request.

        Only call this when `self._controller is not None` (i.e. history has
        actually started for this session).
        """
        from ._chat_client import resolve_greeting

        chat = self._chat
        controller = self._controller
        assert controller is not None

        async def _on_settled(restored: bool) -> None:
            if not restored:
                await resolve_greeting(chat, greeting)

        controller.on_settled = _on_settled

    def _start(self) -> None:
        chat = self._chat
        chat_client = chat.client
        if chat_client is None:
            raise ValueError(
                "Chat history requires a client. Pass one to Chat(client=...)."
            )

        from shiny import reactive, req
        from shiny.session import get_current_session, session_context

        session = get_current_session()
        if session is None or session.is_stub_session():
            return

        root_session = session.root_scope()
        restore_mode = self._restore_mode

        ids = HistoryInputIds.for_chat(chat.id)
        root_session.bookmark.exclude.extend(ids.all_ids())

        adapter = as_turns_adapter(chat_client)
        resolved_store = resolve_store(self._store)
        title = self._title
        scope_key = self._scope
        max_store_bytes = (
            int(self._max_store_mb * 1024 * 1024)
            if self._max_store_mb is not None
            else None
        )
        controller = HistoryController(
            chat=chat,
            adapter=adapter,
            store=resolved_store,
            title_fn=title if callable(title) else None,
            title_enabled=title is not None,
            client=chat_client,
            save_callbacks=self._save_callbacks,
            restore_callbacks=self._restore_callbacks,
            max_store_bytes=max_store_bytes,
        )
        self._controller = controller

        if restore_mode == "url":

            async def _update_url(conv_id: str | None) -> None:
                url = (
                    f"?shinychat_conversation_id={conv_id}"
                    if conv_id is not None
                    else None
                )
                await controller.send_navigate(url, conv_id)

            controller.on_active_id_change = _update_url

        if restore_mode == "bookmark":
            if root_session.bookmark.store != "server":
                raise ValueError(
                    "restore_mode='bookmark' requires bookmark_store='server' in the Shiny app."
                )

            async def _on_response_saved(record: ConversationRecord) -> None:
                captured_id = record.id

                async def _on_bookmarked(url: str) -> None:
                    new_state_id = extract_state_id(url)
                    if new_state_id is None:
                        return
                    if (
                        controller.record is None
                        or controller.record.id != captured_id
                    ):
                        return  # switched away
                    old_state_id = record.bookmark_state_id
                    record.bookmark_state_id = new_state_id
                    if old_state_id is not None:
                        await delete_bookmark_state(old_state_id)
                    if controller.partition is not None:
                        await controller._put_record(
                            controller.partition, record
                        )
                    await controller.send_navigate(
                        f"?_state_id_={new_state_id}", captured_id
                    )

                await do_bookmark_with_cleanup(
                    root_session.bookmark, _on_bookmarked
                )

            controller.on_response_saved = _on_response_saved

            async def _on_pre_switch(target: ConversationRecord) -> bool:
                if target.bookmark_state_id is not None:
                    await controller.send_navigate(
                        f"?_state_id_={target.bookmark_state_id}",
                        target.id,
                        reload=True,
                    )
                    return True
                return False

            controller.on_pre_switch = _on_pre_switch

            async def _on_evict(conv_id: str) -> None:
                if (
                    controller.record is not None
                    and controller.record.id == conv_id
                ):
                    state_id = controller.record.bookmark_state_id
                else:
                    if controller.partition is None:
                        rec = None
                    else:
                        rec = await controller._get_record(
                            controller.partition, conv_id
                        )
                    state_id = (
                        rec.bookmark_state_id if rec is not None else None
                    )
                if state_id is not None:
                    await delete_bookmark_state(state_id)

            controller.on_evict = _on_evict

            async def _update_url_bookmark(conv_id: str | None) -> None:
                if conv_id is None:
                    await controller.send_navigate(None, None, reload=True)

            controller.on_active_id_change = _update_url_bookmark

        # Stamp the active conversation ID into any Shiny server bookmark so
        # that reloading from a bookmark URL reopens the right conversation.
        # This runs regardless of restore_mode whenever server bookmarks are
        # configured — the history system participates automatically.
        stamp_key = f"{chat.id}_history_conversation_id"
        stamp_cancel: Callable[[], None] | None = None
        if root_session.bookmark.store == "server":

            def stamp_conversation(state: Any) -> None:
                if controller.record is not None:
                    state.values[stamp_key] = controller.record.id

            stamp_cancel = root_session.bookmark.on_bookmark(stamp_conversation)

        @reactive.calc
        def scope() -> str:
            # For restore_mode "browser"/"url", the active conversation id
            # arrives from the client only after Shiny's first reactive flush
            # (dispatched inside initializedPromise.then(), same microtask as
            # browser_token). If scope resolved immediately (session.user or
            # a caller scope_key), the init effect would run on that first
            # flush and read current_id/url_id as None permanently.
            # Requiring browser_token here — even when unused for the
            # returned value — forces scope() to wait for the second flush,
            # by which point all three inputs have arrived.
            # Temporary: some session types raise AttributeError on .user;
            # remove this getattr once the pending py-shiny PR lands.
            user = getattr(chat._session, "user", None)
            if restore_mode in ("browser", "url") and (
                scope_key is not None or user is not None
            ):
                token = chat._session.input[ids.browser_token]()
                req(token)
            if isinstance(scope_key, str):
                return scope_key
            if callable(scope_key):
                return scope_key(chat._session)
            if user is not None:
                # session.user is expected to be a stable, per-identity
                # string by Shiny convention; two users whose str(user)
                # values collide would share a history scope.
                return str(user)
            token = chat._session.input[ids.browser_token]()
            return str(req(token))

        async def notify_error(prefix: str, e: Exception) -> None:
            import warnings

            from shiny import ui as shiny_ui

            warnings.warn(f"{prefix}: {e}", stacklevel=1)
            with session_context(session):
                shiny_ui.notification_show(f"{prefix}: {e}", type="error")

        initialized = False

        @reactive.effect
        async def _init_history():
            nonlocal initialized
            if initialized:
                return

            owner_scope = scope()  # req() retries until token arrives
            controller.partition = ConversationPartition(
                chat_id=str(chat.id), scope=owner_scope
            )

            # Priority 1: restore from a Shiny bookmark context (any mode).
            restore_ctx = root_session.bookmark._restore_context
            restored_conv_id: str | None = None
            if restore_ctx is not None and restore_ctx.active:
                raw_id = restore_ctx.values.get(stamp_key)
                restored_conv_id = str(raw_id) if raw_id else None

            if restored_conv_id is not None:
                try:
                    target = await controller._get_record(
                        controller.partition, restored_conv_id
                    )
                except Exception as e:
                    await notify_error("Could not load conversation", e)
                    target = None
                if target is not None:
                    adapter.set_turns_json(target.path_turns())
                    await controller.replay_ui(target)
                    await controller.activate_record(target)
                    controller._restore_app_state(target.values or {})
                    await controller._send_sibling_metadata()
                    await controller.send_history_update()
                    initialized = True
                    await controller.notify_settled(True)
                    return

            # Priority 2: restore from the mode-specific ID source.
            # Reading these inputs may raise SilentException if the browser
            # hasn't sent them yet (they're delivered after Shiny's
            # initializedPromise resolves, which is after the first flush).
            # Keep initialized=False until after send_history_update() so
            # the effect retries correctly on the next flush rather than
            # exiting early via the guard above.
            if restore_mode == "url":
                raw = chat._session.input[ids.url_id]()
                current_id: str | None = str(raw) if raw else None
            elif restore_mode == "browser":
                raw = chat._session.input[ids.current_id]()
                current_id = str(raw) if raw else None
            else:
                current_id = None

            if current_id:
                try:
                    pointed = await controller._get_record(
                        controller.partition, current_id
                    )
                except Exception as e:
                    await notify_error("Could not load conversation", e)
                    pointed = None
                if pointed is not None:
                    adapter.set_turns_json(pointed.path_turns())
                    await controller.replay_ui(pointed)
                    await controller.activate_record(pointed)
                    controller._restore_app_state(pointed.values or {})
                    await controller._send_sibling_metadata()
            await controller.send_history_update()
            initialized = True
            await controller.notify_settled(controller.record is not None)

        @reactive.effect
        @reactive.event(chat.messages, ignore_init=True)
        async def _save_on_response():
            if controller.partition is None:
                return
            messages = chat.messages()
            if messages and messages[-1].get("role") == "assistant":
                try:
                    await controller.on_response()
                except Exception as e:
                    await notify_error("Could not save conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.select])
        async def _on_select():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.select]()
            try:
                await controller.switch_to(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not open conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.new])
        async def _on_new():
            if controller.partition is None:
                return
            try:
                await controller.new_chat()
            except Exception as e:
                await notify_error("Could not start a new chat", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.rename])
        async def _on_rename():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.rename]()
            try:
                await controller.rename(
                    str(payload["id"]), str(payload["title"])
                )
            except Exception as e:
                await notify_error("Could not rename conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.delete])
        async def _on_delete():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.delete]()
            try:
                await controller.delete(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not delete conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_edit])
        async def _on_edit():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.message_edit]()
            try:
                await controller.handle_edit(
                    int(payload["index"]),
                    str(payload["content"]),
                    payload.get("attachments"),
                )
            except Exception as e:
                await notify_error("Could not edit message", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_navigate])
        async def _on_navigate():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.message_navigate]()
            try:
                await controller.handle_navigate(
                    int(payload["index"]), str(payload["direction"])
                )
            except Exception as e:
                await notify_error("Could not navigate messages", e)

        def _on_session_end() -> None:
            # The session consumed the registration by firing it; keep the
            # tracked state truthful so a later `_teardown()` won't re-run.
            self._session_end_cancel = None
            self._on_session_end = None
            if stamp_cancel is not None:
                stamp_cancel()
            controller.cancel_pending()

        self._effects.extend(
            [
                _init_history,
                _save_on_response,
                _on_select,
                _on_new,
                _on_rename,
                _on_delete,
                _on_edit,
                _on_navigate,
            ]
        )
        self._on_session_end = _on_session_end
        self._session_end_cancel = session.on_ended(_on_session_end)
        self._started = True
