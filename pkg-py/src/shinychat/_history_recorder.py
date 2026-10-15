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
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import JsonValue

from ._chat_transcript import TranscriptEntry
from ._chat_types import StoredMessage
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
    from ._history import HistoryController

# Invalidated-turn-baseline sentinel. Canonical turn fingerprints are JSON
# encodings of dicts, so a real fingerprint is never ""; the sentinel is
# therefore never a prefix of a real fingerprint list, which forces
# snapshot mode on the next capture (the escape hatch from delta mode).
# Assign copies of it, never the list itself: reset() clears the current
# baseline in place and must not be able to reach this constant.
_TURN_BASELINE_INVALID: list[str] = [""]


class _ExchangeRecorder:
    """Private v2 capture owner for one history controller session."""

    def __init__(self, controller: HistoryController) -> None:
        self._controller = controller
        self.record: ConversationRecordV2 | None = None
        self._stream_exchanges: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._capture_hooks: dict[str, CaptureHook] = {}
        self._restore_hooks: dict[str, RestoreHook] = {}
        self._rewind_hooks: dict[str, RewindHook] = {}
        self._turn_baseline: list[str] = []
        self._active_id_published_for: ConversationRecordV2 | None = None
        self._register_capture_hook(TURNS_STATE_KEY, self._capture_turns)
        self._register_restore_hook(TURNS_STATE_KEY, self._restore_turns)
        self._register_rewind_hook(TURNS_STATE_KEY, self._restore_turns)

    def _register_capture_hook(self, name: str, hook: CaptureHook) -> None:
        self._capture_hooks[name] = hook

    def _register_restore_hook(self, name: str, hook: RestoreHook) -> None:
        self._restore_hooks[name] = hook

    def _register_rewind_hook(self, name: str, hook: RewindHook) -> None:
        self._rewind_hooks[name] = hook

    @staticmethod
    def _canonical_turns(
        turns: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        # Kept as the recorder-facing name for the capture seam; the
        # implementation lives once in `_history_plan.canonical_turns`.
        return canonical_turns(turns)

    def _set_turn_baseline(self, turns: list[dict[str, Any]]) -> None:
        _, self._turn_baseline = self._canonical_turns(turns)

    def _invalidate_turn_baseline(self) -> None:
        self._turn_baseline = list(_TURN_BASELINE_INVALID)

    def _capture_turns(self, context: CaptureContext) -> StateEntry:
        adapter = self._controller.adapter
        include_system_prompt = adapter_is_chatlas(adapter)
        turns, fingerprints = self._canonical_turns(
            adapter.get_turns_json(include_system_prompt=include_system_prompt)
        )
        is_prefix = (
            len(self._turn_baseline) <= len(fingerprints)
            and self._turn_baseline == fingerprints[: len(self._turn_baseline)]
        )
        if context.reason == "root_close" or not is_prefix:
            mode: Literal["delta", "snapshot"] = "snapshot"
            data = turns
        else:
            mode = "delta"
            data = turns[len(self._turn_baseline) :]

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

    async def _capture_state(self, node_id: str, reason: CaptureReason) -> None:
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
        adapter = self._controller.adapter
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
            id=self._controller._allocate_conversation_id(),
            client_info={
                str(key): str(value)
                for key, value in self._controller.adapter.client_info().items()
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
        self._turn_baseline.clear()
        self._active_id_published_for = None

    @contextmanager
    def suspend_capture(self):
        transcript = self._controller.chat._transcript
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

    async def _persist_record(self) -> None:
        record = self.record
        assert record is not None
        record_id = record.id
        partition = self._controller.partition
        assert partition is not None
        await self._controller.store.put(partition, record)
        if (
            self.record is not record
            or self._controller._active_id_now() != record_id
        ):
            return

        if self._active_id_published_for is not record:
            publisher = getattr(self._controller, "_publish_active_v2_id", None)
            if publisher is not None:
                published = await publisher(record)
            else:
                callback = self._controller.on_active_id_change
                if callback is not None:
                    await callback(record_id)
                published = (
                    self.record is record
                    and self._controller._active_id_now() == record_id
                )
            if published:
                self._active_id_published_for = record

    def _capture_app_state(self) -> None:
        assert self.record is not None
        values: dict[str, Any] = {}
        for callback in self._controller._save_callbacks:
            callback(values)
        self.record.values = values

    async def save_current(self) -> bool:
        async with self._lock:
            return await self.save_current_locked()

    async def save_current_locked(self) -> bool:
        if self.record is None or self._controller.partition is None:
            return False
        self._capture_app_state()
        await self._persist_record()
        return True

    async def response_settled(self) -> bool:
        async with self._lock:
            if self.record is None or self._controller.partition is None:
                return False
            self._capture_app_state()
            self.record.response_count += 1
            await self._persist_record()
            return True

    async def rename_active_locked(self, conv_id: str, title: str) -> bool:
        if (
            self.record is None
            or self.record.id != conv_id
            or self._controller.partition is None
        ):
            return False
        self.record.title = title
        self.record.title_source = "user"
        await self._persist_record()
        return True

    async def bookmark_pointer(
        self, record: ConversationRecordV2 | None = None
    ) -> tuple[str, str] | None:
        """Return one atomic pointer snapshot for a live v2 record."""
        async with self._lock:
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
        async with self._lock:
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
                await self._persist_record()
            except BaseException:
                record.bookmark_state_id = old_state_id
                raise
            return True, old_state_id if old_state_id != state_id else None

    def mark_active_id_published(self, record: ConversationRecordV2) -> None:
        if (
            self.record is record
            and self._controller._active_id_now() == record.id
        ):
            self._active_id_published_for = record

    def _close_root_if_inactive(self) -> None:
        assert self.record is not None
        root_id = "n_0000"
        root = self.record.nodes.get(root_id)
        if (
            root is not None
            and root.status == "pending"
            and root_id not in self._stream_exchanges.values()
        ):
            self.record.finish_exchange(root_id, "ok", None)

    async def accepted_input(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        controller = self._controller
        if controller.partition is None:
            return

        async with self._lock:
            created = False
            if self.record is None:
                title = fallback_title_from_text(message.content)
                self.record = await self._new_record(title=title)
                created = True
            root_id = "n_0000"
            is_first_input = not any(
                node.input is not None for node in self.record.nodes.values()
            )
            if is_first_input:
                await self._capture_state(root_id, "root_close")
                self._close_root_if_inactive()
            else:
                active_leaf = self.record.active_leaf
                assert active_leaf is not None
                await self._capture_state(active_leaf, "node_close")
            self.record.open_exchange(exchange_id, message)
            await self._persist_record()
            send_history_update = getattr(
                controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def _accepted_resubmit_input_locked(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        """Open a degraded-resubmit sibling without closing its shared parent."""
        if self._controller.partition is None:
            raise RuntimeError("HistoryController not initialized")

        if self.record is None:
            raise RuntimeError("No exchange-tree conversation is active")
        self.record.open_exchange(exchange_id, message)
        self._invalidate_turn_baseline()
        self.record.nodes[exchange_id].state[TURNS_STATE_KEY] = (
            self._capture_turns(
                CaptureContext(node_id=exchange_id, reason="node_close")
            )
        )
        await self._persist_record()

    async def message_committed(
        self, exchange_id: str | None, entry: TranscriptEntry
    ) -> None:
        if entry.message.role not in ("user", "assistant"):
            return
        if self._controller.partition is None:
            return

        async with self._lock:
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            self.record.append_message(
                target,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()
            send_history_update = getattr(
                self._controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def stream_started(
        self,
        stream_id: str,
        exchange_id: str | None,
        entry: TranscriptEntry,
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            self._stream_exchanges[stream_id] = target
            self.record.append_stream_message(
                target,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()
            send_history_update = getattr(
                self._controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def stream_updated(
        self, stream_id: str, entry: TranscriptEntry
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            self.record.replace_stream_message(
                exchange_id,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()

    async def stream_finished(
        self,
        stream_id: str,
        status: Literal["ok", "cancelled", "error"],
        error: str | None,
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            await self._capture_state(exchange_id, "stream_finish")
            self.record.finish_exchange(exchange_id, status, error)
            await self._persist_record()
            self._stream_exchanges.pop(stream_id, None)
