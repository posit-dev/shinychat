from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from . import _utils
from ._chat_types import StoredMessage

AsyncCommitSend = Callable[[], Awaitable[bool]]
AsyncActionSend = Callable[[], Awaitable[None]]
ChangeCallback = Callable[[], None]


@dataclass
class TranscriptEntry:
    """One committed complete-message wire spec."""

    message: StoredMessage
    icon: str | None = None

    def copy(self) -> TranscriptEntry:
        return TranscriptEntry(
            message=self.message.model_copy(deep=True),
            icon=self.icon,
        )


class ChatTranscript:
    """Private owner for committed, server-authoritative chat messages."""

    def __init__(self, *, on_change: ChangeCallback | None = None) -> None:
        self._on_change = on_change
        self._entries: tuple[TranscriptEntry, ...] = ()
        self._open_exchange_id: str | None = None

    def read(self) -> tuple[TranscriptEntry, ...]:
        """Return a defensive projection of the committed transcript."""
        return tuple(entry.copy() for entry in self._entries)

    @property
    def open_exchange_id(self) -> str | None:
        return self._open_exchange_id

    async def append(
        self, entry: TranscriptEntry, *, send: AsyncCommitSend
    ) -> bool:
        """Send a complete message, then commit its normalized wire spec."""
        prepared = entry.copy()
        if not await send():
            return False
        self._entries = (*self._entries, prepared)
        self._notify_change()
        return True

    def record_accepted_input(self, message: StoredMessage) -> str:
        """Commit an accepted optimistic user message and open its exchange."""
        self._entries = (
            *self._entries,
            TranscriptEntry(message=message.model_copy(deep=True)),
        )
        self._open_exchange_id = _utils.private_random_id()
        self._notify_change()
        return self._open_exchange_id

    async def clear(self, *, send: AsyncActionSend) -> None:
        """Send the clear action, then discard the committed transcript."""
        await send()
        self._entries = ()
        self._open_exchange_id = None
        self._notify_change()

    def replace(self, entries: Sequence[TranscriptEntry]) -> None:
        """Replace the committed transcript after a caller has restored it."""
        self._entries = tuple(entry.copy() for entry in entries)
        self._open_exchange_id = None
        self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()
