from __future__ import annotations

import asyncio
import dataclasses
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Literal,
    cast,
)

from ._history_bookmark import delete_bookmark_state, extract_state_id
from ._history_client import as_turns_adapter
from ._history_controller import HistoryController
from ._history_store import (
    ConversationPartition,
    ConversationStore,
    resolve_store,
)
from ._history_title import TitleFn

# NB: shiny is imported lazily inside methods throughout this module; a
# top-level import would be circular (shiny.ui._chat imports shinychat).
from ._history_types import ConversationRecordV2

if TYPE_CHECKING:
    from htmltools import HTML, Tag, TagList
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
    message_resubmit: ResolvedId

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
            message_resubmit=RID(f"{chat_id}_message_resubmit"),
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
        in the Shiny app. On in-session conversation switches, the switch
        happens in place (no page reload) and the address bar soft-updates
        to the target conversation's ``?_state_id_=...`` URL if one exists.
        Use this mode when the app uses Shiny bookmarks to capture full
        input state alongside the chat.

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
    restore_bootstrap
        How a v2 exchange-tree restore initializes client turns.
        ``"recorded"`` reconstructs them entirely from saved state entries.
        ``"live"`` preserves the app's current turns and skips only the
        implicit root snapshot before applying later entries.
    """

    def __init__(
        self,
        restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = "browser",
        store: "ConversationStore | Literal['auto', 'memory', 'file']" = "auto",
        scope: "str | Callable[..., str] | None" = None,
        title: "TitleFn | Literal['auto'] | None" = "auto",
        max_store_mb: float | None = 100.0,
        restore_bootstrap: "Literal['recorded', 'live']" = "recorded",
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
        self.restore_bootstrap: "Literal['recorded', 'live']" = (
            restore_bootstrap
        )


def _history_transition_request_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    request_id = value.get("requestId")
    return request_id if isinstance(request_id, str) else None


async def _complete_history_transition(chat: "Chat", request_id: str) -> None:
    try:
        await chat._send_action(
            {
                "type": "history_transition_complete",
                "requestId": request_id,
            }
        )
    except (asyncio.CancelledError, Exception):
        # Completion is advisory and must not alter the transition outcome.
        pass


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
        self._restore_bootstrap: "Literal['recorded', 'live']" = (
            cfg.restore_bootstrap
        )
        self._initial_history_initialized = False

    def enable(self) -> None:
        """Enable chat history for the current session. No-op if already started."""
        if not self._started:
            self._start()

    def _history_action_admitted(self) -> bool:
        controller = self._controller
        return (
            controller is None
            or self._initial_history_initialized
        )

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
        if on_end is not None:
            on_end()
        self._on_session_end = None

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
            restore_bootstrap=self._restore_bootstrap,
        )
        self._controller = controller

        recorder = controller._exchange_recorder
        chat._transcript.set_capture_callbacks(
            on_accepted_input=recorder.accepted_input,
            on_message_committed=recorder.message_committed,
            on_stream_started=recorder.stream_started,
            on_stream_updated=recorder.stream_updated,
            on_stream_finished=recorder.stream_finished,
        )

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

            async def _on_response_saved(
                record: ConversationRecordV2,
            ) -> None:
                recorder = controller._exchange_recorder
                pointer = await recorder.bookmark_pointer(
                    cast(ConversationRecordV2, record)
                )
                if pointer is None:
                    return
                conversation_id, node_id = pointer

                async def _on_bookmarked(url: str) -> None:
                    new_state_id = extract_state_id(url)
                    if new_state_id is None:
                        return
                    try:
                        current, cleanup_state_id = (
                            await recorder.settle_bookmark_state_id(
                                conversation_id, node_id, new_state_id
                            )
                        )
                    except BaseException:
                        await delete_bookmark_state(new_state_id)
                        raise
                    if cleanup_state_id is not None:
                        await delete_bookmark_state(cleanup_state_id)
                    if current:
                        await controller.send_navigate(
                            f"?_state_id_={new_state_id}", conversation_id
                        )

                await do_bookmark_with_cleanup(
                    root_session.bookmark, _on_bookmarked
                )

            controller.on_response_saved = _on_response_saved

            # D5: after a v2 in-place switch restores, point the URL at the
            # restored conversation's bookmark state id via the existing
            # history_navigate action WITHOUT reload (a soft replaceState,
            # like the post-response-save mint). No state id (the target
            # never had a response saved) -> url=None clears the stale query.
            # Uses replaceState, never pushState (pushState would mutate
            # server-side clientdata mid-session).
            async def _on_switch_restored(record: ConversationRecordV2) -> None:
                state_id = record.bookmark_state_id
                url = f"?_state_id_={state_id}" if state_id is not None else None
                await controller.send_navigate(url, record.id)

            controller.on_switch_restored = _on_switch_restored

            async def _on_evict(conv_id: str) -> None:
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

        stamp_key = f"{chat.id}_history_exchange_pointer"
        # Legacy v1 bookmark stamp: a v1 server stamped only the conversation
        # id here. When the v2 pointer above is absent, restoring a bookmark
        # written by a v1 server reads this key instead. Nothing writes it
        # anymore — the v1 write site died with the v1 runtime — but the
        # read-gate below must stay as long as v1-written bookmarks exist in
        # the wild.
        legacy_stamp_key = f"{chat.id}_history_conversation_id"
        stamp_cancel: Callable[[], None] | None = None
        if root_session.bookmark.store == "server":
            recorder = controller._exchange_recorder

            async def stamp_exchange_pointer(state: Any) -> None:
                pointer = await recorder.bookmark_pointer()
                if pointer is None:
                    return
                conversation_id, node_id = pointer
                state.values[stamp_key] = {
                    "conversation_id": conversation_id,
                    "node_id": node_id,
                }

            stamp_cancel = root_session.bookmark.on_bookmark(
                stamp_exchange_pointer
            )

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

        async def _run_history_transition(
            input_id: ResolvedId,
            error_prefix: str,
            action: Callable[[Any, str | None], Awaitable[None]],
            *,
            require_admission: bool = True,
        ) -> None:
            """The one skeleton shared by the transition input effects.

            A request landing before the initial history decision would
            race the pending restore (and publish a history_update that
            releases client-side admission early), so unadmitted requests
            are dropped; delete is the one effect that skips the gate.
            `action` owns the per-effect payload validation and controller
            call.
            """
            payload = chat._session.input[input_id]()
            request_id = _history_transition_request_id(payload)
            try:
                if require_admission and not self._history_action_admitted():
                    return
                if controller.partition is None:
                    return
                await action(payload, request_id)
            except Exception as e:
                await notify_error(error_prefix, e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        async def finish_initial(restored: bool) -> None:
            self._initial_history_initialized = True
            await controller.notify_settled(restored)

        @reactive.effect(priority=10_000)
        async def _init_history():
            if self._initial_history_initialized:
                return

            async def restore_initial_v2(
                target: ConversationRecordV2,
                *,
                node_id: str | None = None,
            ) -> None:
                try:
                    await controller._restore_initial_exchange_record(
                        target, node_id=node_id
                    )
                except BaseException:
                    try:
                        await controller.notify_settled(False)
                    except BaseException:
                        pass
                    raise

            owner_scope = scope()
            controller.partition = ConversationPartition(
                chat_id=str(chat.id), scope=owner_scope
            )

            restore_ctx = root_session.bookmark._restore_context
            # node_id is None only for a legacy v1 stamp (conversation id
            # without a leaf); the open block resolves it to the record's
            # active leaf after fetching the record.
            bookmark_pointer: tuple[str, str | None] | None = None
            bookmark_pointer_invalid = False
            if restore_ctx is not None and restore_ctx.active:
                raw_pointer = restore_ctx.values.get(stamp_key)
                if raw_pointer is not None:
                    if (
                        isinstance(raw_pointer, dict)
                        and set(raw_pointer) == {"conversation_id", "node_id"}
                        and isinstance(raw_pointer["conversation_id"], str)
                        and raw_pointer["conversation_id"]
                        and isinstance(raw_pointer["node_id"], str)
                        and raw_pointer["node_id"]
                    ):
                        bookmark_pointer = (
                            raw_pointer["conversation_id"],
                            raw_pointer["node_id"],
                        )
                    else:
                        bookmark_pointer_invalid = True
                else:
                    # A bookmark written by a v1 server carries only the
                    # legacy conversation stamp. Fall back to it and open
                    # that conversation at its active leaf. The v2 pointer
                    # above keeps precedence when both keys exist; a
                    # present-but-invalid v2 pointer still fails loudly
                    # below rather than silently falling back.
                    legacy_id = restore_ctx.values.get(legacy_stamp_key)
                    if legacy_id is not None:
                        if isinstance(legacy_id, str) and legacy_id:
                            bookmark_pointer = (legacy_id, None)
                        else:
                            bookmark_pointer_invalid = True

            if bookmark_pointer_invalid:
                await notify_error(
                    "Could not load conversation",
                    ValueError("Bookmark pointer is invalid."),
                )
                await controller.send_history_update()
                await finish_initial(False)
                return

            if bookmark_pointer is not None:
                conversation_id, node_id = bookmark_pointer
                try:
                    target = await controller._get_record(
                        controller.partition, conversation_id
                    )
                    if target is None:
                        raise ValueError("Bookmark conversation is unavailable.")
                    if node_id is None:
                        # Legacy v1 stamp: no node was stored. Synthesize the
                        # pointer with the record's active leaf so the restore
                        # runs through the exact same open path as a v2
                        # pointer. A v1 record upgrades on read — never a
                        # silent no-restore.
                        node_id = target.active_leaf
                    if node_id not in target.nodes:
                        raise ValueError("Bookmark node is unavailable.")
                except Exception as e:
                    await notify_error(
                        f"Could not load conversation {conversation_id!r}", e
                    )
                    await controller.send_history_update()
                    await finish_initial(False)
                    return

                await restore_initial_v2(target, node_id=node_id)
                await finish_initial(True)
                return

            # Reading these inputs may raise SilentException if the browser
            # hasn't sent them yet (they're delivered after Shiny's
            # initializedPromise resolves, which is after the first flush).
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
                    await restore_initial_v2(pointed)
                    await finish_initial(True)
                    return
            await controller.send_history_update()
            await finish_initial(
                controller._active_id_now() is not None
            )

        async def _save_on_response():
            if controller.partition is None:
                return
            try:
                await controller.on_response()
            except Exception as e:
                await notify_error("Could not save conversation", e)

        cancel_response_settlement = chat._on_response_settled(
            _save_on_response
        )

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

        async def _apply_new(payload: Any, request_id: str | None) -> None:
            await controller.new_chat()

        @reactive.effect
        @reactive.event(chat._session.input[ids.new])
        async def _on_new():
            await _run_history_transition(
                ids.new,
                "Could not start a new chat",
                _apply_new,
            )

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

        async def _apply_delete(payload: Any, request_id: str | None) -> None:
            await controller.delete(str(payload["id"]))

        @reactive.effect
        @reactive.event(chat._session.input[ids.delete])
        async def _on_delete():
            await _run_history_transition(
                ids.delete,
                "Could not delete conversation",
                _apply_delete,
                require_admission=False,
            )

        async def _apply_edit(payload: Any, request_id: str | None) -> None:
            if not isinstance(payload, dict):
                raise TypeError("Edited message payload must be an object.")
            index = payload.get("index")
            content = payload.get("content")
            if not isinstance(index, int):
                raise TypeError("Edited message index must be an integer.")
            if not isinstance(content, str):
                raise TypeError("Edited message content must be a string.")
            await controller.handle_edit(
                index,
                content,
                payload.get("attachments"),
                request_id=request_id,
            )

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_edit])
        async def _on_edit():
            await _run_history_transition(
                ids.message_edit,
                "Could not edit message",
                _apply_edit,
            )

        async def _apply_navigate(payload: Any, request_id: str | None) -> None:
            if not isinstance(payload, dict):
                raise TypeError("Navigation payload must be an object.")
            index = payload.get("index")
            direction = payload.get("direction")
            if not isinstance(index, int):
                raise TypeError("Navigation index must be an integer.")
            if not isinstance(direction, str):
                raise TypeError("Navigation direction must be a string.")
            await controller.handle_navigate(
                index,
                direction,
                request_id=request_id,
            )

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_navigate])
        async def _on_navigate():
            await _run_history_transition(
                ids.message_navigate,
                "Could not navigate messages",
                _apply_navigate,
            )

        async def _apply_resubmit(payload: Any, request_id: str | None) -> None:
            if not isinstance(payload, dict):
                raise TypeError("Resubmit payload must be an object.")
            index = payload.get("index")
            kind = payload.get("kind")
            if not isinstance(index, int):
                raise TypeError("Resubmit message index must be an integer.")
            if not isinstance(kind, str):
                raise TypeError("Resubmit kind must be a string.")
            await controller.handle_resubmit(
                index, kind, request_id=request_id
            )

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_resubmit])
        async def _on_resubmit():
            await _run_history_transition(
                ids.message_resubmit,
                "Could not retry message",
                _apply_resubmit,
            )

        def _on_session_end() -> None:
            if self._on_session_end is None:
                return
            self._session_end_cancel = None
            self._on_session_end = None
            if stamp_cancel is not None:
                stamp_cancel()
            cancel_response_settlement()
            controller.cancel_pending()

        self._effects.extend(
            [
                _init_history,
                _on_select,
                _on_new,
                _on_rename,
                _on_delete,
                _on_edit,
                _on_navigate,
                _on_resubmit,
            ]
        )
        self._on_session_end = _on_session_end
        self._session_end_cancel = session.on_ended(_on_session_end)
        self._started = True
