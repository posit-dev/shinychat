from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from htmltools import HTML, HTMLDependency, TagChild, TagList

from ._html_islands import split_html_islands
from ._typing_extensions import NotRequired, TypedDict

Role = Literal["assistant", "user", "system"]

# ---------------------------------------------------------------------------
# Wire-format types (mirrors js/src/transport/types.ts)
# ---------------------------------------------------------------------------

ContentType = Literal["markdown", "html", "text"]


class MessagePayloadSegment(TypedDict):
    content: str
    content_type: ContentType


class MessagePayload(TypedDict):
    role: Literal["user", "assistant"]
    segments: list[MessagePayloadSegment]
    id: NotRequired[str]
    icon: NotRequired[str]
    html_deps: NotRequired[list[dict[str, object]]]


class MessageAction(TypedDict):
    type: Literal["message"]
    message: MessagePayload


class ChunkStartAction(TypedDict):
    type: Literal["chunk_start"]
    message: MessagePayload


class ChunkAction(TypedDict):
    type: Literal["chunk"]
    content: str
    operation: Literal["append", "replace"]
    content_type: NotRequired[ContentType]


class ChunkEndAction(TypedDict):
    type: Literal["chunk_end"]


class ClearAction(TypedDict):
    type: Literal["clear"]


class UpdateInputAction(TypedDict):
    type: Literal["update_input"]
    value: NotRequired[str]
    placeholder: NotRequired[str]
    submit: NotRequired[bool]
    focus: NotRequired[bool]


class RemoveLoadingAction(TypedDict):
    type: Literal["remove_loading"]


class HideToolRequestAction(TypedDict):
    type: Literal["hide_tool_request"]
    requestId: str


ChatAction = Union[
    MessageAction,
    ChunkStartAction,
    ChunkAction,
    ChunkEndAction,
    ClearAction,
    UpdateInputAction,
    RemoveLoadingAction,
    HideToolRequestAction,
]


class ShinyChatEnvelope(TypedDict):
    id: str
    action: ChatAction
    html_deps: NotRequired[list[dict[str, object]]]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class ChatMessageDict(TypedDict):
    content: str
    role: Role
    html_deps: NotRequired[list[dict[str, object]]]


class BookmarkMessageDict(TypedDict):
    role: Role
    segments: list[StoredContentSegment]


class ChatMessage:
    def __init__(
        self,
        content: TagChild,
        role: Role = "assistant",
    ):
        self.role: Role = role

        # content _can_ be a TagChild, but it's most likely just a string (of
        # markdown), so only process it if it's not a string.
        deps: list[HTMLDependency] = []
        if not isinstance(content, str):
            split = split_html_islands(content)
            ui = TagList(*split).render()
            content, ui_deps = ui["html"], ui["dependencies"]
            deps = deps + ui_deps
            # Surround with blank lines so the markdown parser treats
            # block-level custom elements correctly.
            content = f"\n\n{content}\n\n"

        self.content = content
        self.html_deps: list[HTMLDependency] = deps


@dataclass
class StoredMessage:
    role: Role
    segments: list[StoredContentSegment]

    @property
    def content(self) -> str:
        return "".join(s["content"] for s in self.segments)

    @property
    def html_deps(self) -> list[dict[str, object]] | None:
        deps = [d for s in self.segments for d in (s.get("html_deps") or [])]
        return deps or None

    @classmethod
    def from_chat_message(
        cls,
        message: ChatMessage,
        html_deps: list[dict[str, object]] | None = None,
    ) -> "StoredMessage":
        content_type: ContentType = "html" if isinstance(message.content, HTML) else "markdown"
        seg = StoredContentSegment(content=str(message.content), content_type=content_type)
        if html_deps:
            seg["html_deps"] = html_deps
        return StoredMessage(role=message.role, segments=[seg])


@dataclass
class ContentSegment:
    content: str
    content_type: ContentType
    html_deps: list[HTMLDependency] | None = None


class StoredContentSegment(TypedDict):
    content: str
    content_type: ContentType
    html_deps: NotRequired[list[dict[str, object]]]
