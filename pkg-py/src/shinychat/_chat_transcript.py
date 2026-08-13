from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from ._attachments import Attachment
from ._chat_segments import (
    append_to_segments,
    copy_segments,
    has_mixed_content_types,
)
from ._chat_types import (
    ChatMessage,
    ContentSegment,
    Role,
    StoredMessage,
)

AsyncSend = Callable[[], Awaitable[None]]
ChunkSend = Callable[
    ["StreamCandidate"],
    Awaitable[StoredMessage | None],
]
SettleSend = Callable[
    ["StreamCandidate"],
    Awaitable[StoredMessage],
]
ChangeCallback = Callable[[], None]


@dataclass(frozen=True)
class TranscriptContext:
    generation: int
    stream_id: str | None
    is_root: bool
    previous_checkpoint: tuple[ContentSegment, ...]


@dataclass(frozen=True)
class StreamCandidate:
    role: Role
    segments: tuple[ContentSegment, ...]
    attachments: tuple[Attachment, ...]
    projection: StoredMessage | None
    operation: Literal["append", "replace"]


class ChatTranscript:
    """The server-authoritative store of settled messages and the one active stream.

    All mutations are transactional: the ``send`` callback runs first, and
    internal state only changes once it succeeds. Callers own transforms,
    dependency serialization, and the actual browser send; this component
    only tracks committed messages and the in-flight stream candidate.
    """

    def __init__(self, *, on_change: ChangeCallback | None = None) -> None:
        self._on_change = on_change
        self._messages: tuple[StoredMessage, ...] = ()
        self._active_stream_id: str | None = None
        self._active_role: Role = "assistant"
        self._active_segments: tuple[ContentSegment, ...] = ()
        self._active_attachments: tuple[Attachment, ...] = ()
        self._active_projection: StoredMessage | None = None
        self._checkpoint: tuple[ContentSegment, ...] = ()
        self._generation = 0

    def read(self) -> tuple[StoredMessage, ...]:
        return tuple(
            message.model_copy(deep=True) for message in self._messages
        )

    def is_active(self, stream_id: str) -> bool:
        return self._active_stream_id == stream_id

    @property
    def active_stream_id(self) -> str | None:
        return self._active_stream_id

    @property
    def active_segments(self) -> tuple[ContentSegment, ...]:
        return tuple(copy_segments(list(self._active_segments)))

    @property
    def active_projection(self) -> StoredMessage | None:
        if self._active_projection is None:
            return None
        return self._active_projection.model_copy(deep=True)

    @property
    def generation(self) -> int:
        return self._generation

    def enter_context(self) -> TranscriptContext:
        context = TranscriptContext(
            generation=self._generation,
            stream_id=self._active_stream_id,
            is_root=self._active_stream_id is None,
            previous_checkpoint=self._checkpoint,
        )
        self._checkpoint = self._active_segments
        return context

    def exit_context(self, context: TranscriptContext) -> None:
        if self._generation == context.generation:
            self._checkpoint = context.previous_checkpoint

    async def append(self, message: StoredMessage, *, send: AsyncSend) -> None:
        if self._active_stream_id is not None:
            raise RuntimeError(
                "Cannot append a complete message while a stream is active"
            )

        next_message = message.model_copy(deep=True)
        await send()

        self._messages = (*self._messages, next_message)
        self._notify_change()

    async def start(
        self, message: ChatMessage, *, stream_id: str, send: AsyncSend
    ) -> None:
        if self._active_stream_id is not None:
            raise RuntimeError(
                "Cannot start a stream while another stream is active"
            )

        segments: list[ContentSegment] = []
        append_to_segments(
            segments,
            message.content,
            message.content_type,
            message.html_deps or None,
        )
        attachments = tuple(message.attachments)

        await send()

        self._active_stream_id = stream_id
        self._active_role = message.role
        self._active_segments = tuple(segments)
        self._active_attachments = attachments
        self._active_projection = None

    async def chunk(
        self,
        message: ChatMessage,
        *,
        stream_id: str,
        operation: Literal["append", "replace"],
        send: ChunkSend,
    ) -> None:
        self._assert_active_stream(
            stream_id,
            missing_error="Cannot apply a stream chunk without an active stream",
        )

        if operation == "replace":
            if has_mixed_content_types(list(self._checkpoint)):
                raise ValueError(
                    "Cannot `.replace()` a stream whose checkpoint spans multiple "
                    "content types (e.g. thinking followed by markdown). The replace "
                    "wire action carries a single content type, so a mixed checkpoint "
                    "cannot be restored. Open a `.message_stream_context()` before the "
                    "mixed content to get a clean checkpoint, or use `.append()`."
                )
            staged_segments = copy_segments(list(self._checkpoint))
        else:
            staged_segments = copy_segments(list(self._active_segments))

        append_to_segments(
            staged_segments,
            message.content,
            message.content_type,
            message.html_deps or None,
        )

        candidate = StreamCandidate(
            role=self._active_role,
            segments=tuple(staged_segments),
            attachments=self._active_attachments,
            projection=self._active_projection,
            operation=operation,
        )

        projection = await send(candidate)

        self._active_segments = tuple(staged_segments)
        self._active_projection = projection

    async def settle(self, *, stream_id: str, send: SettleSend) -> None:
        self._assert_active_stream(
            stream_id,
            missing_error="Cannot end a stream without an active stream",
        )

        candidate = StreamCandidate(
            role=self._active_role,
            segments=self._active_segments,
            attachments=self._active_attachments,
            projection=self._active_projection,
            operation="append",
        )

        settled = await send(candidate)

        self._messages = (*self._messages, settled)
        self._active_stream_id = None
        self._active_segments = ()
        self._active_attachments = ()
        self._active_projection = None
        self._notify_change()

    def abort(self, stream_id: str) -> None:
        if self._active_stream_id != stream_id:
            return
        self._active_stream_id = None
        self._active_segments = ()
        self._active_attachments = ()
        self._active_projection = None

    async def clear(self, *, send: AsyncSend) -> None:
        await send()

        self._messages = ()
        self._active_stream_id = None
        self._active_segments = ()
        self._active_attachments = ()
        self._active_projection = None
        self._checkpoint = ()
        self._generation += 1
        self._notify_change()

    async def replace(
        self,
        messages: Sequence[StoredMessage],
        *,
        send: AsyncSend | None = None,
    ) -> None:
        next_messages = tuple(
            message.model_copy(deep=True) for message in messages
        )
        if send is not None:
            await send()

        self._messages = next_messages
        self._notify_change()

    def _assert_active_stream(
        self, stream_id: str, *, missing_error: str
    ) -> None:
        if self._active_stream_id is None:
            raise RuntimeError(missing_error)
        if self._active_stream_id != stream_id:
            raise RuntimeError("Cannot write to a stream that is not active")

    def _notify_change(self) -> None:
        if self._on_change is not None:
            self._on_change()
