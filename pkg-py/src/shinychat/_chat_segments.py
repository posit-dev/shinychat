from __future__ import annotations

from htmltools import HTMLDependency

from ._chat_types import ContentSegment, ContentType


def segments_content(segments: list[ContentSegment]) -> str:
    return "".join(s.content for s in segments)


def segments_deps(segments: list[ContentSegment]) -> list[HTMLDependency]:
    deps: list[HTMLDependency] = []
    for s in segments:
        if s.html_deps:
            deps.extend(s.html_deps)
    return deps


def copy_segments(segments: list[ContentSegment]) -> list[ContentSegment]:
    return [
        ContentSegment(
            content=s.content,
            content_type=s.content_type,
            html_deps=list(s.html_deps) if s.html_deps else None,
        )
        for s in segments
    ]


def has_mixed_content_types(segments: list[ContentSegment]) -> bool:
    if not segments:
        return False
    first_content_type = segments[0].content_type
    return any(seg.content_type != first_content_type for seg in segments[1:])


def append_to_segments(
    segments: list[ContentSegment],
    content: str,
    content_type: ContentType,
    deps: list[HTMLDependency] | None = None,
) -> None:
    if not content and deps is None:
        return
    if segments and segments[-1].content_type == content_type:
        segments[-1].content += content
        if deps:
            if segments[-1].html_deps is None:
                segments[-1].html_deps = []
            segments[-1].html_deps.extend(deps)
    else:
        segments.append(
            ContentSegment(
                content=content,
                content_type=content_type,
                html_deps=list(deps) if deps else None,
            )
        )
