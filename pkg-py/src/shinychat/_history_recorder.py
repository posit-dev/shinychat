"""The v2 exchange-tree capture owner for one history session.

``_ExchangeRecorder`` owns the v2 record, its single ``asyncio.Lock``, the
capture/restore/rewind hook registries, turn capture and baseline, record
and root lifecycle, and persistence/bookmark state. Restore/rewind
*planning* lives in ``_history_plan`` as pure functions; this class only
executes what those functions plan, and keeps ``_restore_turns`` because
it writes adapter turns and the turn baseline (recorder-owned state).

The R port mirrors this structure. ``HistoryController`` (in ``_history``)
re-enters the one lock via ``_exchange_mutation``; do not split it into
per-role locks.
"""

from __future__ import annotations

import asyncio
import inspect
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
    adapter_is_chatlas,
    canonical_turns,
    turn_entry_kind,
)
from ._history_store import ConversationPartition, ConversationStore
from ._history_title import fallback_title_from_text
from ._history_types import (
    TURNS_STATE_KEY,
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

    async def _publish_active_v2_id(
        self, record: ConversationRecordV2
    ) -> bool: ...

    async def send_history_update(self) -> None: ...


class _ExchangeRecorder:
    """Private v2 capture owner for one history controller session."""

    def __init__(self, host: RecorderHost) -> None:
        self._host = host
        self.record: ConversationRecordV2 | None = None
        self._stream_exchanges: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self._capture_hooks: dict[str, CaptureHook] = {}
        self._restore_hooks: dict[str, RestoreHook] = {}
        self._rewind_hooks: dict[str, RewindHook] = {}
        # None means the baseline is invalid: the next capture must take
        # a snapshot (the escape hatch from delta mode), because the
        # adapter's turns no longer extend what was last captured.
        self._turn_baseline: list[str] | None = []
        self._active_id_published_for: ConversationRecordV2 | None = None
        self._register_capture_hook(TURNS_STATE_KEY, self._capture_turns)
        self._register_restore_hook(TURNS_STATE_KEY, self._restore_turns)
        self._register_rewind_hook(TURNS_STATE_KEY, self._restore_turns)

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

    def _set_turn_baseline(self, turns: list[dict[str, Any]]) -> None:
        _, self._turn_baseline = canonical_turns(turns)

    def invalidate_turn_baseline(self) -> None:
        self._turn_baseline = None

    def _capture_turns(self, context: CaptureContext) -> StateEntry:
        adapter = self._host.adapter
        include_system_prompt = adapter_is_chatlas(adapter)
        turns, fingerprints = canonical_turns(
            adapter.get_turns_json(include_system_prompt=include_system_prompt)
        )
        baseline = self._turn_baseline
        is_prefix = (
            baseline is not None
            and len(baseline) <= len(fingerprints)
            and baseline == fingerprints[: len(baseline)]
        )
        if context.reason == "root_close" or not is_prefix:
            mode: Literal["delta", "snapshot"] = "snapshot"
            data = turns
        else:
            assert baseline is not None  # is_prefix implies a valid baseline
            mode = "delta"
            data = turns[len(baseline) :]

        self._turn_baseline = fingerprints
        assert self.record is not None
        previous = self.record.nodes[context.node_id].state.get(
            TURNS_STATE_KEY
        )
        if mode == "delta" and previous is not None:
            if not isinstance(previous.data, list):
                raise ValueError("Turn-state entries must contain a list.")
            data = [*previous.data, *data]
            mode = previous.mode
        return StateEntry(
            kind=turn_entry_kind(adapter),
            version=1,
            mode=mode,
            data=cast(JsonValue, data),
        )

    async def capture_state_locked(self, node_id: str, reason: CaptureReason) -> None:
        assert self.record is not None
        node = self.record.nodes[node_id]
        context = CaptureContext(node_id=node_id, reason=reason)
        for name, hook in self._capture_hooks.items():
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
            if context.bootstrap == "recorded":
                adapter.set_turns_json([])
            self._set_turn_baseline(turns)
            return
        adapter.set_turns_json(cast(list[TurnDict], turns))
        self._set_turn_baseline(turns)

    def install_restored_record(self, record: ConversationRecordV2) -> None:
        self.record = record
        self._stream_exchanges.clear()
        self._active_id_published_for = None

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
        # Back to a valid empty baseline (not None): the next capture on a
        # fresh record is a root-close snapshot either way, matching the
        # pre-sentinel behavior of the in-place clear.
        self._turn_baseline = []
        self._active_id_published_for = None

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

    async def persist_record_locked(self) -> None:
        record = self.record
        assert record is not None
        record_id = record.id
        partition = self._host.partition
        assert partition is not None
        await self._host.store.put(partition, record)
        if (
            self.record is not record
            or self._host._active_id_now() != record_id
        ):
            return

        if self._active_id_published_for is not record:
            published = await self._host._publish_active_v2_id(record)
            if published:
                self._active_id_published_for = record

    def _capture_app_state(self) -> None:
        assert self.record is not None
        values: dict[str, Any] = {}
        for callback in self._host._save_callbacks:
            callback(values)
        self.record.values = values

    async def save_current(self) -> bool:
        async with self.lock:
            return await self.save_current_locked()

    async def save_current_locked(self) -> bool:
        if self.record is None or self._host.partition is None:
            return False
        self._capture_app_state()
        await self.persist_record_locked()
        return True

    async def response_settled(self) -> bool:
        async with self.lock:
            if self.record is None or self._host.partition is None:
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
            self.record is not target
            or target.title_source == "user"
            or self._host.partition is None
        ):
            return False
        target.title = title
        target.title_source = "llm"
        self._capture_app_state()
        await self.persist_record_locked()
        return True

    def move_active_leaf_locked(
        self, record: ConversationRecordV2, leaf: str
    ) -> None:
        """Move the active leaf on a controller-validated record.

        The recorder owns every live-record mutation; the controller
        passes the record it validated and preflighted (``self.record``
        in every current flow).
        """
        record.set_active_leaf(leaf)

    async def persist_active_leaf_locked(
        self, record: ConversationRecordV2, leaf: str
    ) -> None:
        """Move the active leaf and persist, as one recorder-owned step."""
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
                record is None
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
        if (
            self.record is record
            and self._host._active_id_now() == record.id
        ):
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
        if self._host.partition is None:
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
            if is_first_input:
                await self.capture_state_locked(
                    self.record.root_id, "root_close"
                )
                self._close_root_if_inactive()
            else:
                active_leaf = self.record.active_leaf
                assert active_leaf is not None
                await self.capture_state_locked(active_leaf, "node_close")
            self.record.open_exchange(exchange_id, message)
            await self.persist_record_locked()
            if created:
                await self._host.send_history_update()

    async def accepted_resubmit_input_locked(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        """Open a degraded-resubmit sibling without closing its shared parent."""
        if self._host.partition is None:
            raise RuntimeError("HistoryController not initialized")

        if self.record is None:
            raise RuntimeError("No exchange-tree conversation is active")
        self.record.open_exchange(exchange_id, message)
        self.invalidate_turn_baseline()
        self.record.nodes[exchange_id].state[TURNS_STATE_KEY] = (
            self._capture_turns(
                CaptureContext(node_id=exchange_id, reason="node_close")
            )
        )
        await self.persist_record_locked()

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
        if self._host.partition is None:
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
            await self.persist_record_locked()
            if created:
                await self._host.send_history_update()

    async def stream_updated(
        self, stream_id: str, entry: TranscriptEntry
    ) -> None:
        if self._host.partition is None:
            return

        async with self.lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            self.record.replace_stream_message(
                exchange_id,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self.persist_record_locked()

    async def stream_finished(
        self,
        stream_id: str,
        status: Literal["ok", "cancelled", "error"],
        error: str | None,
    ) -> None:
        if self._host.partition is None:
            return

        async with self.lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            await self.capture_state_locked(exchange_id, "stream_finish")
            self.record.finish_exchange(exchange_id, status, error)
            await self.persist_record_locked()
            self._stream_exchanges.pop(stream_id, None)
