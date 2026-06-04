from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterable, Literal, Union

from htmltools import HTML, HTMLDependency, Tag, TagChild, TagList

from ._html_islands import split_html_islands
from ._typing_extensions import NotRequired, TypedDict

Role = Literal["assistant", "user", "system"]

# ---------------------------------------------------------------------------
# Wire-format types (mirrors js/src/transport/types.ts)
# ---------------------------------------------------------------------------

ContentType = Literal["markdown", "html", "text", "thinking"]


class MessagePayloadSegment(TypedDict):
    content: str
    content_type: ContentType


class MessagePayload(TypedDict):
    role: Literal["user", "assistant"]
    segments: list[MessagePayloadSegment]
    id: NotRequired[str]
    icon: NotRequired[str]


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
    greeting: NotRequired[bool]


class UpdateInputAction(TypedDict):
    type: Literal["update_input"]
    value: NotRequired[str]
    placeholder: NotRequired[str]
    submit: NotRequired[bool]
    focus: NotRequired[bool]


class RemoveLoadingAction(TypedDict):
    type: Literal["remove_loading"]


class UpdateCancelAction(TypedDict):
    type: Literal["update_cancel"]
    enable_cancel: bool


class HideToolRequestAction(TypedDict):
    type: Literal["hide_tool_request"]
    requestId: str


class GreetingOptions(TypedDict):
    dismissible: NotRequired[bool]


class GreetingAction(TypedDict):
    type: Literal["greeting"]
    content: str
    content_type: ContentType
    options: GreetingOptions


class GreetingStartAction(TypedDict):
    type: Literal["greeting_start"]
    content: str
    content_type: ContentType
    options: GreetingOptions


class GreetingChunkAction(TypedDict):
    type: Literal["greeting_chunk"]
    content: str
    operation: Literal["append", "replace"]
    content_type: NotRequired[ContentType]


class GreetingEndAction(TypedDict):
    type: Literal["greeting_end"]


class GreetingClearAction(TypedDict):
    type: Literal["greeting_clear"]


ChatAction = Union[
    MessageAction,
    ChunkStartAction,
    ChunkAction,
    ChunkEndAction,
    ClearAction,
    UpdateInputAction,
    RemoveLoadingAction,
    UpdateCancelAction,
    HideToolRequestAction,
    GreetingAction,
    GreetingStartAction,
    GreetingChunkAction,
    GreetingEndAction,
    GreetingClearAction,
]


class ShinyChatEnvelope(TypedDict):
    id: str
    action: ChatAction
    html_deps: NotRequired[list[dict[str, object]]]


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
        content_type: "ContentType | None" = None,
    ):
        self.role: Role = role
        self.content_type: ContentType = (
            content_type if content_type is not None else "markdown"
        )

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
            if content_type is None:
                self.content_type = "html"

        self.content = content
        self.html_deps: list[HTMLDependency] = deps


class ChatGreeting:
    def __init__(
        self,
        content: Union[str, HTML, Tag, TagList, "AsyncIterable[str]"],
        *,
        dismissible: bool = True,
    ):
        self.dismissible = dismissible

        if isinstance(content, AsyncIterable):
            self.content: Union[str, AsyncIterable[str]] = content
            self.content_type: ContentType = "markdown"
            self.html_deps: list[HTMLDependency] = []
            return

        deps: list[HTMLDependency] = []
        content_type: ContentType = "markdown"
        if not isinstance(content, str):
            split = split_html_islands(content)
            ui = TagList(*split).render()
            content, ui_deps = ui["html"], ui["dependencies"]
            deps = deps + ui_deps
            content = f"\n\n{content}\n\n"
            content_type = "html"

        self.content = content
        self.content_type = content_type
        self.html_deps = deps


def chat_greeting(
    content: Union[str, HTML, Tag, TagList, "AsyncIterable[str]"],
    *,
    dismissible: bool = True,
) -> ChatGreeting:
    """
    Create a greeting for a chat UI.

    A greeting is a welcome message displayed at the top of the chat before any
    conversation messages. It can be static (set via :func:`~shinychat.chat_ui`) or
    dynamic (set via :meth:`~shinychat.Chat.set_greeting`).

    Parameters
    ----------
    content
        The greeting content. Can be a markdown string, :class:`~htmltools.HTML`,
        :class:`~htmltools.Tag`, :class:`~htmltools.TagList`, or an
        :class:`~typing.AsyncIterable` of strings (streaming, only valid via
        :meth:`~shinychat.Chat.set_greeting`).
    dismissible
        Whether the greeting can be dismissed when the user sends a message. When
        ``True`` (the default), the greeting is hidden once the user sends their first
        message. Set to ``False`` to keep the greeting visible throughout the
        conversation, which is useful for persistent instructions or navigation.

    Examples
    --------
    Basic greeting:

    ```python
    from shinychat import chat_greeting

    chat_greeting("## Welcome!\\n\\nHow can I help you today?")
    ```

    Non-dismissible greeting that stays visible:

    ```python
    chat_greeting("Please select a topic to get started.", dismissible=False)
    ```

    Greeting with suggestion cards (uses ``<span class="suggestion">``):

    ```python
    chat_greeting(
        "## Welcome!\\n\\n"
        '<span class="suggestion">Summarize this dataset</span>\\n'
        '<span class="suggestion">Show me recent trends</span>'
    )
    ```

    See Also
    --------
    :func:`~shinychat.chat_ui` : Set a static greeting in the UI definition.
    :meth:`~shinychat.Chat.set_greeting` : Set or stream a greeting from the server.
    """
    return ChatGreeting(
        content,
        dismissible=dismissible,
    )


@dataclass
class ContentSegment:
    content: str
    content_type: ContentType
    html_deps: list[HTMLDependency] | None = None


class StoredContentSegment(TypedDict):
    content: str
    content_type: ContentType
    html_deps: NotRequired[list[dict[str, object]]]


class BookmarkMessageDict(TypedDict):
    role: Role
    segments: list[StoredContentSegment]


@dataclass
class StoredMessage:
    role: Role
    segments: list[StoredContentSegment]

    @property
    def content(self) -> str:
        return "".join(
            s["content"] for s in self.segments if s["content_type"] != "thinking"
        )

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
        seg = StoredContentSegment(content=str(message.content), content_type=message.content_type)
        if html_deps:
            seg["html_deps"] = html_deps
        return StoredMessage(role=message.role, segments=[seg])
