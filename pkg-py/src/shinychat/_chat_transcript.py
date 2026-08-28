from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from . import _utils
from ._chat_segments import copy_segments
from ._chat_types import ContentSegment, StoredMessage, StoredSegment

AsyncCommitSend = Callable[[], Awaitable[bool]]
AsyncActionSend = Callable[[], Awaitable[None]]
ChangeCallback = Callable[[], None]
StreamTerminalCallback = Callable[[], None]
StreamStatus = Literal["cancelled", "error"]


@dataclass
class TranscriptEntry:
    """One committed message wire spec."""

    message: StoredMessage
    icon: str | None = None
    status: StreamStatus | None = None
    error: dict[str, str] | None = None
    exchange_id: str | None = None

    def copy(self) -> TranscriptEntry:
        return TranscriptEntry(
            message=self.message.model_copy(deep=True),
            icon=self.icon,
            status=self.status,
            error=dict(self.error) if self.error is not None else None,
            exchange_id=self.exchange_id,
        )


@dataclass
class _InFlightStream:
    id: str
    entry: TranscriptEntry
    source_segments: list[ContentSegment]
    checkpoint: list[ContentSegment]
    owner_task: object | None


class ChatTranscript:
    """Private owner for committed, server-authoritative chat messages."""

    def __init__(
        self,
        *,
        on_change: ChangeCallback | None = None,
        on_stream_terminal: StreamTerminalCallback | None = None,
    ) -> None:
        self._on_change = on_change
        self._on_stream_terminal = on_stream_terminal
        self._entries: tuple[TranscriptEntry, ...] = ()
        self._open_exchange_id: str | None = None
        self._stream: _InFlightStream | None = None
        self._transaction: object | None = None

    def read(self) -> tuple[TranscriptEntry, ...]:
        """Return a defensive projection of the committed transcript."""
        return tuple(entry.copy() for entry in self._entries)

    @property
    def open_exchange_id(self) -> str | None:
        return self._open_exchange_id

    @property
    def active_stream_id(self) -> str | None:
        stream = self._stream
        return stream.id if stream is not None else None

    def stream_is_owned_by(self, owner_task: object | None) -> bool:
        stream = self._require_stream()
        return stream.owner_task is owner_task

    async def append(
        self,
        entry: TranscriptEntry,
        *,
        exchange_id: str | None,
        send: AsyncCommitSend,
        transaction: object | None = None,
    ) -> bool:
        """Send a complete message, then commit its normalized wire spec."""
        transaction, release = self._use_transaction(
            transaction, self._reserve_complete_append
        )
        prepared = entry.copy()
        prepared.exchange_id = exchange_id
        try:
            if not await send():
                return False
            self._entries = (*self._entries, prepared)
            self._notify_change()
            return True
        finally:
            if release:
                self._release_transaction(transaction)

    def record_accepted_input(self, message: StoredMessage) -> str:
        """Commit an accepted optimistic user message and open its exchange."""
        exchange_id = _utils.private_random_id()
        self._entries = (
            *self._entries,
            TranscriptEntry(
                message=message.model_copy(deep=True),
                exchange_id=exchange_id,
            ),
        )
        self._open_exchange_id = exchange_id
        self._notify_change()
        return exchange_id

    async def start_stream(
        self,
        *,
        stream_id: str,
        entry: TranscriptEntry,
        owner_task: object | None,
        exchange_id: str | None,
        send: AsyncCommitSend,
        transaction: object | None = None,
    ) -> bool:
        """Reserve, send, then commit a stream start."""
        transaction, release = self._use_transaction(
            transaction, self._reserve_stream_start
        )
        prepared = entry.copy()
        prepared.exchange_id = exchange_id
        reserved = _InFlightStream(
            id=stream_id,
            entry=prepared,
            source_segments=[],
            checkpoint=[],
            owner_task=owner_task,
        )
        # Reserve before awaiting transport so another stream cannot pass the
        # admission check while this start is in flight.
        self._stream = reserved
        try:
            sent = await send()
            if not sent:
                self._stream = None
                return False
            self._entries = (*self._entries, prepared)
            self._notify_change()
            return True
        except BaseException:
            if self._stream is reserved:
                self._stream = None
            raise
        finally:
            if release:
                self._release_transaction(transaction)

    def stream_segments(self, stream_id: str) -> list[ContentSegment]:
        """Return a defensive source-segment snapshot for an active stream."""
        stream = self._require_stream(stream_id)
        return copy_segments(stream.source_segments)

    def stream_checkpoint(self, stream_id: str) -> list[ContentSegment]:
        """Return a defensive replacement checkpoint for an active stream."""
        stream = self._require_stream(stream_id)
        return copy_segments(stream.checkpoint)

    def set_stream_checkpoint(
        self, stream_id: str, checkpoint: list[ContentSegment]
    ) -> None:
        """Set the replacement checkpoint for an active stream context."""
        stream = self._require_stream(stream_id)
        self._assert_no_transaction(
            "Cannot update a message stream while another transcript operation is active."
        )
        stream.checkpoint = copy_segments(checkpoint)

    async def transition_stream(
        self,
        *,
        stream_id: str,
        source_segments: list[ContentSegment],
        message: StoredMessage,
        operation: Literal["append", "replace"],
        send: AsyncCommitSend,
    ) -> bool:
        """Send a stream chunk, then commit its accumulated source and display."""
        stream, transaction = self._admit_stream_transition(stream_id)
        try:
            prepared_segments = copy_segments(source_segments)
            prepared_message = message.model_copy(deep=True)
            if not await send():
                return False

            stream.source_segments = prepared_segments
            self._apply_stream_message(
                stream.entry, prepared_message, operation
            )
            self._notify_change()
            return True
        finally:
            self._release_transaction(transaction)

    def commit_stream_source(
        self, stream_id: str, source_segments: list[ContentSegment]
    ) -> None:
        """Commit transformed-away source without changing the displayed entry."""
        stream = self._require_stream(stream_id)
        self._assert_no_transaction(
            "Cannot update a message stream while another transcript operation is active."
        )
        stream.source_segments = copy_segments(source_segments)

    async def end_stream(
        self,
        *,
        stream_id: str,
        status: StreamStatus | None,
        error: str | None,
        send: AsyncCommitSend,
        source_segments: list[ContentSegment] | None = None,
        message: StoredMessage | None = None,
        operation: Literal["append", "replace"] = "append",
    ) -> bool:
        """Send a stream end, then commit optional terminal display and status."""
        stream, transaction = self._admit_stream_transition(stream_id)
        try:
            prepared_segments = (
                copy_segments(source_segments)
                if source_segments is not None
                else None
            )
            prepared_message = (
                message.model_copy(deep=True) if message is not None else None
            )
            if not await send():
                self._set_stream_status(
                    stream.entry,
                    status or "error",
                    error or "Could not send message stream end.",
                )
                self._stream = None
                self._notify_change()
                self._notify_stream_terminal()
                return False

            if prepared_segments is not None:
                stream.source_segments = prepared_segments
            if prepared_message is not None:
                self._apply_stream_message(
                    stream.entry, prepared_message, operation
                )
            self._set_stream_status(stream.entry, status, error)
            self._stream = None
            self._notify_change()
            self._notify_stream_terminal()
            return True
        finally:
            self._release_transaction(transaction)

    def abort_stream(
        self,
        stream_id: str,
        *,
        status: StreamStatus,
        error: str | None = None,
    ) -> None:
        """Retain successfully sent stream content after an interrupted end."""
        self._assert_no_transaction(
            "Cannot abort a message stream while another transcript operation is active."
        )
        stream = self._require_stream(stream_id)
        self._set_stream_status(stream.entry, status, error)
        self._stream = None
        self._notify_change()
        self._notify_stream_terminal()

    async def clear(
        self, *, send: AsyncActionSend, transaction: object | None = None
    ) -> None:
        """Send the clear action, then discard the committed transcript."""
        transaction, release = self._use_transaction(
            transaction, self._reserve_clear_or_restore
        )
        retained_from = len(self._entries)
        try:
            await send()
            # Input is already optimistic on the client and remains admissible
            # while a clear transport send is in flight. Keep that new tail.
            retained_entries = self._entries[retained_from:]
            self._entries = retained_entries
            self._open_exchange_id = (
                retained_entries[-1].exchange_id if retained_entries else None
            )
            self._notify_change()
        finally:
            if release:
                self._release_transaction(transaction)

    def replace(self, entries: Sequence[TranscriptEntry]) -> None:
        """Replace the committed transcript after a caller has restored it."""
        self._assert_can_clear_or_restore()
        self._entries = tuple(entry.copy() for entry in entries)
        self._open_exchange_id = None
        self._notify_change()

    def assert_no_active_stream(self) -> None:
        """Reject destructive operations while a stream owns the transcript."""
        if self._stream is not None:
            raise RuntimeError(
                "Cannot clear or restore messages while a message stream is active."
            )

    def assert_can_clear_or_restore(self) -> None:
        """Check whether a destructive mutation can proceed without reserving it."""
        self._assert_can_clear_or_restore()

    def _reserve_complete_append(self) -> object:
        if self._stream is not None:
            raise RuntimeError(
                "Cannot append a complete message while a message stream is active."
            )
        self._assert_no_transaction(
            "Cannot append a complete message while another transcript operation is active."
        )
        return self._reserve_transaction()

    def _reserve_stream_start(self) -> object:
        if self._stream is not None:
            raise RuntimeError(
                "Cannot start a second message stream while a message stream is active."
            )
        self._assert_no_transaction(
            "Cannot start a message stream while another transcript operation is active."
        )
        return self._reserve_transaction()

    def _admit_stream_transition(
        self, stream_id: str
    ) -> tuple[_InFlightStream, object]:
        stream = self._require_stream(stream_id)
        self._assert_no_transaction(
            "Cannot transition a message stream while another transcript operation is active."
        )
        return stream, self._reserve_transaction()

    def _reserve_clear_or_restore(self) -> object:
        self._assert_can_clear_or_restore()
        return self._reserve_transaction()

    def _use_transaction(
        self,
        transaction: object | None,
        reserve: Callable[[], object],
    ) -> tuple[object, bool]:
        if transaction is None:
            return reserve(), True
        if self._transaction is not transaction:
            raise RuntimeError("Transcript admission was not reserved.")
        return transaction, False

    def _assert_can_clear_or_restore(self) -> None:
        self.assert_no_active_stream()
        self._assert_no_transaction(
            "Cannot clear or restore messages while another transcript operation is active."
        )

    def _assert_no_transaction(self, message: str) -> None:
        if self._transaction is not None:
            raise RuntimeError(message)

    def _reserve_transaction(self) -> object:
        transaction = object()
        self._transaction = transaction
        return transaction

    def _release_transaction(self, transaction: object) -> None:
        if self._transaction is transaction:
            self._transaction = None

    def _require_stream(self, stream_id: str | None = None) -> _InFlightStream:
        stream = self._stream
        if stream is None:
            raise RuntimeError("No message stream is active.")
        if stream_id is not None and stream.id != stream_id:
            raise RuntimeError(
                "Cannot transition a message stream other than the active stream."
            )
        return stream

    @staticmethod
    def _apply_stream_message(
        entry: TranscriptEntry,
        message: StoredMessage,
        operation: Literal["append", "replace"],
    ) -> None:
        if operation == "replace":
            prior_deps = entry.message.html_deps or []
            replacement_deps = message.html_deps or []
            merged_deps = [
                *prior_deps,
                *(dep for dep in replacement_deps if dep not in prior_deps),
            ]
            if merged_deps and message.segments:
                for segment in message.segments:
                    segment.html_deps = None
                message.segments[0].html_deps = merged_deps
            entry.message = message
            return

        target = entry.message
        if (
            len(target.segments) == 1
            and target.segments[0].content == ""
            and not target.attachments
        ):
            target.segments = []
        for segment in message.segments:
            if (
                target.segments
                and target.segments[-1].content_type == segment.content_type
                and target.segments[-1].html_deps == segment.html_deps
            ):
                target.segments[-1].content += segment.content
            else:
                target.segments.append(
                    StoredSegment(
                        content=segment.content,
                        content_type=segment.content_type,
                        html_deps=(
                            list(segment.html_deps)
                            if segment.html_deps is not None
                            else None
                        ),
                    )
                )

    @staticmethod
    def _set_stream_status(
        entry: TranscriptEntry,
        status: StreamStatus | None,
        error: str | None,
    ) -> None:
        entry.status = status
        entry.error = (
            {"message": error if error is not None else ""}
            if status == "error"
            else None
        )

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _notify_stream_terminal(self) -> None:
        if self._on_stream_terminal is not None:
            self._on_stream_terminal()
