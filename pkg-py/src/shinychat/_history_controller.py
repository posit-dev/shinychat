from __future__ import annotations

import asyncio
import inspect
import warnings
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Iterator,
    Literal,
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
from ._history_client import TurnsAdapter
from ._history_plan import (
    RestorePlan,
    StatePlan,
)
from ._history_recorder import _ExchangeRecorder
from ._history_store import (
    ConversationPartition,
    ConversationStore,
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
    from ._chat import Chat


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


# The in-flight restore step travels on the exception itself rather than a
# controller slot, so the mechanism stays stateless: an already-labeled
# exception is never relabeled (the innermost failing step wins), and the
# label is consumed when read, so a reused exception instance can't report
# a stale first-failure step. The label rides on a private attribute that
# only these helpers read and write; the matching PEP 678 note is pure
# traceback decoration for developers, and nothing parses it. Cancellation
# and other non-`Exception` failures stay unlabeled, matching
# `_history_plan.run_plan`.
_RESTORE_STEP_ATTR = "__shinychat_restore_step__"
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


def _take_restore_step_label(failure: BaseException) -> str | None:
    """Consume the restore-step label carried by `failure`, if any.

    Like the controller slot this replaces, the label is read once: a
    second cleanup of the same failure, or the same exception instance
    failing again later, gets no stale step from the first failure.
    """
    step = getattr(failure, _RESTORE_STEP_ATTR, None)
    if step is not None:
        delattr(failure, _RESTORE_STEP_ATTR)
    return step


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
    # Consumed unconditionally, matching the old slot's reset-on-read: a
    # StateHookError's wording wins, but the label never leaks past this
    # failure's cleanup either way.
    step = _take_restore_step_label(failure)
    if isinstance(failure, _history_plan.StateHookError):
        return f"the {failure.entry_name!r} state entry failed to apply"
    if step is not None:
        return f"failed while {step}"
    return None


@contextmanager
def _restore_step(step: str) -> Iterator[None]:
    """Label the in-flight restore step on the failure for the detail.

    The step is remembered only when the wrapped block fails, so a later
    ``_clear_failed_restore`` can name where the restore broke; successful
    steps leave nothing behind. The label rides on a private exception
    attribute, and an already-labeled exception is never relabeled, so
    the innermost step wins. The PEP 678 note is added purely for
    developers reading tracebacks. Cancellation and other
    non-``Exception`` failures stay unlabeled, matching
    ``_history_plan.run_plan``.
    """
    try:
        yield
    except Exception as error:
        if getattr(error, _RESTORE_STEP_ATTR, None) is None:
            setattr(error, _RESTORE_STEP_ATTR, step)
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
        self.on_active_id_change: (
            Callable[[str | None], Awaitable[None]] | None
        ) = None
        self.on_response_saved: (
            Callable[[ConversationRecordV2], Awaitable[None]] | None
        ) = None
        self.on_switch_restored: (
            Callable[[ConversationRecordV2], Awaitable[None]] | None
        ) = None
        self.on_evict: Callable[[str], Awaitable[None]] | None = None
        self.on_settled: Callable[[bool], Awaitable[None]] | None = None
        self.max_store_bytes: int | None = max_store_bytes
        self.restore_bootstrap: Literal["recorded", "live"] = restore_bootstrap
        self._title_task: asyncio.Task[None] | None = None
        self._over_budget_warned: bool = False
        self._exchange_recorder = _ExchangeRecorder(self)

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
        if self._active_id_now() == id:
            return
        self._active_id.set(id)
        if self.on_active_id_change is not None:
            await self.on_active_id_change(id)

    async def _publish_active_id(self, record: ConversationRecordV2) -> bool:
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

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response.

        A private response lifecycle callback is the only automatic caller.
        It fires after a completed assistant append or a stream terminal
        outcome, so replay, clear, accepted input, and partial chunks do not
        settle history.
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
        """Launch the retitle task when the active path carries its second
        input exchange.

        The count covers exchanges carrying an ``input`` on the active
        path, so navigation/resubmit siblings don't inflate the count the
        way a session counter would; the task fires when that count
        reaches 2, giving the LLM/custom ``title_fn`` the same
        two-exchange context as classic titling and skipping conversations
        abandoned after one message. The retitle is skipped when titling
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
            self.retitle(turns_flat, record)
        )
        self._title_task.add_done_callback(title_task_done)

    async def retitle(
        self, turns: list[TurnDict], target: ConversationRecordV2
    ) -> None:
        """Retitle the settled record with the LLM or custom ``title_fn``.

        The slow title call targets the record passed by the scheduler, so
        it titles the conversation that was eligible when scheduling
        happened; bail when the conversation switched away or the user
        renamed mid-call, then write the new title through the recorder's
        normal persist path (store put under the recorder lock) and
        publish it via ``history_update``.
        """
        recorder = self._exchange_recorder
        if recorder.record is not target:
            return
        if target.title_source == "user":
            return
        title = await generate_title(self.title_fn, self.client, turns)
        if (
            title is None
            or recorder.record is not target
            or target.title_source == "user"
        ):
            return
        async with self._exchange_mutation():
            if not await recorder.retitle_active_locked(target, title):
                return
        await self.send_history_update()

    def cancel_pending(self) -> None:
        """Cancel in-flight background work (e.g. titling) at teardown."""
        if self._title_task is not None and not self._title_task.done():
            self._title_task.cancel()

    async def notify_settled(self, restored: bool) -> None:
        """Fires the ``on_settled`` hook.

        Called whenever it's known whether the active conversation is a
        restore (True) or a fresh/new one (False) - at the initial restore
        decision, and again on every ``new_chat()``. The greeting wiring
        relies on this to defer greeting generation instead of racing the
        client's independent ``{id}_greeting_requested`` request.
        """
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
        for meta in reversed(metas):
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
            warnings.warn(
                f"Chat history restore failed ({detail or 'no detail'}): "
                f"{failure!r}",
                stacklevel=2,
            )

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
            pass

    def _prepare_exchange_restore(
        self,
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> tuple[tuple[str, ...], RestorePlan, Literal["recorded", "live"]]:
        recorder = self._exchange_recorder

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
            await self._clear_failed_restore(error)
            raise

        async with AsyncExitStack() as stack:
            try:
                with _restore_step("admitting the restored conversation"):
                    await stack.enter_async_context(
                        self._destructive_mutation()
                    )
                    await stack.enter_async_context(
                        self._exchange_mutation()
                    )
            except BaseException as error:
                # Admission failed before the restore body ran: it has no
                # attribution or cleanup of its own yet, so recover here.
                await self._clear_failed_restore(error)
                raise
            # Admitted: the restore body does its own step attribution and
            # failure cleanup; its failures propagate through the stack.
            await self._restore_exchange_record_locked(
                selected,
                node_ids=node_ids,
                planned_state=planned_state,
                bootstrap=bootstrap,
                persist_active_pointer=persist_active_pointer,
            )

    async def switch_to(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        if self._active_id_now() == conv_id:
            return
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
        if self.on_switch_restored is not None:
            try:
                await self.on_switch_restored(target)
            except Exception as exc:
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
                self._exchange_recorder.reset()
                await self.clear_active()
                if self.on_active_id_change is not None:
                    await self.on_active_id_change(None)
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

    async def _send_sibling_metadata(self) -> None:
        record = self._exchange_recorder.record
        if record is None:
            return
        sibling_meta = record.path_sibling_metadata()
        if not sibling_meta:
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
