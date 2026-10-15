from __future__ import annotations

import asyncio
import dataclasses
import inspect
import warnings
from contextlib import asynccontextmanager, contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Iterator,
    Literal,
    cast,
)

from . import _history_plan
from ._attachments import (
    Attachment,
    validate_attachments,
)
from ._chat_types import (
    ExchangeMetadata,
    HistoryAcceptedInputProjectionAction,
    HistoryEditProjectionAction,
    HistoryNavigateAction,
    HistoryUpdateAction,
    StoredMessage,
    StoredSegment,
    UpdateExchangeMetadataAction,
    UpdateSiblingsAction,
)
from ._history_bookmark import delete_bookmark_state, extract_state_id
from ._history_client import (
    TurnsAdapter,
    as_turns_adapter,
)
from ._history_plan import (
    RestorePlan,
    StatePlan,
)
from ._history_recorder import _ExchangeRecorder
from ._history_store import (
    ConversationPartition,
    ConversationStore,
    resolve_store,
)
from ._history_title import (
    MAX_TITLE_LEN,
    TitleFn,
    generate_title,
)

# NB: shiny is imported lazily inside methods throughout this module; a
# top-level import would be circular (shiny.ui._chat imports shinychat).
from ._history_types import (
    ConversationRecordV1,
    ConversationRecordV2,
    ExchangeNode,
    TurnDict,
    check_schema_version,
    new_conversation_id,
    project_history_error_message,
)
from ._history_v1 import import_v1_record_with_warnings

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


# Exchange statuses from which a retry (or a fresh resubmit) is allowed.
_RETRYABLE_STATUSES = ("pending", "error", "cancelled")


def _attachment_projection(
    attachments: list[Attachment],
) -> list[dict[str, Any]]:
    """The wire shape for attachments on resubmit projection actions."""
    return [
        {
            "mime": attachment.mime,
            "data_url": attachment.data_url,
            "name": attachment.name,
            "size": attachment.size,
        }
        for attachment in attachments
    ]


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


# The in-flight restore step travels on the exception itself (PEP 678
# notes) rather than a controller slot, so the mechanism is stateless: no
# label needs resetting after recovery, and an already-labeled exception
# is never relabeled, which makes the innermost failing step win.
_RESTORE_STEP_NOTE_PREFIX = "shinychat restore step: "


def _add_exception_note(error: BaseException, note: str) -> None:
    """`BaseException.add_note` that also works on Python 3.10.

    CI's floor is 3.10 and `add_note` arrived in 3.11; the fallback writes
    `__notes__` directly with the same shape `add_note` would produce.
    """
    add_note = getattr(error, "add_note", None)
    if add_note is not None:
        add_note(note)
        return
    notes: list[Any] = list(getattr(error, "__notes__", None) or ())
    notes.append(note)
    setattr(error, "__notes__", notes)


def _restore_step_label(error: BaseException) -> str | None:
    """The restore-step note carried by `error`, if any."""
    notes: Any = getattr(error, "__notes__", None)
    if notes is None:
        return None
    for note in notes:
        if isinstance(note, str) and note.startswith(
            _RESTORE_STEP_NOTE_PREFIX
        ):
            return note[len(_RESTORE_STEP_NOTE_PREFIX) :]
    return None


def _restore_failure_detail(failure: BaseException | None) -> str | None:
    """Name the failing hook or step for the restore-failure notification.

    The returned detail is safe for end users: it names the failing
    state entry (``StateHookError`` names its hook) or the labeled
    in-flight step, and never carries raw exception text, which can
    hold internal details from app hooks or the store.
    Cancellation keeps the generic message: its identity is the
    outcome, not a diagnostic.
    """
    if not isinstance(failure, Exception):
        return None
    if isinstance(failure, _history_plan.StateHookError):
        return f"the {failure.entry_name!r} state entry failed to apply"
    step = _restore_step_label(failure)
    if step is not None:
        return f"failed while {step}"
    return None


@contextmanager
def _restore_step(step: str) -> Iterator[None]:
    """Label the in-flight restore step on the failure for the detail.

    The step is remembered only when the wrapped block fails, so a later
    ``_clear_failed_restore`` can name where the restore broke; successful
    steps leave nothing behind. Cancellation and other non-``Exception``
    failures stay unlabeled, matching ``_history_plan.run_plan``.
    """
    try:
        yield
    except Exception as error:
        if _restore_step_label(error) is None:
            _add_exception_note(
                error, f"{_RESTORE_STEP_NOTE_PREFIX}{step}"
            )
        raise


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
        restore_bootstrap: Literal["recorded", "live"] = "recorded",
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

        # Conversation ids whose lossy v1-import warnings already surfaced
        # this session; the read-gate warns once per session per conversation.
        self._lossy_import_warned: set[str] = set()
        self.partition: ConversationPartition | None = None
        # Active conversation identity: an identified draft (submitted but
        # not yet saved) has an ID and no record. All identity mutations go
        # through clear_active()
        # and _set_active_id() so that the active ID never moves
        # independently of the recorder's record.
        from shiny import reactive

        self._active_id: "reactive.Value[str | None]" = reactive.Value(None)
        # Set by enable() when restore_mode="url"; called with the new
        # conversation id (or None) after any switch that changes the active
        # conversation.
        self.on_active_id_change: (
            Callable[[str | None], Awaitable[None]] | None
        ) = None
        # Internal hook: fired after every save. bookmark mode uses it to mint.
        # Receives the v2 record the exchange recorder owns.
        self.on_response_saved: (
            Callable[[ConversationRecordV2], Awaitable[None]] | None
        ) = None
        # Internal hook: fired after a v2 in-place switch_to restore
        # succeeds. Bookmark mode uses it to point the URL at the restored
        # conversation's bookmark state id without a reload (a soft
        # replaceState, the same mechanism the post-response-save mint
        # uses); a failed or blocked switch never fires it, so the URL
        # keeps matching the still-active conversation.
        self.on_switch_restored: (
            Callable[[ConversationRecordV2], Awaitable[None]] | None
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
        self.restore_bootstrap: Literal["recorded", "live"] = restore_bootstrap
        self._title_task: asyncio.Task[None] | None = None
        self._over_budget_warned: bool = False
        self._exchange_recorder = _ExchangeRecorder(self)

    # -- active conversation identity --------------------------------------

    def conversation_id(self) -> str | None:
        """
        Reactive read of the active conversation ID: ``None`` for an empty
        draft, otherwise the ID the eventual conversation record will (or
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

    def _allocate_conversation_id(self) -> str:
        id = self._active_id_now()
        if id is None:
            id = new_conversation_id()
            self._active_id.set(id)
        return id

    async def ensure_conversation_id(self) -> str:
        """
        Return the active conversation ID, allocating one when the active
        conversation is an empty draft. Repeated calls for the same active
        conversation return the same ID.
        """
        id = self._active_id_now()
        if id is None:
            id = self._allocate_conversation_id()
        return id

    async def clear_active(self) -> None:
        if self._active_id_now() is not None:
            self._active_id.set(None)

    async def _set_active_id(self, id: str | None) -> None:
        # Single writer for the active ID; notifies on_active_id_change only
        # on an actual change (e.g. first save after ensure_conversation_id()
        # does not re-fire).
        if self._active_id_now() == id:
            return
        self._active_id.set(id)
        if self.on_active_id_change is not None:
            await self.on_active_id_change(id)

    async def _publish_active_v2_id(self, record: ConversationRecordV2) -> bool:
        if self._active_id_now() != record.id:
            return False
        if self.on_active_id_change is not None:
            await self.on_active_id_change(record.id)
        recorder = self._exchange_recorder
        return recorder.record is record and self._active_id_now() == record.id

    async def _get_record(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV2 | None:
        record = await self.store.get(partition, conv_id)
        if record is not None:
            check_schema_version(record.schema_version)
            if isinstance(record, ConversationRecordV1):
                # Lazy-conversion read-gate: a v1 record -- read from disk by
                # a built-in store or handed back by a custom store --
                # upgrades to v2 in memory here, and is written back as v2 on
                # its next save. Genuinely lossy upgrade steps surface as
                # warnings once per session per conversation; re-reads
                # re-import quietly. (Python's default warning filter also
                # coalesces an identical repeat process-wide, so a second
                # session in the same process may not re-see a warning a
                # previous session already emitted.)
                record, warns = import_v1_record_with_warnings(record)
                if warns and record.id not in self._lossy_import_warned:
                    self._lossy_import_warned.add(record.id)
                    for warning in warns:
                        warnings.warn(warning)
            if not isinstance(record, ConversationRecordV2):
                raise ValueError(
                    "Conversation record schema does not match the active history path."
                )
        return record

    @asynccontextmanager
    async def _destructive_mutation(self, *, block_input: bool = False):
        if block_input:
            async with self.chat._destructive_history_mutation(
                block_input=True
            ):
                yield
            return
        async with self.chat._destructive_history_mutation():
            yield

    @asynccontextmanager
    async def _exchange_mutation(self):
        async with self._exchange_recorder.lock:
            yield

    # -- save -----------------------------------------------------------

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response.

        A private response lifecycle callback is the only automatic caller.
        It fires after a completed assistant append or a stream terminal
        outcome, so replay, clear, accepted input, and partial chunks do not
        settle history.

        Safe without additional locking (P5.6.8 audit, superseding the stale
        process-wide ``reactive.lock()`` argument): every recorder mutation
        takes the recorder's ``asyncio.Lock``; the response-settlement pump
        is single-flight (one runner task, FIFO); and
        ``ChatTranscript.end_stream`` awaits the capture callbacks before
        scheduling settlement, so a settlement always observes a finished
        exchange. These properties hold under both py-shiny's sequential
        flush and the proposed concurrent-effects model.
        """
        recorder = self._exchange_recorder
        if not await recorder.response_settled():
            return
        record = recorder.record
        assert record is not None
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(record)
        await self.send_history_update()
        await self._send_sibling_metadata()
        self._schedule_exchange_retitle(record)

    def _schedule_exchange_retitle(self, record: ConversationRecordV2) -> None:
        """Launch the v2 retitle task (phase-5.7 D8: `tgdt`).

        v1 waits for the second settled response (``response_count == 2``).
        The tree-aware equivalent counts exchanges carrying an ``input`` on
        the active path, so navigation/resubmit siblings don't inflate the
        count the way a session counter would; the task fires when that
        count reaches 2, giving the LLM/custom ``title_fn`` the same
        two-exchange context as v1 and skipping conversations abandoned
        after one message. As on v1, the retitle is skipped when titling
        is disabled (``title_enabled`` False) or the title is already set
        (``title_source`` non-None: a user rename or an earlier title).
        """
        input_exchanges = sum(
            1
            for node_id in record.path_node_ids()
            if record.nodes[node_id].input is not None
        )
        if (
            not self.title_enabled
            or record.title_source is not None
            or input_exchanges != 2
        ):
            return
        turns_flat = self.adapter.get_turns_json()
        self._title_task = asyncio.create_task(
            self.retitle_v2(turns_flat, record)
        )
        self._title_task.add_done_callback(title_task_done)

    async def retitle_v2(
        self, turns: list[TurnDict], target: ConversationRecordV2
    ) -> None:
        """The v2 counterpart of :meth:`retitle` (phase-5.7 D8: `tgdt`).

        Same shape as the scheduling path: the caller passes the settled record
        to title, so the slow LLM call targets the conversation that was
        eligible when scheduling happened; bail when the conversation switched
        away or the user renamed mid-call, then write the new title through the
        recorder's normal v2 persist path (store put under the recorder
        lock) and publish it via ``history_update``.
        """
        recorder = self._exchange_recorder
        if recorder.record is not target:
            return  # the active conversation switched away before we started
        if target.title_source == "user":
            return
        title = await generate_title(self.title_fn, self.client, turns)
        if (
            title is None
            or recorder.record is not target
            or target.title_source == "user"
        ):
            return  # conversation switched away or user renamed mid-call
        async with self._exchange_mutation():
            # Re-checked under the recorder lock, inside the recorder: the
            # active record or its title may have changed while the LLM
            # call was in flight.
            if not await recorder.retitle_active_locked(target, title):
                return
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
        active_record = self._exchange_recorder.record
        metas = await self.store.list(self.partition)
        total = sum(m.size_bytes for m in metas)
        if total <= self.max_store_bytes:
            return
        for meta in reversed(metas):  # oldest first
            if active_record is not None and meta.id == active_record.id:
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
        record = self._exchange_recorder.record
        assert record is not None
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(record)
        await self.send_history_update()
        await self._send_sibling_metadata()
        return True

    async def save_current(self) -> bool:
        """Persist the active conversation if it has ever been saved."""
        return await self._exchange_recorder.save_current()

    def _restore_app_state(self, values: dict[str, Any]) -> None:
        for cb in self._restore_callbacks:
            cb(values)

    async def _notify_restore_failure(
        self, *, recovery_incomplete: bool, detail: str | None = None
    ) -> None:
        from shiny import ui as shiny_ui
        from shiny.session import session_context

        message = "Could not restore conversation."
        if detail:
            # `detail` names the failing hook (state entry) or restore step;
            # it carries no trailing period so the sentence composes.
            message = f"Could not restore conversation: {detail.rstrip('.')}."
        message += (
            " Recovery was incomplete; reload before starting a new chat."
            if recovery_incomplete
            else " A fresh chat is ready."
        )
        with session_context(self.chat._session):
            shiny_ui.notification_show(
                message,
                type="error",
            )

    async def _notify_turns_unavailable(self) -> None:
        from shiny import ui as shiny_ui
        from shiny.session import session_context

        with session_context(self.chat._session):
            shiny_ui.notification_show(
                "Conversation display was restored, but model context was unavailable.",
                type="warning",
            )

    async def _clear_failed_restore(
        self, failure: BaseException | None = None
    ) -> None:
        recorder = self._exchange_recorder

        detail = _restore_failure_detail(failure)
        if isinstance(failure, Exception):
            # The user-facing notification carries only the safe detail;
            # developers get the full error, including any raw exception
            # text from app hooks or the store.
            warnings.warn(
                f"Chat history restore failed ({detail or 'no detail'}): "
                f"{failure!r}",
                stacklevel=2,
            )

        # Local ownership is cleared synchronously before any cleanup can
        # suspend, so a subsequent accepted input always creates a fresh draft.
        recorder.reset()
        self._active_id.set(None)

        cleanup_failures: list[BaseException] = []
        async def best_effort(operation: Callable[[], Any]) -> None:
            try:
                result = operation()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                cleanup_failures.append(error)

        await best_effort(self.chat.clear_messages)
        await best_effort(lambda: self.adapter.set_turns_json([]))
        await best_effort(lambda: self.chat.set_greeting(None))
        active_id_callback = self.on_active_id_change
        if active_id_callback is not None:
            await best_effort(lambda: active_id_callback(None))
        try:
            await self.send_history_update()
        except BaseException as error:
            cleanup_failures.append(error)
        else:
            history = getattr(self.chat, "history", None)
            if (
                history is not None
                and not history._initial_history_initialized
            ):
                history._initial_history_initialized = True
        try:
            await self._notify_restore_failure(
                recovery_incomplete=bool(cleanup_failures), detail=detail
            )
        except BaseException:
            # The original restore error or cancellation remains the outcome.
            pass

    async def replay_exchange_record(
        self, record: ConversationRecordV2 | None = None
    ) -> None:
        target = self._exchange_recorder.record if record is None else record
        if target is not None:
            await self._restore_exchange_record(target)

    def _prepare_exchange_restore(
        self,
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> tuple[tuple[str, ...], RestorePlan, Literal["recorded", "live"]]:
        recorder = self._exchange_recorder

        # Validate the entire path before this transaction clears the current
        # display or mutates the attached client.
        node_ids = tuple(target.path_node_ids())
        if not node_ids or target.active_leaf is None:
            raise ValueError("Exchange-tree record has no active path.")
        selected_bootstrap = (
            self.restore_bootstrap if bootstrap is None else bootstrap
        )
        planned_state = _history_plan.preflight_state(
            target,
            node_ids,
            recorder.restore_hooks,
            adapter=self.adapter,
            bootstrap=selected_bootstrap,
        )
        return node_ids, planned_state, selected_bootstrap

    async def _restore_exchange_record_locked(
        self,
        target: ConversationRecordV2,
        *,
        node_ids: tuple[str, ...],
        planned_state: RestorePlan,
        bootstrap: Literal["recorded", "live"],
        persist_active_pointer: bool = False,
    ) -> None:
        recorder = self._exchange_recorder

        try:
            # Live bootstrap is intentionally captured only after admission
            # and recorder serialization, but before destructive effects.
            with _restore_step("materializing the restored turns"):
                if bootstrap == "live":
                    planned_state = (
                        _history_plan.materialize_live_restore_turns(
                            planned_state, adapter=self.adapter
                        )
                    )
            with _restore_step("replaying the conversation display"):
                await self._replay_exchange_display(target, node_ids)
            with _restore_step("applying the recorded state entries"):
                await _history_plan.run_plan(planned_state)
            if _history_plan.turns_unavailable(planned_state):
                recorder.invalidate_turn_baseline()

            # `_ExchangeRecorder` remains the sole v2 record owner.
            # The controller only sequences its installation after
            # display and state consumers have accepted the target.
            with _restore_step("installing the restored record"):
                recorder.install_restored_record(target)
                await self._set_active_id(target.id)
                recorder.mark_active_id_published(target)
            with _restore_step("persisting the restored record"):
                if persist_active_pointer:
                    await recorder.persist_record_locked()
            with _restore_step("restoring the app state"):
                self._restore_app_state(target.values or {})
            with _restore_step(
                "sending the restored conversation metadata"
            ):
                await self._send_exchange_metadata()
                await self._send_sibling_metadata()
                if _history_plan.turns_unavailable(planned_state):
                    await self._notify_turns_unavailable()
                await self.send_history_update()
        except BaseException as error:
            await self._clear_failed_restore(error)
            raise

    async def _replay_exchange_display(
        self, record: ConversationRecordV2, node_ids: tuple[str, ...]
    ) -> None:
        recorder = self._exchange_recorder

        await self.chat.clear_messages()
        await self.chat.set_greeting(None)
        with recorder.suspend_capture():
            for node_id in node_ids:
                node = record.nodes[node_id]
                if node.input is not None:
                    await self.chat._restore_bookmark_message(
                        node.input.model_dump(mode="json")
                    )
                for message in node.messages:
                    await self.chat._restore_bookmark_message(
                        message.as_stored_message().model_dump(mode="json"),
                        icon=message.icon,
                    )

    async def _restore_exchange_record(
        self,
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> None:
        node_ids, planned_state, selected_bootstrap = (
            self._prepare_exchange_restore(target, bootstrap=bootstrap)
        )

        async with self._destructive_mutation():
            async with self._exchange_mutation():
                await self._restore_exchange_record_locked(
                    target,
                    node_ids=node_ids,
                    planned_state=planned_state,
                    bootstrap=selected_bootstrap,
                )

    async def _restore_initial_exchange_record(
        self,
        target: ConversationRecordV2,
        *,
        node_id: str | None = None,
    ) -> None:
        """Restore an initial target, recovering only preflight failures."""
        selected = target
        persist_active_pointer = False
        try:
            with _restore_step("validating the saved conversation"):
                if node_id is not None:
                    selected = target.model_copy(deep=True)
                    selected.set_active_leaf(node_id)
                    persist_active_pointer = target.active_leaf != node_id
                node_ids, planned_state, bootstrap = (
                    self._prepare_exchange_restore(selected)
                )
        except BaseException as error:
            # Initial restore has no surrounding transaction to recover a
            # failed preflight. Keep the shared restore methods fail-closed.
            await self._clear_failed_restore(error)
            raise

        restore_body_entered = False
        try:
            with _restore_step("admitting the restored conversation"):
                async with self._destructive_mutation():
                    async with self._exchange_mutation():
                        restore_body_entered = True
                        await self._restore_exchange_record_locked(
                            selected,
                            node_ids=node_ids,
                            planned_state=planned_state,
                            bootstrap=bootstrap,
                            persist_active_pointer=persist_active_pointer,
                        )
        except BaseException as error:
            if not restore_body_entered:
                await self._clear_failed_restore(error)
            # Otherwise the restore body already ran its own attribution
            # and cleanup; its failure propagates unchanged, and the
            # step note on the exception can't leak into a later one.
            raise

    async def restore_bookmark_pointer(
        self, target: ConversationRecordV2, node_id: str
    ) -> None:
        """Restore a validated v2 bookmark node through the normal transaction."""
        selected = target.model_copy(deep=True)
        selected.set_active_leaf(node_id)
        node_ids, planned_state, bootstrap = self._prepare_exchange_restore(selected)
        persist_active_pointer = target.active_leaf != node_id

        async with self._destructive_mutation():
            async with self._exchange_mutation():
                await self._restore_exchange_record_locked(
                    selected,
                    node_ids=node_ids,
                    planned_state=planned_state,
                    bootstrap=bootstrap,
                    persist_active_pointer=persist_active_pointer,
                )

    # -- switch / new ----------------------------------------------------

    async def switch_to(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        if self._active_id_now() == conv_id:
            return
        # Load BEFORE mutating anything: a failed load must leave the
        # current conversation untouched.
        target = await self._get_record(self.partition, conv_id)
        if target is None:
            raise RuntimeError(f"Conversation {conv_id!r} no longer exists.")
        from shiny import reactive

        with reactive.isolate():
            stream_is_running = (
                self.chat.latest_message_stream.status() == "running"
            )
        if stream_is_running:
            raise RuntimeError(
                "Cannot switch conversations while a message stream is active."
            )
        recorder = self._exchange_recorder
        async with self._destructive_mutation(block_input=True):
            async with self._exchange_mutation():
                await recorder.save_current_locked()
                target = await self._get_record(self.partition, conv_id)
                if target is None:
                    raise RuntimeError(
                        f"Conversation {conv_id!r} no longer exists."
                    )
                node_ids, planned_state, bootstrap = (
                    self._prepare_exchange_restore(target)
                )
                await self._restore_exchange_record_locked(
                    target,
                    node_ids=node_ids,
                    planned_state=planned_state,
                    bootstrap=bootstrap,
                )
        # Only after a successful restore: bookmark mode points the URL
        # at the restored conversation's state id (or clears a stale
        # query) without a reload. A failed or blocked switch raises
        # above, leaving the URL matching the still-active conversation.
        if self.on_switch_restored is not None:
            try:
                await self.on_switch_restored(target)
            except Exception as exc:
                # The restore already committed; a best-effort URL update
                # failure (e.g. session closing) must not make callers
                # treat the succeeded switch as failed.
                warnings.warn(
                    f"on_switch_restored hook failed: {exc}", stacklevel=1
                )

    async def new_chat(self, *, greeting: bool = False) -> None:
        """
        Start a new conversation.

        The current conversation is saved before the client turns, rendered
        messages, active ID, and history drawer state are reset. ``greeting``
        is forwarded to :meth:`Chat.clear_messages`; when ``True``, the
        greeting is cleared and the configured greeting is resolved again
        after the new-chat transition settles.
        """
        async with self._destructive_mutation():
            async with self._exchange_mutation():
                await self._exchange_recorder.save_current_locked()
                self.adapter.set_turns_json([])
                await self.chat.clear_messages(greeting=greeting)
                # Announce the cleared state even when the active ID is already None:
                # in URL/bookmark restore modes the browser may still carry a stale
                # conversation param (e.g. after a failed restore) that only
                # on_active_id_change(None) clears.
                self._exchange_recorder.reset()
                await self.clear_active()
                if self.on_active_id_change is not None:
                    await self.on_active_id_change(None)
                # A fresh chat is never a restore: resolve the greeting the same way
                # the initial settle does, so it doesn't just rely on a stale/absent
                # cached value from that first resolution.
                await self.notify_settled(False)
                await self.send_history_update()

    @staticmethod
    def _validate_resubmit_target(
        record: ConversationRecordV2, exchange_id: str, kind: str
    ) -> tuple[ExchangeNode, str]:
        """The validated resubmit target and its parent prefix id."""
        target = record.nodes.get(exchange_id)
        if target is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        if target.input is None:
            raise ValueError(
                f"Exchange {exchange_id!r} has no user input to resubmit."
            )
        if exchange_id not in record.path_node_ids():
            raise ValueError(
                f"Exchange {exchange_id!r} is not on the active path."
            )
        if target.parent_id is None:
            raise ValueError(
                f"Exchange {exchange_id!r} has no parent prefix to resubmit."
            )
        if kind == "retry":
            if target.status not in _RETRYABLE_STATUSES:
                raise ValueError(
                    "Only interrupted or failed exchanges can be retried."
                )
        elif kind == "regenerate":
            if target.status != "ok":
                raise ValueError(
                    "Only completed exchanges can be regenerated."
                )
        elif kind != "edit":
            raise ValueError(f"Unknown exchange resubmit kind {kind!r}.")
        return target, target.parent_id

    @staticmethod
    def _normalize_resubmit_input(message: StoredMessage) -> StoredMessage:
        if message.role != "user":
            raise ValueError("Only user inputs can be resubmitted.")
        normalized = message.model_copy(deep=True)
        validate_attachments(normalized.attachments)
        return normalized

    @staticmethod
    def _replacement_resubmit_input(
        content: str,
        attachments: list[dict[str, Any]] | None,
    ) -> StoredMessage:
        if not isinstance(content, str):
            raise TypeError("Edited message content must be a string.")
        parsed = (
            [Attachment.model_validate(attachment) for attachment in attachments]
            if attachments is not None
            else []
        )
        validate_attachments(parsed)
        return StoredMessage(
            role="user",
            segments=[StoredSegment(content=content, content_type="markdown")],
            attachments=parsed,
        )

    async def resubmit(
        self,
        exchange_id: str,
        replacement_input: StoredMessage | None = None,
        *,
        kind: str,
        request_id: str,
        message_index: int,
    ) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        recorder = self._exchange_recorder
        record = recorder.record
        if record is None:
            raise RuntimeError("No exchange-tree conversation is active")

        target, parent_id = self._validate_resubmit_target(
            record, exchange_id, kind
        )
        preserve_live_turns = _history_plan.active_path_turns_are_incompatible(
            record, adapter=self.adapter
        )
        assert target.input is not None  # _validate_resubmit_target
        submitted_input = self._normalize_resubmit_input(
            target.input if replacement_input is None else replacement_input
        )

        # Preflight against a copy so malformed rewind state cannot move the
        # persisted path after input validation has already succeeded.
        prefix = record.model_copy(deep=True)
        prefix.set_active_leaf(parent_id)
        node_ids = tuple(prefix.path_node_ids())
        rewind_state = _history_plan.preflight_state(
            prefix,
            node_ids,
            recorder.rewind_hooks,
            adapter=self.adapter,
            preserve_live_turns=preserve_live_turns,
            reject_unavailable=True,
            phase="rewind",
        )

        async with self._destructive_mutation(block_input=True):
            if preserve_live_turns:
                await self._open_resubmit_sibling_locked(
                    record,
                    rewind_state,
                    parent_id,
                    submitted_input,
                    message_index,
                )
                return
            action: HistoryEditProjectionAction = {
                "type": "history_edit_projection",
                "requestId": request_id,
                "index": message_index,
                "content": str(submitted_input.content),
                "attachments": _attachment_projection(
                    submitted_input.attachments
                ),
            }

            async def send_resubmission() -> None:
                with _restore_step("sending the resubmission"):
                    await self.chat._send_action(action)

            await self._rewind_locked(
                record,
                rewind_state,
                parent_id,
                save_step="saving the resubmission",
                send=send_resubmission,
            )

    async def _rewind_locked(
        self,
        record: ConversationRecordV2,
        rewind_state: StatePlan,
        leaf: str,
        *,
        save_step: str,
        send: Callable[[], Awaitable[None]],
    ) -> None:
        """The shared rewind skeleton: capture the close, run the plan,
        move and persist the leaf, send, clear a failed restore."""
        recorder = self._exchange_recorder
        async with self._exchange_mutation():
            current_leaf = record.active_leaf
            if current_leaf is None:
                raise ValueError("Exchange-tree record has no active leaf.")
            await recorder.capture_state_locked(current_leaf, "node_close")
            try:
                # Rewind hooks run before the leaf move is persisted, so a
                # hook failure leaves the store pointing at the leaf the
                # user still sees and the fail-to-fresh-draft recovery
                # below is the only thing that changed. The plan was
                # preflighted against a deep copy, so nothing here mutates
                # until the hooks have accepted the rewind.
                with _restore_step(save_step):
                    await _history_plan.run_plan(rewind_state)
                    await recorder.persist_active_leaf_locked(record, leaf)
                await send()
            except BaseException as error:
                await self._clear_failed_restore(error)
                raise

    async def _open_resubmit_sibling_locked(
        self,
        record: ConversationRecordV2,
        rewind_state: StatePlan,
        parent_id: str,
        submitted_input: StoredMessage,
        message_index: int,
    ) -> None:
        """The preserve-live-turns resubmit path: the failed target and
        its shared parent stay immutable, and non-turn hooks still rewind
        the ordinary parent prefix before the accepted input opens its
        sibling."""
        recorder = self._exchange_recorder
        async with self._exchange_mutation():
            if record.active_leaf is None:
                raise ValueError("Exchange-tree record has no active leaf.")
            await _history_plan.run_plan(rewind_state, skip_turns=True)
            recorder.move_active_leaf_locked(record, parent_id)
            accepted_exchange_id = (
                self.chat._transcript.record_accepted_input(submitted_input)
            )
            await recorder.accepted_resubmit_input_locked(
                accepted_exchange_id, submitted_input
            )
            accepted_input_action: HistoryAcceptedInputProjectionAction = {
                "type": "history_accepted_input_projection",
                "index": message_index,
                "content": str(submitted_input.content),
                "attachments": _attachment_projection(
                    submitted_input.attachments
                ),
            }
            projection_error: BaseException | None = None
            try:
                await self.chat._send_action(accepted_input_action)
            except BaseException as error:
                projection_error = error
                raise
            finally:
                try:
                    self.chat._publish_accepted_user_input(submitted_input)
                except BaseException as publication_error:
                    if projection_error is None:
                        raise
                    raise projection_error from publication_error

    async def retry(
        self, exchange_id: str, *, request_id: str, message_index: int
    ) -> None:
        await self.resubmit(
            exchange_id,
            kind="retry",
            request_id=request_id,
            message_index=message_index,
        )

    async def regenerate(
        self, exchange_id: str, *, request_id: str, message_index: int
    ) -> None:
        await self.resubmit(
            exchange_id,
            kind="regenerate",
            request_id=request_id,
            message_index=message_index,
        )

    # -- list mutations ----------------------------------------------------

    async def rename(self, conv_id: str, title: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        title = " ".join(title.split())[:MAX_TITLE_LEN]
        if not title:
            return
        recorder = self._exchange_recorder
        renamed = False
        async with self._exchange_mutation():
            if await recorder.rename_active_locked(conv_id, title):
                renamed = True
            else:
                record = await self._get_record(self.partition, conv_id)
                if record is not None:
                    record.title = title
                    record.title_source = "user"
                    await self.store.put(self.partition, record)
                    renamed = True
        if renamed:
            await self.send_history_update()

    async def delete(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        async with self._destructive_mutation():
            async with self._exchange_mutation():
                if self.on_evict is not None:
                    await self.on_evict(conv_id)
                await self.store.delete(self.partition, conv_id)
                exchange_record = self._exchange_recorder.record
                if exchange_record is not None and exchange_record.id == conv_id:
                    self._exchange_recorder.reset()
                    await self.clear_active()
                    self.adapter.set_turns_json([])
                    await self.chat.clear_messages()
                    if self.on_active_id_change is not None:
                        await self.on_active_id_change(None)
                await self.send_history_update()

    # -- branch navigation --------------------------------------------------

    async def _send_sibling_metadata(self) -> None:
        record = self._exchange_recorder.record
        if record is None:
            return
        sibling_meta = record.path_sibling_metadata()
        if not sibling_meta:
            # No "clear all badges" payload is needed. A badge only exists at a
            # fork point (a node with >1 sibling), and forks are permanent:
            # navigating between siblings keeps that node's sibling count > 1,
            # and nothing prunes nodes from a record. So a path that currently
            # has no forks never had one, meaning there is no stale badge to
            # clear — empty here always means the client already shows none.
            return
        data: dict[int, dict[str, int]] = {}
        for node_id, msg_idx in record.iter_visible_inputs():
            if node_id in sibling_meta:
                idx, total = sibling_meta[node_id]
                data[msg_idx] = {"index": idx, "total": total}
        if data:
            action: UpdateSiblingsAction = {
                "type": "update_siblings",
                "data": data,
            }
            await self.chat._send_action(action)

    async def _send_exchange_metadata(self) -> None:
        recorder = self._exchange_recorder
        if recorder.record is None:
            return

        data: dict[int, ExchangeMetadata] = {}
        for node_id, message_index in recorder.record.iter_visible_inputs():
            node = recorder.record.nodes[node_id]
            metadata: ExchangeMetadata = {
                "status": node.status,
                "retryable": node.status in _RETRYABLE_STATUSES,
            }
            if node.status == "error":
                metadata["error_message"] = project_history_error_message(
                    node.error.message if node.error is not None else None
                )
            data[message_index] = metadata
        if data:
            action: UpdateExchangeMetadataAction = {
                "type": "update_exchange_metadata",
                "data": data,
            }
            await self.chat._send_action(action)

    async def handle_resubmit(
        self,
        message_index: int,
        kind: str,
        *,
        request_id: str | None = None,
    ) -> None:
        recorder = self._exchange_recorder
        if request_id is None or not request_id:
            raise ValueError("Exchange-tree resubmits require a request ID.")
        record = recorder.record
        if record is None:
            return
        exchange_id = record.exchange_id_for_user_message_index(message_index)
        await self.resubmit(
            exchange_id,
            kind=kind,
            request_id=request_id,
            message_index=message_index,
        )

    async def handle_navigate(
        self,
        message_index: int,
        direction: str,
        *,
        request_id: str | None = None,
    ) -> None:
        if direction not in ("prev", "next"):
            return
        recorder = self._exchange_recorder
        if request_id is None or not request_id:
            raise ValueError("Exchange-tree navigation requires a request ID.")
        record = recorder.record
        if record is None:
            return

        node_id = record.exchange_id_for_user_message_index(message_index)
        siblings = record.siblings_of(node_id)
        current_pos = siblings.index(node_id)
        if direction == "prev":
            if current_pos == 0:
                return
            target = siblings[current_pos - 1]
        else:
            if current_pos == len(siblings) - 1:
                return
            target = siblings[current_pos + 1]

        leaf = record.subtree_leaf(target)
        projection = record.model_copy(deep=True)
        projection.set_active_leaf(leaf)
        node_ids = tuple(projection.path_node_ids())
        rewind_state = _history_plan.preflight_state(
            projection,
            node_ids,
            recorder.rewind_hooks,
            adapter=self.adapter,
            reject_unavailable=True,
            phase="rewind",
        )

        async with self._destructive_mutation(block_input=True):

            async def send_navigation() -> None:
                # The display replay reads only node content by id, so it
                # does not depend on the record's leaf pointer.
                with _restore_step(
                    "replaying the conversation display"
                ):
                    await self._replay_exchange_display(record, node_ids)
                with _restore_step("sending the navigation update"):
                    await self._send_sibling_metadata()
                    await self._send_exchange_metadata()
                    await self.send_history_update()

            await self._rewind_locked(
                record,
                rewind_state,
                leaf,
                save_step="saving the navigation change",
                send=send_navigation,
            )

    async def handle_edit(
        self,
        message_index: int,
        content: str,
        attachments: "list[dict[str, Any]] | None" = None,
        *,
        request_id: str | None = None,
    ) -> None:
        recorder = self._exchange_recorder
        record = recorder.record
        if record is None:
            return
        if request_id is None:
            raise ValueError("Exchange-tree edits require a request ID.")
        exchange_id = record.exchange_id_for_user_message_index(message_index)
        replacement = self._replacement_resubmit_input(content, attachments)
        await self.resubmit(
            exchange_id,
            replacement,
            kind="edit",
            request_id=request_id,
            message_index=message_index,
        )

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
            "active_id": self._active_id_now(),
            "transition_protocol": "completion-v2",
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
        self._restore_bootstrap: "Literal['recorded', 'live']" = (
            cfg.restore_bootstrap
        )
        # This is the initial history effect's existing completion fact. V2
        # admission reads it synchronously at every guard site, through
        # `_history_action_admitted()` (the history input effects in this
        # module and the entry points in `_chat.py`).
        self._initial_history_initialized = False

    def enable(self) -> None:
        """Enable chat history for the current session. No-op if already started."""
        if not self._started:
            self._start()

    def _history_action_admitted(self) -> bool:
        """Admit private actions once v2's initial history decision is known."""
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

        # Stamp the active history pointer into any Shiny server bookmark.
        # V2 records need the selected leaf as well as the conversation ID.
        stamp_key = f"{chat.id}_history_exchange_pointer"
        # Legacy v1 bookmark stamp: a v1 server stamped only the conversation
        # id here. When the v2 pointer above is absent, restoring a bookmark
        # written by a v1 server reads this key instead (shinychat#dmgt,
        # plan §7.8). Nothing writes it anymore — the v1 write site died with
        # the v1 runtime (shinychat#4b9z) — but the read-gate below must stay
        # as long as v1-written bookmarks exist in the wild.
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

        async def finish_initial(restored: bool) -> None:
            # Every initial path sends its authoritative history_update before
            # calling this helper.
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
                        # Settlement is advisory; preserve the restore error.
                        pass
                    raise

            owner_scope = scope()  # req() retries until token arrives
            controller.partition = ConversationPartition(
                chat_id=str(chat.id), scope=owner_scope
            )

            # Priority 1: restore from a Shiny bookmark context (any mode).
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
                    # that conversation at its active leaf (shinychat#dmgt,
                    # plan §7.8). The v2 pointer above keeps precedence
                    # when both keys exist; a present-but-invalid v2
                    # pointer still fails loudly below rather than
                    # silently falling back.
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
                        # pointer (shinychat#dmgt, plan §7.8). A v1 record
                        # upgrades on read (shinychat#e0x2) — never a silent
                        # no-restore.
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

            # Priority 2: restore from the mode-specific ID source.
            # Reading these inputs may raise SilentException if the browser
            # hasn't sent them yet (they're delivered after Shiny's
            # initializedPromise resolves, which is after the first flush).
            # Keep the initial readiness false until after send_history_update()
            # so the effect retries correctly on the next flush rather than
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

        @reactive.effect
        @reactive.event(chat._session.input[ids.new])
        async def _on_new():
            request_id = _history_transition_request_id(
                chat._session.input[ids.new]()
            )
            try:
                # Mirror the edit/navigate/resubmit input effects: a new-chat
                # request that lands before the initial history decision would
                # race the pending restore (and publish a history_update that
                # releases client-side admission early), so it is dropped.
                if not self._history_action_admitted():
                    return
                if controller.partition is None:
                    return
                await controller.new_chat()
            except Exception as e:
                await notify_error("Could not start a new chat", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

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
            payload = chat._session.input[ids.delete]()
            request_id = _history_transition_request_id(payload)
            try:
                if controller.partition is None:
                    return
                await controller.delete(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not delete conversation", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_edit])
        async def _on_edit():
            payload = chat._session.input[ids.message_edit]()
            request_id = _history_transition_request_id(payload)
            try:
                if not self._history_action_admitted():
                    return
                if controller.partition is None:
                    return
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
            except Exception as e:
                await notify_error("Could not edit message", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_navigate])
        async def _on_navigate():
            payload = chat._session.input[ids.message_navigate]()
            request_id = _history_transition_request_id(payload)
            try:
                if not self._history_action_admitted():
                    return
                if controller.partition is None:
                    return
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
            except Exception as e:
                await notify_error("Could not navigate messages", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_resubmit])
        async def _on_resubmit():
            payload = chat._session.input[ids.message_resubmit]()
            request_id = _history_transition_request_id(payload)
            try:
                if not self._history_action_admitted():
                    return
                if controller.partition is None:
                    return
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
            except Exception as e:
                await notify_error("Could not retry message", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        def _on_session_end() -> None:
            if self._on_session_end is None:
                return
            # The session consumed the registration by firing it; keep the
            # tracked state truthful so a later `_teardown()` won't re-run.
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
