"""The v2 exchange-tree capture owner for one history session.

``_ExchangeRecorder`` owns the v2 record, its single ``asyncio.Lock``, the
capture/restore/rewind hook registries, full turn snapshots, record
and root lifecycle, and persistence/bookmark state. Restore/rewind
*planning* lives in ``_history_plan`` as pure functions; this class only
executes what those functions plan, and keeps ``_restore_turns`` because
it writes adapter turns.

``HistoryController`` (in ``_history``) re-enters the one lock via
``_exchange_mutation``.
"""

from __future__ import annotations

import asyncio
import inspect
import warnings
from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Mapping,
    Protocol,
    cast,
)

from pydantic import JsonValue

from ._chat_transcript import TranscriptEntry
from ._chat_types import StoredMessage
from ._history_client import TurnsAdapter
from ._history_plan import (
    CaptureContext,
    CaptureHook,
    CaptureReason,
    RestoreHook,
    RewindHook,
    StatePathContext,
    canonical_turns,
    canonical_values,
    latest_system_prompt,
    materialize_restore_turns,
    sparse_snapshot_entry,
    turn_entry_kind,
)
from ._history_store import ConversationPartition, ConversationStore
from ._history_title import fallback_title_from_text
from ._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    ConversationRecordV2,
    StateEntry,
    TurnDict,
    new_conversation_record_v2,
)

if TYPE_CHECKING:
    from ._chat import Chat


class RecorderHost(Protocol):
    """The host surface ``_ExchangeRecorder`` reads from its controller.

    Declares exactly the members the recorder uses: the turns adapter, the
    active partition, the store, the chat (for capture-callback suspension
    during display replay), app-state save callbacks, active-id access and
    publish, conversation-id allocation, and ``send_history_update``. Any
    test double for the recorder's host must provide all of them; there are
    no optional fallbacks.
    """

    adapter: TurnsAdapter
    partition: ConversationPartition | None
    store: ConversationStore
    chat: Chat
    _save_callbacks: list[Callable[[dict[str, Any]], None]]

    def _active_id_now(self) -> str | None: ...

    def _allocate_conversation_id(self) -> str: ...

    async def _publish_active_id(
        self, record: ConversationRecordV2
    ) -> bool: ...

    async def send_history_update(self) -> None: ...


class _ExchangeRecorder:
    def __init__(self, host: RecorderHost) -> None:
        self._host = host
        self.record: ConversationRecordV2 | None = None
        self._stream_exchanges: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self._capture_hooks: dict[str, CaptureHook] = {}
        self._restore_hooks: dict[str, RestoreHook] = {}
        self._rewind_hooks: dict[str, RewindHook] = {}
        self._active_id_published_for: ConversationRecordV2 | None = None
        self._source_isolated = False
        # Ephemeral flag for the loaded record (never a saved field): a
        # restored record whose saved model context is unavailable is
        # view-only. Captures and message mutations are suppressed so
        # close/switch/New cannot replace the saved context with cleared
        # live turns. An interrupted viewer also cannot write its source.
        self._read_only: bool = False
        if (
            isinstance(host.adapter, TurnsAdapter)
            and host.adapter.has_system_prompt()
        ):
            self._register_capture_hook(
                SYSTEM_PROMPT_STATE_KEY, self._capture_system_prompt
            )
            self._register_restore_hook(
                SYSTEM_PROMPT_STATE_KEY, self._restore_system_prompt
            )
            self._register_rewind_hook(
                SYSTEM_PROMPT_STATE_KEY, self._rewind_system_prompt
            )
        self._register_capture_hook(TURNS_STATE_KEY, self._capture_turns)
        self._register_restore_hook(TURNS_STATE_KEY, self._restore_turns)
        self._register_rewind_hook(TURNS_STATE_KEY, self._restore_turns)
        # Application values capture through the same state lifecycle, even
        # without a model client; they own no restore/rewind hook because
        # they are delivered to on_restore/on_navigate callbacks rather
        # than applied to the client.
        self._register_capture_hook(VALUES_STATE_KEY, self._capture_values)

    @property
    def read_only(self) -> bool:
        """Whether the loaded record's saved model context is unavailable.

        Set when a restored record is installed; cleared on reset (New
        chat, delete, failed-restore cleanup) and reclassified on every
        install. Once set, it is kept for the loaded conversation across
        sibling navigation, even when another sibling has compatible
        turns.
        """
        return self._read_only

    @property
    def restore_hooks(self) -> Mapping[str, RestoreHook]:
        """The restore hook registry, exposed read-only for preflights."""
        return self._restore_hooks

    @property
    def rewind_hooks(self) -> Mapping[str, RewindHook]:
        """The rewind hook registry, exposed read-only for preflights."""
        return self._rewind_hooks

    def _register_capture_hook(self, name: str, hook: CaptureHook) -> None:
        self._capture_hooks[name] = hook

    def _register_restore_hook(self, name: str, hook: RestoreHook) -> None:
        self._restore_hooks[name] = hook

    def _register_rewind_hook(self, name: str, hook: RewindHook) -> None:
        self._rewind_hooks[name] = hook

    def _capture_system_prompt(
        self,
        context: CaptureContext,
        *,
        record: ConversationRecordV2 | None = None,
    ) -> StateEntry | None:
        record = self.record if record is None else record
        assert record is not None
        prompt = self._host.adapter.get_system_prompt()
        if prompt is None:
            prompt = ""
        # Preserve historical prompt inheritance before replacing the parent.
        sparse_snapshot_entry(
            record,
            context.node_id,
            SYSTEM_PROMPT_STATE_KEY,
            prompt,
            is_effective=lambda entry: (
                entry is not None and entry.data is not None
            ),
            kind="system_prompt",
        )
        return StateEntry(
            kind="system_prompt", version=1, mode="snapshot", data=prompt
        )

    def _capture_values(
        self,
        context: CaptureContext,
        *,
        record: ConversationRecordV2 | None = None,
    ) -> StateEntry | None:
        return self._capture_values_at(
            context.node_id, strict=True, record=record
        )

    def _capture_values_at(
        self,
        node_id: str,
        *,
        strict: bool = False,
        record: ConversationRecordV2 | None = None,
    ) -> StateEntry | None:
        """Run the ``on_save`` callbacks and sparsely record their values.

        The callbacks receive a fresh dictionary and run inside
        ``reactive.isolate()`` so callbacks can read reactive state without
        taking dependencies. Response-associated values are captured only at
        post-flush settlement, after the stream task can expose its result.
        The result is validated as JSON (non-string keys and non-finite floats are
        refused, never coerced) and detached from the callback's object.
        Values treat every validated object -- including ``{}`` -- as
        effective, so an empty object records an explicit value rather
        than inheriting.

        Error policy: an *automatic* capture (``strict=False`` -- root
        close, node close, response settlement, retitle)
        never lets a failing callback or an invalid payload block the
        move that triggered it. The error is warned to the developer
        with its details, and the node keeps its previously recorded
        entry (deep-copied) -- or stays missing, so inheritance answers
        -- never losing recorded values to a failed capture. An
        *explicit* capture (``strict=True``, the ``chat.history.save()``
        path) re-raises, so the caller learns the save did not record.
        Only ``Exception`` is caught; cancellation and fatal errors
        propagate in both modes, and failures here never swallow the
        store/model-state errors of the surrounding flow.
        """
        record = self.record if record is None else record
        assert record is not None
        from shiny import reactive

        try:
            values: dict[str, Any] = {}
            with reactive.isolate():
                for callback in self._host._save_callbacks:
                    callback(values)
            data = canonical_values(values)
        except Exception as error:
            if strict:
                raise
            # Developer diagnostics only: automatic capture failure warns
            # but completes, with no new user-notification policy.
            warnings.warn(
                "Automatic app-state values capture failed at exchange "
                f"{node_id!r}; keeping the previously recorded values "
                f"({type(error).__name__}: {error}).",
                stacklevel=2,
            )
            previous = record.nodes[node_id].state.get(VALUES_STATE_KEY)
            if previous is not None:
                return previous.model_copy(deep=True)
            return None

        return sparse_snapshot_entry(
            record,
            node_id,
            VALUES_STATE_KEY,
            data,
            is_effective=lambda entry: entry is not None,
            kind="values",
            # A path without any entry resolves to {}: the default answers
            # the previous-value fallback, the unchanged dedupe, and the
            # child anchoring alike.
            default_entry=StateEntry(
                kind="values", version=1, mode="snapshot", data={}
            ),
        )

    def _restore_system_prompt(self, context: StatePathContext) -> None:
        entry = latest_system_prompt(context.entries)
        if entry is not None:
            self._host.adapter.set_system_prompt(cast(str, entry.data))

    def _rewind_system_prompt(self, context: StatePathContext) -> None:
        if context.previous_entries is None:
            raise RuntimeError(
                "The recorded source path is required before rewind."
            )
        target = latest_system_prompt(context.entries)
        # Compare saved paths, not the live prompt or the node-close capture:
        # an on_restore override must survive a same-prompt rewind.
        previous = latest_system_prompt(context.previous_entries)
        if target is not None and (
            previous is None or target.data != previous.data
        ):
            self._host.adapter.set_system_prompt(cast(str, target.data))

    def _capture_turns(
        self,
        context: CaptureContext,
        *,
        record: ConversationRecordV2 | None = None,
    ) -> StateEntry:
        adapter = self._host.adapter
        turns, _ = canonical_turns(adapter.get_turns_json())
        record = self.record if record is None else record
        assert record is not None
        # Pin legacy delta children before replacing their shared prefix.
        for child_id in record.nodes[context.node_id].children:
            child = record.nodes[child_id]
            entry = child.state.get(TURNS_STATE_KEY)
            if entry is None or entry.mode != "delta":
                continue
            path_ids = [child_id]
            parent_id = child.parent_id
            while parent_id is not None:
                path_ids.append(parent_id)
                parent_id = record.nodes[parent_id].parent_id
            path = tuple(reversed(path_ids))
            saved_context = StatePathContext(
                conversation_id=record.id,
                active_leaf=child_id,
                node_ids=path,
                entries=tuple(
                    (node_id, record.nodes[node_id].state[TURNS_STATE_KEY])
                    for node_id in path
                    if TURNS_STATE_KEY in record.nodes[node_id].state
                ),
            )
            saved_turns, unavailable = materialize_restore_turns(
                saved_context, adapter=adapter
            )
            if unavailable is not None:
                raise ValueError(
                    "Cannot replace a legacy prefix without its model context."
                )
            child.state[TURNS_STATE_KEY] = StateEntry(
                kind=turn_entry_kind(adapter),
                version=1,
                mode="snapshot",
                data=cast(JsonValue, saved_turns),
            )
        return StateEntry(
            kind=turn_entry_kind(adapter),
            version=1,
            mode="snapshot",
            data=cast(JsonValue, turns),
        )

    def _validate_model_state(self) -> None:
        canonical_turns(self._host.adapter.get_turns_json())
        self._host.adapter.get_system_prompt()

    def _builtin_capture(self, hook: CaptureHook) -> str | None:
        if not inspect.ismethod(hook) or hook.__self__ is not self:
            return None
        for key, function in (
            (TURNS_STATE_KEY, _ExchangeRecorder._capture_turns),
            (SYSTEM_PROMPT_STATE_KEY, _ExchangeRecorder._capture_system_prompt),
            (VALUES_STATE_KEY, _ExchangeRecorder._capture_values),
        ):
            if hook.__func__ is function:
                return key
        return None

    def _requires_app_capture(self) -> bool:
        return (
            bool(self._host._save_callbacks)
            or self._builtin_capture(self._capture_hooks[VALUES_STATE_KEY])
            != VALUES_STATE_KEY
        ) or any(
            key
            not in (TURNS_STATE_KEY, SYSTEM_PROMPT_STATE_KEY, VALUES_STATE_KEY)
            for key in self._capture_hooks
        )

    @staticmethod
    def _stage_state(record: ConversationRecordV2) -> ConversationRecordV2:
        # Builtin captures replace entries or pin fresh entries on children;
        # none mutate an existing payload. Copy every state map so turns,
        # sparse prompts, and sparse app values can all stage their child pins.
        return record.model_copy(
            update={
                "nodes": {
                    key: node.model_copy(update={"state": dict(node.state)})
                    for key, node in record.nodes.items()
                }
            }
        )

    async def capture_state_locked(
        self,
        node_id: str,
        reason: CaptureReason,
        *,
        model_only: bool = False,
        app_only: bool = False,
        strict: bool = True,
    ) -> bool:
        assert self.record is not None
        if self._read_only:
            return False
        # Hooks may pin inherited entries on children as well as returning a
        # frame. Run them against a detached staging tree, committing all state
        # dictionaries together only after every required hook succeeds.
        live = self.record
        staged = self._stage_state(live)
        context = CaptureContext(node_id=node_id, reason=reason)
        for name, hook in self._capture_hooks.items():
            is_model = name in (TURNS_STATE_KEY, SYSTEM_PROMPT_STATE_KEY)
            if (model_only and not is_model) or (app_only and is_model):
                continue
            builtin = self._builtin_capture(hook)
            try:
                if builtin == TURNS_STATE_KEY:
                    entry = self._capture_turns(context, record=staged)
                elif builtin == SYSTEM_PROMPT_STATE_KEY:
                    entry = self._capture_system_prompt(context, record=staged)
                elif builtin == VALUES_STATE_KEY:
                    entry = self._capture_values(context, record=staged)
                else:
                    entry = hook(context)
            except Exception as error:
                if name != VALUES_STATE_KEY or strict:
                    raise
                warnings.warn(
                    "Automatic app-state values capture failed at exchange "
                    f"{node_id!r}; keeping the previously recorded values "
                    f"({type(error).__name__}: {error}).",
                    stacklevel=2,
                )
                return False
            if inspect.isawaitable(entry):
                entry = await entry
            if entry is None:
                staged.nodes[node_id].state.pop(name, None)
            else:
                # Builtins already validate and detach their fresh payloads.
                # Overrides/wrappers/custom hooks cannot borrow that trust.
                staged.nodes[node_id].state[name] = (
                    entry
                    if builtin is not None
                    else StateEntry.model_validate(
                        canonical_values(entry.model_dump(mode="python"))
                    )
                )
        for key, node in staged.nodes.items():
            live.nodes[key].state = node.state
        return True

    async def _restore_turns(self, context: StatePathContext) -> None:
        if context.prepared_turns is None:
            raise RuntimeError("Turns must be materialized before restore.")
        turns = context.prepared_turns
        adapter = self._host.adapter
        if context.turns_unavailable:
            adapter.set_turns_json([])
            return
        adapter.set_turns_json(cast(list[TurnDict], turns))

    def install_restored_record(
        self,
        record: ConversationRecordV2,
        *,
        read_only: bool = False,
        source_isolated: bool = False,
    ) -> None:
        self.record = record
        self._source_isolated = source_isolated
        self._stream_exchanges.clear()
        self._active_id_published_for = None
        self._read_only = read_only

    async def _new_record(self, *, title: str) -> ConversationRecordV2:
        return new_conversation_record_v2(
            title=title,
            id=self._host._allocate_conversation_id(),
            client_info={
                str(key): str(value)
                for key, value in self._host.adapter.client_info().items()
            },
        )

    async def _content_exchange(
        self, exchange_id: str | None
    ) -> tuple[str | None, bool]:
        if self.record is None:
            if exchange_id is not None:
                return None, False
            self.record = await self._new_record(title="New chat")
            return self.record.active_leaf, True
        if exchange_id is not None:
            return (
                exchange_id if exchange_id in self.record.nodes else None,
                False,
            )
        return self.record.open_inputless_exchange(), False

    def reset(self) -> None:
        self.record = None
        self._stream_exchanges.clear()
        self._active_id_published_for = None
        self._read_only = False
        self._source_isolated = False

    @contextmanager
    def suspend_capture(self):
        transcript = self._host.chat._transcript
        transcript.set_capture_callbacks(
            on_accepted_input=None,
            on_message_committed=None,
            on_stream_started=None,
            on_stream_updated=None,
            on_stream_finished=None,
        )
        try:
            yield
        finally:
            transcript.set_capture_callbacks(
                on_accepted_input=self.accepted_input,
                on_message_committed=self.message_committed,
                on_stream_started=self.stream_started,
                on_stream_updated=self.stream_updated,
                on_stream_finished=self.stream_finished,
            )

    @property
    def source_isolated(self) -> bool:
        return self._source_isolated

    async def flush_pending(self) -> bool:
        """Capture model-only changes at a coherent completed position."""
        async with self.lock:
            if self._stream_exchanges:
                return False
            return await self.save_current_locked()

    async def persist_record_locked(self) -> None:
        record = self.record
        assert record is not None
        record_id = record.id
        partition = self._host.partition
        assert partition is not None
        if self._source_isolated:
            return
        # A custom store may retain its argument. Never hand it the working
        # record: later chunks and metadata edits must not move a checkpoint.
        snapshot = record.model_copy(deep=True)
        if (
            snapshot.nodes[snapshot.root_id].status == "pending"
            and snapshot.root_id in self._stream_exchanges.values()
        ):
            return
        for node in snapshot.nodes.values():
            # Classify legacy data by the documented default when rewriting it.
            # State on unfinished ancestors remains structural/recoverable data,
            # never evidence that the ancestor is a selectable checkpoint.
            node.checkpoint = node.checkpoint_state
            if not self._read_only and node.status == "pending":
                node.messages.clear()
        await self._host.store.put(partition, snapshot)
        if self.record is record:
            for node in record.nodes.values():
                if node.checkpoint is None:
                    node.checkpoint = node.checkpoint_state
        if (
            self.record is record
            and self._host._active_id_now() == record_id
            and self._active_id_published_for is not record
        ):
            published = await self._host._publish_active_id(record)
            if published:
                self._active_id_published_for = record

    def _capture_app_state(self, *, strict: bool = False) -> bool:
        assert self.record is not None
        if self._read_only:
            return False
        live = self.record
        staged = self._stage_state(live)
        node_id = live.active_leaf
        assert node_id is not None
        try:
            entry = self._capture_values_at(node_id, strict=True, record=staged)
            if entry is None:
                staged.nodes[node_id].state.pop(VALUES_STATE_KEY, None)
            else:
                staged.nodes[node_id].state[VALUES_STATE_KEY] = entry
        except Exception as error:
            if strict:
                raise
            warnings.warn(
                "Automatic app-state values capture failed at exchange "
                f"{node_id!r}; keeping the previously recorded values "
                f"({type(error).__name__}: {error}).",
                stacklevel=2,
            )
            return False
        for key, node in staged.nodes.items():
            live.nodes[key].state = node.state
        return True

    async def save_current(self) -> bool:
        # The public save is the explicit one: callback and payload
        # failures raise to the caller instead of warning.
        async with self.lock:
            return await self.save_current_locked(strict=True)

    async def save_current_locked(self, *, strict: bool = False) -> bool:
        if (
            self.record is None
            or self._host.partition is None
            or self._read_only
        ):
            return False
        leaf = self.record.active_leaf
        assert leaf is not None
        if self.record.nodes[leaf].status == "pending":
            if (
                leaf != self.record.root_id
                or not self.record.nodes[leaf].is_checkpoint
                or leaf in self._stream_exchanges.values()
            ):
                return False
            # An empty draft root can be explicitly saved; unlike a streamed
            # inputless root it has no response in flight.
        if not self.record.nodes[leaf].is_checkpoint:
            return False
        await self.capture_state_locked(
            leaf, "node_close", model_only=not strict
        )
        self._close_root_if_inactive()
        await self.persist_record_locked()
        return True

    async def response_settled(self) -> bool:
        """Persist settlement and report whether a write occurred, not reliability."""
        async with self.lock:
            if (
                self.record is None
                or self._host.partition is None
                or self._read_only
            ):
                return False
            leaf = self.record.active_leaf
            assert leaf is not None
            node = self.record.nodes[leaf]
            if node.status == "pending" or node.checkpoint_state == "invalid":
                return False
            if node.is_checkpoint and self._requires_app_capture():
                return False
            try:
                reliable = (
                    not self._requires_app_capture()
                    or await self.capture_state_locked(
                        leaf, "node_close", app_only=True
                    )
                )
            except Exception as error:
                warnings.warn(
                    "Automatic app-state values capture failed at exchange "
                    f"{leaf!r}; keeping the previously recorded values "
                    f"({type(error).__name__}: {error}).",
                    stacklevel=2,
                )
                reliable = False
            node.checkpoint = "valid" if reliable else "invalid"
            self.record.response_count += 1
            await self.persist_record_locked()
            return True

    async def rename_active_locked(self, conv_id: str, title: str) -> bool:
        if (
            self.record is None
            or self.record.id != conv_id
            or self._host.partition is None
        ):
            return False
        if self._source_isolated:
            raise RuntimeError(
                "Cannot rename an interrupted read-only conversation."
            )
        self.record.title = title
        self.record.title_source = "user"
        await self.persist_record_locked()
        return True

    async def retitle_active_locked(
        self, target: ConversationRecordV2, title: str
    ) -> bool:
        """Apply an LLM-generated title to the active record.

        Returns False without mutating when the active record moved on,
        the user renamed mid-call, or there is no partition to persist
        into — the controller's under-lock re-check lives here, so the
        record mutation stays recorder-owned.
        """
        if (
            self._source_isolated
            or self.record is not target
            or target.title_source == "user"
            or self._host.partition is None
        ):
            return False
        target.title = title
        target.title_source = "llm"
        self._capture_app_state()
        await self.persist_record_locked()
        return True

    async def persist_active_leaf_locked(
        self, record: ConversationRecordV2, leaf: str
    ) -> None:
        """Move the active leaf and persist, as one recorder-owned step."""
        assert record is self.record
        record.require_checkpoint(leaf)
        record.set_active_leaf(leaf)
        await self.persist_record_locked()

    async def bookmark_pointer(
        self, record: ConversationRecordV2 | None = None
    ) -> tuple[str, str] | None:
        """Return one atomic pointer snapshot for a live v2 record."""
        async with self.lock:
            active = self.record
            if (
                active is None
                or active.active_leaf is None
                or (record is not None and active is not record)
            ):
                return None
            return active.id, active.active_leaf

    async def settle_bookmark_state_id(
        self, conversation_id: str, node_id: str, state_id: str
    ) -> tuple[bool, str | None]:
        """Persist a bookmark URL only when its pointer is still active.

        The returned state id is safe to delete: it is either the replaced URL
        after a successful update or the newly minted stale URL.
        """
        async with self.lock:
            record = self.record
            if (
                self._source_isolated
                or record is None
                or record.id != conversation_id
                or record.active_leaf != node_id
            ):
                return False, state_id

            old_state_id = record.bookmark_state_id
            record.bookmark_state_id = state_id
            try:
                await self.persist_record_locked()
            except BaseException:
                record.bookmark_state_id = old_state_id
                raise
            return True, old_state_id if old_state_id != state_id else None

    def mark_active_id_published(self, record: ConversationRecordV2) -> None:
        if self.record is record and self._host._active_id_now() == record.id:
            self._active_id_published_for = record

    def _close_root_if_inactive(self) -> None:
        assert self.record is not None
        root_id = self.record.root_id
        if (
            self.record.nodes[root_id].status == "pending"
            and self.record.nodes[root_id].is_checkpoint
            and root_id not in self._stream_exchanges.values()
        ):
            self.record.finish_exchange(root_id, "ok", None)

    async def accepted_input(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        if self._host.partition is None or self._read_only:
            return

        async with self.lock:
            created = False
            if self.record is None:
                title = fallback_title_from_text(message.content)
                self.record = await self._new_record(title=title)
                created = True
            is_first_input = not any(
                node.input is not None for node in self.record.nodes.values()
            )
            active_leaf = self.record.active_leaf
            assert active_leaf is not None
            if (
                is_first_input
                and self.record.nodes[self.record.root_id].is_checkpoint
                and self.record.root_id not in self._stream_exchanges.values()
            ):
                # Failed recapture keeps the previously valid starting base,
                # not a new model frame under stale app values.
                await self.capture_state_locked(
                    self.record.root_id, "root_close", strict=False
                )
                self._close_root_if_inactive()
            elif not self.record.nodes[active_leaf].is_checkpoint:
                # Admission still validates the actual client, but an
                # unresolved predecessor must not become a model checkpoint.
                self._validate_model_state()
            else:
                await self.capture_state_locked(
                    active_leaf, "node_close", model_only=True
                )
            for node_id in self.record.path_node_ids():
                node = self.record.nodes[node_id]
                if node.checkpoint_state == "candidate":
                    node.checkpoint = "invalid"
            self.record.open_exchange(exchange_id, message)
            self._capture_app_state()
            await self.persist_record_locked()
            if created:
                await self._host.send_history_update()

    async def message_committed(
        self, exchange_id: str | None, entry: TranscriptEntry
    ) -> None:
        if entry.message.role not in ("user", "assistant"):
            return
        await self._commit_content(exchange_id, entry)

    async def stream_started(
        self,
        stream_id: str,
        exchange_id: str | None,
        entry: TranscriptEntry,
    ) -> None:
        await self._commit_content(exchange_id, entry, stream_id=stream_id)

    async def _commit_content(
        self,
        exchange_id: str | None,
        entry: TranscriptEntry,
        *,
        stream_id: str | None = None,
    ) -> None:
        if self._host.partition is None or self._read_only:
            return

        async with self.lock:
            if (
                entry.message.role == "assistant"
                and self.record is not None
                and exchange_id in self.record.nodes
                and self.record.nodes[exchange_id].status != "pending"
            ):
                # Independent responses must not reopen a coherent checkpoint.
                exchange_id = None
            previous_leaf = (
                self.record.active_leaf if self.record is not None else None
            )
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            if previous_leaf is not None and target != previous_leaf:
                previous = self.record.nodes[previous_leaf]
                if (
                    previous.status != "pending"
                    and previous.checkpoint_state == "candidate"
                ):
                    previous.checkpoint = "invalid"
            captured = CapturedMessage.from_stored_message(
                entry.message, icon=entry.icon
            )
            if stream_id is None:
                if entry.message.role == "assistant":
                    try:
                        await self.capture_state_locked(
                            target, "node_close", model_only=True
                        )
                    except Exception:
                        # The transcript has already committed this display.
                        # Retain it locally without publishing an unmatched
                        # terminal checkpoint or advancing settlement.
                        self.record.append_message(target, captured)
                        self.record.nodes[target].checkpoint = "invalid"
                        raise
                self.record.append_message(target, captured)
                if (
                    entry.message.role == "assistant"
                    and not self._requires_app_capture()
                ):
                    self.record.nodes[target].checkpoint = "valid"
            else:
                self._stream_exchanges[stream_id] = target
                self.record.append_stream_message(target, captured)
            if stream_id is None or (
                target != self.record.root_id
                and self.record.nodes[target].input is None
            ):
                # Publish an unresolved child marker, never streamed content.
                await self.persist_record_locked()
            if created:
                await self._host.send_history_update()

    async def stream_updated(
        self, stream_id: str, entry: TranscriptEntry
    ) -> None:
        if self._host.partition is None or self._read_only:
            return

        async with self.lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            captured = CapturedMessage.from_stored_message(
                entry.message, icon=entry.icon
            )
            self.record.replace_stream_message(exchange_id, captured)

    async def stream_finished(
        self,
        stream_id: str,
        status: Literal["ok", "cancelled", "error"],
        error: str | None,
    ) -> None:
        try:
            if self._host.partition is None or self._read_only:
                return

            async with self.lock:
                exchange_id = self._stream_exchanges.get(stream_id)
                if exchange_id is None or self.record is None:
                    return
                try:
                    await self.capture_state_locked(
                        exchange_id, "stream_finish", model_only=True
                    )
                except BaseException:
                    self.record.finish_exchange(exchange_id, status, error)
                    self.record.nodes[exchange_id].checkpoint = "invalid"
                    raise
                self.record.finish_exchange(exchange_id, status, error)
                if self.record.nodes[exchange_id].checkpoint_state != "invalid":
                    self.record.nodes[exchange_id].checkpoint = (
                        "candidate" if self._requires_app_capture() else "valid"
                    )
                await self.persist_record_locked()
        finally:
            # The provider stream has ended even if capture or persistence
            # fails. Durability retries operate on the record, not this map.
            self._stream_exchanges.pop(stream_id, None)
