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


class MessagePayload(TypedDict):
    role: Literal["user", "assistant"]
    content: str
    content_type: ContentType
    id: NotRequired[str]
    icon: NotRequired[str]
    html_deps: NotRequired[list[dict[str, str]]]


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
    html_deps: NotRequired[list[dict[str, str]]]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

# TODO: content should probably be [{"type": "text", "content": "..."}, {"type": "image", ...}]
# in order to support multiple content types...
class ChatMessageDict(TypedDict):
    content: str
    role: Role
    html_deps: NotRequired[list[dict[str, object]]]


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
    content: str | HTML
    role: Role
    html_deps: list[HTMLDependency] | None = None

    @classmethod
    def from_chat_message(cls, message: ChatMessage) -> "StoredMessage":
        return StoredMessage(
            content=message.content,
            role=message.role,
            html_deps=message.html_deps if message.html_deps else None,
        )

