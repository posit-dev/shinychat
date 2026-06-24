from __future__ import annotations

import asyncio
import warnings
from typing import TYPE_CHECKING, Any, Callable, Literal

from ._chat_types import HistoryNavigateAction, HistoryUpdateAction
from ._history_bookmark import BookmarkMinter
from ._history_client import (
    TurnsAdapter,
    as_turns_adapter,
    turn_fallback_markdown,
)
from ._history_store import ConversationStore, resolve_store
from ._history_title import (
    MAX_TITLE_LEN,
    TitleFn,
    fallback_title,
    generate_title,
)
from ._history_types import ConversationRecord, new_conversation_record

if TYPE_CHECKING:
    from ._chat import Chat


class HistoryOptions:
    """
    Configuration for :class:`~shinychat.Chat` conversation history.

    Pass an instance to ``Chat(history=...)``.

    Parameters
    ----------
    restore_mode
        How a previous conversation is reloaded when the page opens.
        ``"browser"`` (the default) stores the active conversation ID in
        localStorage so it survives page reloads. ``"url"`` encodes the ID
        in a server bookmark URL (requires ``bookmark_store="server"``).
        ``"none"`` disables automatic restore entirely.

        Note: on an in-session conversation switch only the ``values`` dict
        written by ``@chat.history.on_save`` callbacks is restored. Raw
        Shiny input values (sliders, text boxes, etc.) are **not** restored
        the way a full URL bookmark reload would restore them.
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
        Controls how a new conversation is named. Pass a ``TitleFn``
        callable to generate a title from the first exchange, ``"fallback"``
        to use a generic timestamp-based name, or ``None`` to let the LLM
        decide.
    """

    def __init__(
        self,
        restore_mode: "Literal['browser', 'url', 'none']" = "browser",
        store: "ConversationStore | Literal['auto', 'memory', 'file']" = "auto",
        scope: "str | Callable[..., str] | None" = None,
        title: "TitleFn | Literal['fallback'] | None" = None,
        max_store_mb: float = 100.0,
    ) -> None:
        self.restore_mode: "Literal['browser', 'url', 'none']" = restore_mode
        self.store: "ConversationStore | Literal['auto', 'memory', 'file']" = store
        self.scope: "str | Callable[..., str] | None" = scope
        self.title: "TitleFn | Literal['fallback'] | None" = title
        self.max_store_mb: float = max_store_mb


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

        self.scope: str | None = None
        self.record: ConversationRecord | None = None  # None => unsaved draft
        self.baseline_values: dict[str, Any] = {}
        self.ui_offset = 0  # messages already attached to nodes
        self.minter: BookmarkMinter | None = None  # set in restore_mode="url"
        self.max_store_bytes: int | None = max_store_bytes
        self._title_task: asyncio.Task[None] | None = None
        # replay_ui contains multiple await points (one per message), so
        # _save_on_response can fire at each yield — before replay finishes.
        # _is_replaying suppresses all of those in-flight fires; it is set
        # before the first await and cleared in a finally block.
        # _suppress_next_save handles the single post-replay reactive flush
        # that fires after _is_replaying is already False; it is consumed once.
        self._is_replaying: bool = False
        self._suppress_next_save: bool = False

    # -- save -----------------------------------------------------------

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response."""
        if self._is_replaying:
            return
        if self._suppress_next_save:
            self._suppress_next_save = False
            return
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
        turns = self.adapter.get_turns_json()
        messages = self.chat._messages_for_bookmark()

        first_save = self.record is None
        if first_save:
            self.record = new_conversation_record(title=fallback_title(turns))
            self.record.client_info = self.adapter.client_info()

        record = self.record
        if record is None:
            raise RuntimeError("HistoryController not initialized")
        extend_record_linear(record, turns, messages, ui_offset=self.ui_offset)
        await self._capture_app_state(record)
        await self.store.put(self.scope, record)
        await self._evict_if_needed()
        self.ui_offset = len(messages)
        await self.send_history_update()

        if first_save and self.title_enabled:
            self._title_task = asyncio.create_task(self.retitle(turns))
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
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
        await self.store.put(self.scope, target)
        await self.send_history_update()

    def cancel_pending(self) -> None:
        """Cancel in-flight background work (e.g. titling) at teardown."""
        if self._title_task is not None and not self._title_task.done():
            self._title_task.cancel()

    async def _evict_one(self, conv_id: str) -> None:
        assert self.scope is not None
        if self.minter is not None:
            record = await self.store.get(self.scope, conv_id)
            if record is not None and record.bookmark_state_id is not None:
                try:
                    await self.minter.delete_state(record.bookmark_state_id)
                except Exception:
                    pass
        await self.store.delete(self.scope, conv_id)

    async def _evict_if_needed(self) -> None:
        if self.max_store_bytes is None or self.scope is None:
            return
        total = await self.store.total_size(self.scope)
        if total <= self.max_store_bytes:
            return
        metas = await self.store.list(self.scope)
        for meta in reversed(metas):  # oldest first
            if self.record is not None and meta.id == self.record.id:
                continue
            await self._evict_one(meta.id)
            total = await self.store.total_size(self.scope)
            if total <= self.max_store_bytes:
                break

    async def save_current(self) -> None:
        """Persist the active conversation if it has ever been saved."""
        if self.record is None or self.scope is None:
            return
        turns = self.adapter.get_turns_json()
        messages = self.chat._messages_for_bookmark()
        extend_record_linear(
            self.record, turns, messages, ui_offset=self.ui_offset
        )
        await self._capture_app_state(self.record)
        await self.store.put(self.scope, self.record)
        self.ui_offset = len(messages)

    async def _capture_app_state(self, record: ConversationRecord) -> None:
        values: dict[str, Any] = {}
        for cb in self._save_callbacks:
            cb(values)
        record.values = values
        if self.minter is not None:
            try:
                await self.minter.mint_if_needed(record)
            except Exception as e:
                warnings.warn(f"Bookmark mint failed: {e}", stacklevel=2)

    async def _restore_app_state(self, values: dict[str, Any]) -> None:
        for cb in self._restore_callbacks:
            cb(values)

    # -- switch / new ----------------------------------------------------

    async def switch_to(self, conv_id: str) -> None:
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
        if self.record is not None and conv_id == self.record.id:
            return
        # Load BEFORE mutating anything: a failed load must leave the
        # current conversation untouched.
        target = await self.store.get(self.scope, conv_id)
        if target is None:
            raise RuntimeError(f"Conversation {conv_id!r} no longer exists.")

        await self.save_current()
        if self.minter is not None and target.bookmark_state_id is not None:
            await self.send_navigate(
                self.minter.url_with_state(target.bookmark_state_id), target.id
            )
            return
        self.adapter.set_turns_json(target.path_turns())
        await self.replay_ui(target)
        await self._restore_app_state(target.values or {})
        self.record = target
        await self.send_history_update()

    async def new_chat(self) -> None:
        await self.save_current()
        if self.minter is not None:
            await self.send_navigate(self.minter.base_url(), None)
            return
        self.adapter.set_turns_json([])
        await self.chat.clear_messages()
        self.ui_offset = 0
        await self._restore_app_state(self.baseline_values)
        self.record = None
        await self.send_history_update()

    async def replay_ui(self, record: ConversationRecord) -> None:
        self._is_replaying = True
        self._suppress_next_save = True
        try:
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
        finally:
            self._is_replaying = False

    # -- list mutations ----------------------------------------------------

    async def rename(self, conv_id: str, title: str) -> None:
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
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
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
        if self.minter is not None:
            target = (
                self.record
                if self.record is not None and self.record.id == conv_id
                else await self.store.get(self.scope, conv_id)
            )
            if target is not None and target.bookmark_state_id is not None:
                await self.minter.delete_state(target.bookmark_state_id)
        await self.store.delete(self.scope, conv_id)
        if self.record is not None and self.record.id == conv_id:
            self.record = None
            if self.minter is not None:
                await self.send_navigate(self.minter.base_url(), None)
                return
            self.adapter.set_turns_json([])
            await self.chat.clear_messages()
            self.ui_offset = 0
            await self._restore_app_state(self.baseline_values)
        await self.send_history_update()

    # -- protocol ----------------------------------------------------------

    async def send_navigate(self, url: str, active_id: str | None) -> None:
        action: HistoryNavigateAction = {
            "type": "history_navigate",
            "url": url,
            "active_id": active_id,
        }
        await self.chat._send_action(action)

    async def send_history_update(self) -> None:
        if self.scope is None:
            raise RuntimeError("HistoryController not initialized")
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


class ChatHistory:
    """Namespace for chat history configuration and lifecycle on a `Chat` instance."""

    def __init__(self, chat: "Chat", config: HistoryOptions | None = None) -> None:
        self._chat = chat
        self._started: bool = False
        self._save_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        self._restore_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        cfg = config if config is not None else HistoryOptions()
        self._store: "ConversationStore | Literal['auto', 'memory', 'file']" = cfg.store
        self._scope: "str | Callable[..., str] | None" = cfg.scope
        self._title: "TitleFn | Literal['fallback'] | None" = cfg.title
        self._restore_mode: "Literal['browser', 'url', 'none']" = cfg.restore_mode
        self._max_store_mb: float = cfg.max_store_mb

    def enable(self) -> None:
        """Enable chat history for the current session. No-op if already started."""
        if not self._started:
            self._start()

    def on_save(
        self, fn: "Callable[[dict[str, Any]], None]"
    ) -> "Callable[[dict[str, Any]], None]":
        """
        Decorator. Register a callback fired when a conversation is saved.

        The callback receives a mutable ``values`` dict; write any per-conversation
        app state you want to persist into it::

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
        if restore_mode == "url" and root_session.bookmark.store != "server":
            raise ValueError(
                'history restore_mode="url" requires server '
                "bookmarking: set `shiny.App(bookmark_store=\"server\")` "
                "(or `app_opts(bookmark_store=\"server\")` in Express)."
            )

        token_input_id = f"{chat.id}_history_browser_token"
        current_id_input_id = f"{chat.id}_history_current_id"
        root_session.bookmark.exclude.extend(
            [
                token_input_id,
                current_id_input_id,
                f"{chat.id}_history_select",
                f"{chat.id}_history_new",
                f"{chat.id}_history_rename",
                f"{chat.id}_history_delete",
            ]
        )

        adapter = as_turns_adapter(chat_client)
        resolved_store = resolve_store(self._store)
        title = self._title
        scope_key = self._scope
        max_store_bytes = int(self._max_store_mb * 1024 * 1024)
        controller = HistoryController(
            chat=chat,
            adapter=adapter,
            store=resolved_store,
            title_fn=title if callable(title) else None,
            title_enabled=title != "fallback",
            client=chat_client,
            save_callbacks=self._save_callbacks,
            restore_callbacks=self._restore_callbacks,
            max_store_bytes=max_store_bytes,
        )

        stamp_key = f"{chat.id}_history_conversation_id"
        stamp_cancel: Callable[[], None] | None = None
        if restore_mode == "url":
            controller.minter = BookmarkMinter(session)

            def stamp_conversation(state: Any) -> None:
                if controller.record is not None:
                    state.values[stamp_key] = controller.record.id

            stamp_cancel = root_session.bookmark.on_bookmark(stamp_conversation)

        @reactive.calc
        def scope() -> str:
            if isinstance(scope_key, str):
                return scope_key
            if callable(scope_key):
                return scope_key(chat._session)
            if chat._session.user is not None:
                return str(chat._session.user)
            token = chat._session.input[token_input_id]()
            return str(req(token))

        async def notify_error(prefix: str, e: Exception) -> None:
            from shiny import ui as shiny_ui

            with session_context(session):
                shiny_ui.notification_show(f"{prefix}: {e}", type="error")

        initialized = False

        @reactive.effect
        async def _init_history():
            nonlocal initialized
            if initialized:
                return

            current_id: str | None = None
            if restore_mode != "none":
                raw = chat._session.input[current_id_input_id]()
                current_id = str(raw) if raw else None

            controller.scope = scope()  # req() retries until token arrives
            initialized = True

            restore_ctx = root_session.bookmark._restore_context
            restored_conv_id: str | None = None
            if restore_ctx is not None and restore_ctx.active:
                raw_id = restore_ctx.values.get(stamp_key)
                restored_conv_id = str(raw_id) if raw_id else None

            target = None
            if restored_conv_id is not None:
                target = await controller.store.get(
                    controller.scope, restored_conv_id
                )
            if target is not None:
                adapter.set_turns_json(target.path_turns())
                await controller.replay_ui(target)
                controller.record = target
            elif restore_mode != "none":
                if current_id:
                    pointed = await controller.store.get(
                        controller.scope, current_id
                    )
                    if pointed is not None:
                        adapter.set_turns_json(pointed.path_turns())
                        await controller.replay_ui(pointed)
                        await controller._restore_app_state(pointed.values or {})
                        controller.record = pointed
            await controller.send_history_update()

        @reactive.effect
        @reactive.event(chat.messages, ignore_init=True)
        async def _save_on_response():
            if controller.scope is None:
                return
            messages = chat.messages()
            if messages and messages[-1].get("role") == "assistant":
                try:
                    await controller.on_response()
                except Exception as e:
                    await notify_error("Could not save conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[f"{chat.id}_history_select"])
        async def _on_select():
            if controller.scope is None:
                return
            payload = chat._session.input[f"{chat.id}_history_select"]()
            try:
                await controller.switch_to(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not open conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[f"{chat.id}_history_new"])
        async def _on_new():
            if controller.scope is None:
                return
            try:
                await controller.new_chat()
            except Exception as e:
                await notify_error("Could not start a new chat", e)

        @reactive.effect
        @reactive.event(chat._session.input[f"{chat.id}_history_rename"])
        async def _on_rename():
            if controller.scope is None:
                return
            payload = chat._session.input[f"{chat.id}_history_rename"]()
            try:
                await controller.rename(
                    str(payload["id"]), str(payload["title"])
                )
            except Exception as e:
                await notify_error("Could not rename conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[f"{chat.id}_history_delete"])
        async def _on_delete():
            if controller.scope is None:
                return
            payload = chat._session.input[f"{chat.id}_history_delete"]()
            try:
                await controller.delete(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not delete conversation", e)

        def _on_session_end() -> None:
            if stamp_cancel is not None:
                stamp_cancel()
            controller.cancel_pending()

        session.on_ended(_on_session_end)
        self._started = True
