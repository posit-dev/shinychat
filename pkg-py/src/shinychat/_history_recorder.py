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
        self, context: CaptureContext
    ) -> StateEntry | None:
        assert self.record is not None
        prompt = self._host.adapter.get_system_prompt()
        if prompt is None:
            prompt = ""
        # Preserve historical prompt inheritance before replacing the parent.
        sparse_snapshot_entry(
            self.record,
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

    def _capture_values(self, context: CaptureContext) -> StateEntry | None:
        return self._capture_values_at(context.node_id)

    def _capture_values_at(
        self, node_id: str, *, strict: bool = False
    ) -> StateEntry | None:
        """Run the ``on_save`` callbacks and sparsely record their values.

        The callbacks receive a fresh dictionary and run inside
        ``reactive.isolate()``: this capture also fires at stream finish,
        inside the stream task where reactive reads are denied, and
        callbacks legitimately read reactive state (``input``, reactive
        values) without taking reactive dependencies. The result is
        validated as JSON (non-string keys and non-finite floats are
        refused, never coerced) and detached from the callback's object.
        Values treat every validated object -- including ``{}`` -- as
        effective, so an empty object records an explicit value rather
        than inheriting.

        Error policy: an *automatic* capture (``strict=False`` -- root
        close, stream finish, node close, response settlement, retitle)
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
        assert self.record is not None
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
            previous = self.record.nodes[node_id].state.get(VALUES_STATE_KEY)
            if previous is not None:
                return previous.model_copy(deep=True)
            return None

        return sparse_snapshot_entry(
            self.record,
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

    def _capture_turns(self, context: CaptureContext) -> StateEntry:
        adapter = self._host.adapter
        turns, _ = canonical_turns(adapter.get_turns_json())
        assert self.record is not None
        # Pin legacy delta children before replacing their shared prefix.
        for child_id in self.record.nodes[context.node_id].children:
            child = self.record.nodes[child_id]
            entry = child.state.get(TURNS_STATE_KEY)
            if entry is None or entry.mode != "delta":
                continue
            path_ids = [child_id]
            parent_id = child.parent_id
            while parent_id is not None:
                path_ids.append(parent_id)
                parent_id = self.record.nodes[parent_id].parent_id
            path = tuple(reversed(path_ids))
            saved_context = StatePathContext(
                conversation_id=self.record.id,
                active_leaf=child_id,
                node_ids=path,
                entries=tuple(
                    (node_id, self.record.nodes[node_id].state[TURNS_STATE_KEY])
                    for node_id in path
                    if TURNS_STATE_KEY in self.record.nodes[node_id].state
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

    async def capture_state_locked(
        self, node_id: str, reason: CaptureReason, *, model_only: bool = False
    ) -> None:
        assert self.record is not None
        if self._read_only:
            # A read-only record's saved state is immutable: close/switch/
            # New must never replace it with cleared live turns.
            return
        node = self.record.nodes[node_id]
        context = CaptureContext(node_id=node_id, reason=reason)
        for name, hook in self._capture_hooks.items():
            if model_only and name not in (
                TURNS_STATE_KEY,
                SYSTEM_PROMPT_STATE_KEY,
            ):
                continue
            entry = hook(context)
            if inspect.isawaitable(entry):
                entry = await entry
            if entry is None:
                node.state.pop(name, None)
            else:
                node.state[name] = entry

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
        if not self._read_only:
            # Existing delta branches may depend on a legacy captured pending
            # ancestor. Materialize their known context before suppressing
            # unresolved model entries; never reconstruct it from display.
            for node_id, node in snapshot.nodes.items():
                if node.status == "pending":
                    continue
                path_ids = [node_id]
                parent_id = node.parent_id
                while parent_id is not None:
                    path_ids.append(parent_id)
                    parent_id = snapshot.nodes[parent_id].parent_id
                path = tuple(reversed(path_ids))
                if not any(
                    snapshot.nodes[parent].status == "pending"
                    and snapshot.nodes[parent].input is not None
                    and TURNS_STATE_KEY in snapshot.nodes[parent].state
                    for parent in path
                ):
                    continue
                context = StatePathContext(
                    conversation_id=snapshot.id,
                    active_leaf=node_id,
                    node_ids=path,
                    entries=tuple(
                        (parent, snapshot.nodes[parent].state[TURNS_STATE_KEY])
                        for parent in path
                        if TURNS_STATE_KEY in snapshot.nodes[parent].state
                    ),
                )
                turns, unavailable = materialize_restore_turns(
                    context, adapter=self._host.adapter
                )
                if unavailable is not None:
                    raise ValueError(
                        "Cannot project a legacy branch without its model context."
                    )
                node.state[TURNS_STATE_KEY] = StateEntry(
                    kind=turn_entry_kind(self._host.adapter),
                    version=1,
                    mode="snapshot",
                    data=cast(JsonValue, turns),
                )
                prompt = latest_system_prompt(
                    tuple(
                        (
                            parent,
                            snapshot.nodes[parent].state[
                                SYSTEM_PROMPT_STATE_KEY
                            ],
                        )
                        for parent in path
                        if SYSTEM_PROMPT_STATE_KEY
                        in snapshot.nodes[parent].state
                    )
                )
                if prompt is not None:
                    node.state[SYSTEM_PROMPT_STATE_KEY] = prompt.model_copy(
                        deep=True
                    )
            for node in snapshot.nodes.values():
                if node.status == "pending":
                    node.messages.clear()
                    # Structural legacy roots may retain the captured base
                    # of terminal delta descendants. Accepted inputs cannot.
                    if node.input is not None:
                        node.state.pop(TURNS_STATE_KEY, None)
                        node.state.pop(SYSTEM_PROMPT_STATE_KEY, None)
        await self._host.store.put(partition, snapshot)
        if (
            self.record is record
            and self._host._active_id_now() == record_id
            and self._active_id_published_for is not record
        ):
            published = await self._host._publish_active_id(record)
            if published:
                self._active_id_published_for = record

    def _capture_app_state(self, *, strict: bool = False) -> None:
        """Capture application values at the active leaf, sparsely.

        The explicit/boundary save points (explicit save, response
        settlement, retitle) capture only values -- never the model-state
        entries the full capture-hook cycle owns. The record-on-change
        rule is the same as the hook's: the root always records,
        descendants record only changes against their ancestor path.
        ``strict`` carries the caller's error policy to
        ``_capture_values_at``: the public explicit save re-raises
        callback/payload failures, while the automatic boundary points
        warn and retain. Read-only suppression wins at this central
        capture point: even when a retitle still writes its title
        metadata, live app values never replace the saved record's.
        """
        assert self.record is not None
        if self._read_only:
            # A read-only record's saved state is immutable, exactly as
            # in capture_state_locked; the title writes that share this
            # path stay live, but the values capture does not.
            return
        node_id = self.record.active_leaf
        assert node_id is not None
        node = self.record.nodes[node_id]
        entry = self._capture_values_at(node_id, strict=strict)
        if entry is None:
            node.state.pop(VALUES_STATE_KEY, None)
        else:
            node.state[VALUES_STATE_KEY] = entry

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
                or leaf in self._stream_exchanges.values()
            ):
                return False
            # An empty draft root can be explicitly saved; unlike a streamed
            # inputless root it has no response in flight.
            self._close_root_if_inactive()
        await self.capture_state_locked(leaf, "node_close", model_only=True)
        if strict:
            self._capture_app_state(strict=True)
        await self.persist_record_locked()
        return True

    async def response_settled(self) -> bool:
        async with self.lock:
            if (
                self.record is None
                or self._host.partition is None
                or self._read_only
            ):
                return False
            leaf = self.record.active_leaf
            assert leaf is not None
            if self.record.nodes[leaf].status == "pending":
                return False
            self._capture_app_state()
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
                and self.record.root_id not in self._stream_exchanges.values()
            ):
                await self.capture_state_locked(
                    self.record.root_id, "root_close"
                )
                self._close_root_if_inactive()
            elif self.record.nodes[active_leaf].status == "pending":
                # Admission still validates the actual client, but an
                # unresolved predecessor must not become a model checkpoint.
                self._validate_model_state()
            else:
                await self.capture_state_locked(
                    active_leaf, "node_close", model_only=True
                )
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
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            captured = CapturedMessage.from_stored_message(
                entry.message, icon=entry.icon
            )
            if stream_id is None:
                self.record.append_message(target, captured)
            else:
                self._stream_exchanges[stream_id] = target
                self.record.append_stream_message(target, captured)
            if stream_id is None:
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
        if self._host.partition is None or self._read_only:
            return

        async with self.lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            await self.capture_state_locked(exchange_id, "stream_finish")
            self.record.finish_exchange(exchange_id, status, error)
            await self.persist_record_locked()
            self._stream_exchanges.pop(stream_id, None)
