from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Callable

from htmltools import HTMLDependency

from ._chat_types import (
    ChatMessage,
    ContentSegment,
    ContentType,
    SerializedDep,
    StoredSegment,
    StructuredBlock,
    _SegmentBase,
    processed_block_deps,
)

# A stream accumulator entry.
StreamSegment = ContentSegment | StructuredBlock


def segments_content(segments: Sequence[StreamSegment]) -> str:
    return "".join(s.content for s in segments if isinstance(s, ContentSegment))


def segments_deps(segments: Sequence[StreamSegment]) -> list[HTMLDependency]:
    deps: list[HTMLDependency] = []
    for s in segments:
        if isinstance(s, ContentSegment) and s.html_deps:
            deps.extend(s.html_deps)
    return deps


def copy_segments(segments: Sequence[StreamSegment]) -> list[StreamSegment]:
    return [
        ContentSegment(
            content=s.content,
            content_type=s.content_type,
            html_deps=list(s.html_deps) if s.html_deps else None,
        )
        if isinstance(s, ContentSegment)
        else copy.deepcopy(s)
        for s in segments
    ]


def has_mixed_content_types(segments: Sequence[StreamSegment]) -> bool:
    # A structured block has no content_type spelling for replace to restore.
    types = [s.content_type for s in segments if isinstance(s, _SegmentBase)]
    return len(types) != len(segments) or len(set(types)) > 1


def append_to_segments(
    segments: list[ContentSegment] | list[StreamSegment],
    content: str,
    content_type: ContentType,
    deps: list[HTMLDependency] | None = None,
) -> None:
    if not content and deps is None:
        return
    last = segments[-1] if segments else None
    if isinstance(last, ContentSegment) and last.content_type == content_type:
        last.content += content
        if deps:
            if last.html_deps is None:
                last.html_deps = []
            last.html_deps.extend(deps)
    else:
        segments.append(
            ContentSegment(
                content=content,
                content_type=content_type,
                html_deps=list(deps) if deps else None,
            )
        )


def append_chunk_segments(
    segments: list[StreamSegment],
    msg: ChatMessage,
    serialize_deps: Callable[
        [list[HTMLDependency] | None], list[SerializedDep] | None
    ],
) -> None:
    """Absorb one stream chunk: coalesce string content, append blocks in order."""
    append_to_segments(
        segments, msg.content, msg.content_type, msg.html_deps or None
    )
    segments.extend(processed_block_deps(msg, serialize_deps))


def serialize_segments(
    segments: Sequence[StreamSegment],
    serialize_deps: Callable[
        [list[HTMLDependency] | None], list[SerializedDep] | None
    ],
) -> list[StoredSegment | StructuredBlock]:
    # Blocks pass through with session-processed deps already attached.
    return [
        StoredSegment(
            content=seg.content,
            content_type=seg.content_type,
            html_deps=serialize_deps(seg.html_deps or None),
        )
        if isinstance(seg, ContentSegment)
        else seg
        for seg in segments
    ]
