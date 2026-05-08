from __future__ import annotations

from typing import Callable

from htmltools import HTMLDependency

from ._chat_types import ContentSegment, ContentType, StoredContentSegment


def segments_content(segments: list[ContentSegment]) -> str:
    return "".join(s.content for s in segments)


def segments_deps(segments: list[ContentSegment]) -> list[HTMLDependency]:
    deps: list[HTMLDependency] = []
    for s in segments:
        if s.html_deps:
            deps.extend(s.html_deps)
    return deps


def append_to_segments(
    segments: list[ContentSegment],
    content: str,
    content_type: ContentType,
    deps: list[HTMLDependency] | None = None,
) -> None:
    if not content and not deps:
        return
    if segments and segments[-1].content_type == content_type:
        segments[-1].content += content
        if deps:
            if segments[-1].html_deps is None:
                segments[-1].html_deps = []
            segments[-1].html_deps.extend(deps)
    else:
        deps_copy = list(deps) if deps else None
        segments.append(ContentSegment(content, content_type, deps_copy))


def serialize_segments(
    segments: list[ContentSegment],
    serialize_deps: Callable[[list[HTMLDependency] | None], list[dict[str, object]] | None],
) -> list[StoredContentSegment]:
    result: list[StoredContentSegment] = []
    for seg in segments:
        stored_seg = StoredContentSegment(
            content=seg.content,
            content_type=seg.content_type,
        )
        serialized_deps = serialize_deps(seg.html_deps)
        if serialized_deps:
            stored_seg["html_deps"] = serialized_deps
        result.append(stored_seg)
    return result
