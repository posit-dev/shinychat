from __future__ import annotations

import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    Callable,
    Literal,
    Union,
    cast,
)

from htmltools import HTML, HTMLDependency, Tag, TagChild, TagList
from pydantic import BaseModel

if TYPE_CHECKING:
    from shiny.session import Session

from ._attachments import Attachment
from ._html_islands import (
    IslandBlockPart,
    derive_island_parts,
)
from ._typing_extensions import NotRequired, TypedDict, TypeGuard
from ._utils_types import DEPRECATED, DEPRECATED_TYPE, MISSING, MISSING_TYPE

Role = Literal["assistant", "user", "system"]

SerializedDep = dict[str, object]

# ---------------------------------------------------------------------------
# Wire-format types (mirrors js/src/transport/types.ts)
# ---------------------------------------------------------------------------

ContentType = Literal["markdown", "html", "text", "thinking"]


class StringSegment(TypedDict):
    content: str
    content_type: ContentType


class ToolRequestBlock(TypedDict):
    """A tool call request from the server.

    The client shows a ``running`` call when a request has no matching
    result.
    """

    type: Literal["tool_request"]
    version: Literal[1]
    request_id: str
    tool_name: str
    title: NotRequired[str]
    icon: NotRequired[str]
    intent: NotRequired[str]
    arguments: NotRequired[str]
    grouping: NotRequired[Literal["none", "tool", "all"]]


class ToolResultBlock(TypedDict):
    """The result of a completed tool call.

    Paired with a preceding ``tool_request`` by ``request_id``.
    """

    type: Literal["tool_result"]
    version: Literal[1]
    request_id: str
    tool_name: str
    status: Literal["success", "error"]
    value: NotRequired[str]
    value_type: NotRequired[
        Literal["html", "markdown", "text", "code", "content_extra"]
    ]
    request_call: NotRequired[str]
    title: NotRequired[str]
    icon: NotRequired[str]
    intent: NotRequired[str]
    label: NotRequired[str]
    value_preview: NotRequired[str]
    grouping: NotRequired[Literal["none", "tool", "all"]]
    show_request: NotRequired[bool]
    expanded: NotRequired[bool]
    open_style: NotRequired[Literal["minimal", "framed"]]
    full_screen: NotRequired[bool]
    custom_display: NotRequired[bool]
    footer: NotRequired[str]


class WebSearchSource(TypedDict):
    """One source in a ``web_search_results`` block.

    ``url`` is required. ``title`` and ``domain`` are optional display
    hints.
    """

    url: str
    title: NotRequired[str]
    domain: NotRequired[str]


class WebSearchBlock(TypedDict):
    """A web search query.

    Consecutive ``web_*`` blocks group into one ``web_activity`` block on
    the client.
    """

    type: Literal["web_search"]
    version: Literal[1]
    query: str
    # Provider search id, when the provider supplies one.
    id: NotRequired[str]


class WebSearchResultsBlock(TypedDict):
    """Results for a preceding ``web_search`` block."""

    type: Literal["web_search_results"]
    version: Literal[1]
    sources: list[WebSearchSource]
    # `id` of the `web_search` these results answer, when known.
    search_id: NotRequired[str]


class WebSearchCitationsBlock(TypedDict):
    """Citations for the most recent ``web_search`` block.

    The client merges ``sources`` into the search and renders nothing for
    the block itself. Citations appear only while no provider results are
    attached.
    """

    type: Literal["web_search_citations"]
    version: Literal[1]
    sources: list[WebSearchSource]


class WebFetchBlock(TypedDict):
    """A fetched URL from a web search session."""

    type: Literal["web_fetch"]
    version: Literal[1]
    url: str
    status: NotRequired[Literal["success", "error"]]


class HtmlBlock(TypedDict):
    """Trusted HTML rendered through the RawHTML sink.

    The thinking-tag and fence state machine operates only on string
    content, so this block passes through untouched.
    """

    type: Literal["html_block"]
    version: Literal[1]
    content: str
    html_deps: NotRequired[list[SerializedDep]]


def html_block(
    html: str, html_deps: list[SerializedDep] | None = None
) -> HtmlBlock:
    block: HtmlBlock = {"type": "html_block", "version": 1, "content": html}
    if html_deps:
        block["html_deps"] = html_deps
    return block


def content_to_segments(
    content: TagChild, content_type: ContentType | None
) -> tuple[
    list[ContentSegment | StructuredBlock],
    ContentType,
    list[HTMLDependency],
    dict[int, list[HTMLDependency]],
]:
    # TagList/tag content is an HTML container: bare strings inside it are
    # escaped text nodes (via TagList().render()), NOT markdown. To mix
    # markdown and UI in one message, use `parts`.
    # The shared derive_island_parts() partition turns non-React runs into
    # html_block structured blocks; bare React elements are rendered and
    # concatenated as residual string segments.
    island_parts = derive_island_parts(content)
    resolved_type: ContentType = (
        content_type
        if content_type is not None
        else ("html" if island_parts else "markdown")
    )
    deps: list[HTMLDependency] = []
    block_html_deps: dict[int, list[HTMLDependency]] = {}
    segments: list[ContentSegment | StructuredBlock] = []
    block_idx = 0
    for part in island_parts:
        deps.extend(part.deps)
        if isinstance(part, IslandBlockPart):
            segments.append(
                html_block(
                    part.html,
                    [d.as_dict() for d in part.deps] if part.deps else None,
                )
            )
            if part.deps:
                # The raw as_dict() copy on the block is the no-session
                # fallback; the send path overwrites it with session-processed
                # deps.
                block_html_deps[block_idx] = part.deps
            block_idx += 1
        else:
            segments.append(
                ContentSegment(content=part.html, content_type=resolved_type)
            )
    return segments, resolved_type, deps, block_html_deps


# The union of typed blocks carried in `MessagePayload.segments` (outside a
# stream) or via a `block_insert` action (mid-stream).
StructuredBlock = Union[
    ToolRequestBlock,
    ToolResultBlock,
    WebSearchBlock,
    WebSearchResultsBlock,
    WebSearchCitationsBlock,
    WebFetchBlock,
    HtmlBlock,
]

# Structured blocks the markdown-stream wire supports: `html_block` and
# the web_* family. Tool blocks are out of scope for streams.
StreamBlock = Union[
    WebSearchBlock,
    WebSearchResultsBlock,
    WebSearchCitationsBlock,
    WebFetchBlock,
    HtmlBlock,
]

# One entry of `MessagePayload.segments`: a string segment or a structured
# block (discriminated by the presence of `type`).
SegmentPayload = Union[StringSegment, StructuredBlock]


def is_structured_segment(
    seg: SegmentPayload,
) -> TypeGuard[StructuredBlock]:
    return isinstance(seg, dict) and "type" in seg


class MessagePayload(TypedDict):
    role: Literal["user", "assistant"]
    segments: list[SegmentPayload]
    attachments: NotRequired[list[dict[str, Any]]]
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


class BlockInsertAction(TypedDict):
    """Delivers one structured block while a message streams.

    The client appends it to the in-flight message's block list.
    """

    type: Literal["block_insert"]
    block: StructuredBlock


class ClearAction(TypedDict):
    type: Literal["clear"]
    greeting: NotRequired[bool]


class UpdateInputAction(TypedDict):
    type: Literal["update_input"]
    value: NotRequired[str]
    placeholder: NotRequired[str]
    submit: NotRequired[bool]
    focus: NotRequired[bool]
    attachments: NotRequired[list[dict[str, Any]]]
    attachment_mode: NotRequired[Literal["append", "set"]]


class RemoveLoadingAction(TypedDict):
    type: Literal["remove_loading"]


class UpdateCancelAction(TypedDict):
    type: Literal["update_cancel"]
    enable_cancel: bool


class UpdateUploadAction(TypedDict):
    type: Literal["update_upload"]
    enable_upload: bool


class GreetingOptions(TypedDict):
    persistent: NotRequired[bool]


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


class SlashCommandDef(TypedDict):
    name: str
    description: str
    echo: bool


class UpdateSlashCommandsAction(TypedDict):
    type: Literal["update_slash_commands"]
    commands: list[SlashCommandDef]


class DrawerShowAction(TypedDict):
    type: Literal["drawer_show"]
    content: NotRequired[str]
    title: NotRequired[str]


class DrawerHideAction(TypedDict):
    type: Literal["drawer_hide"]


class DrawerToggleAction(TypedDict):
    type: Literal["drawer_toggle"]


class DrawerUpdateAction(TypedDict):
    type: Literal["drawer_update"]
    content: NotRequired[str]
    title: NotRequired[str]


class HistoryUpdateAction(TypedDict):
    type: Literal["history_update"]
    enabled: bool
    conversations: list[dict[str, Any]]  # ConversationMeta dumps
    active_id: str | None


class HistoryNavigateAction(TypedDict):
    type: Literal["history_navigate"]
    url: str | None
    active_id: str | None
    reload: NotRequired[bool]


class UpdateSiblingsAction(TypedDict):
    type: Literal["update_siblings"]
    data: dict[int, dict[str, int]]


ChatAction = Union[
    MessageAction,
    ChunkStartAction,
    ChunkAction,
    ChunkEndAction,
    BlockInsertAction,
    ClearAction,
    UpdateInputAction,
    RemoveLoadingAction,
    UpdateCancelAction,
    UpdateUploadAction,
    GreetingAction,
    GreetingStartAction,
    GreetingChunkAction,
    GreetingEndAction,
    GreetingClearAction,
    UpdateSlashCommandsAction,
    DrawerShowAction,
    DrawerHideAction,
    DrawerToggleAction,
    DrawerUpdateAction,
    HistoryUpdateAction,
    HistoryNavigateAction,
    UpdateSiblingsAction,
]


class ShinyChatEnvelope(TypedDict):
    id: str
    action: ChatAction
    html_deps: NotRequired[list[SerializedDep]]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


# TODO: content should probably be [{"type": "text", "content": "..."}, {"type": "image", ...}]
# in order to support multiple content types...
class ChatMessageDict(TypedDict):
    content: str
    role: Role
    html_deps: NotRequired[list[SerializedDep]]
    attachments: NotRequired[list[Attachment]]


class ChatMessage:
    """A chat message with ordered content segments.

    The message stores its content as ``segments``: string segments
    interleaved with structured blocks. This is the same shape the wire
    format and :class:`StoredMessage` use. The ``content``, ``blocks``,
    and ``parts`` properties are read-only views over those segments.

    Pass ``content`` for a simple string or HTML tag, ``parts`` to
    interleave strings and blocks in one message, or ``blocks`` to attach
    structured blocks after a string. These three inputs are mutually
    exclusive: ``parts`` raises when combined with ``blocks`` or
    non-empty ``content``.

    Parameters
    ----------
    content
        The message content. A plain string is markdown. An htmltools
        tag, :class:`~htmltools.TagList`, or :class:`~htmltools.HTML` is
        trusted HTML. Tag content is an HTML container: bare strings
        inside it are escaped text, not markdown. To mix markdown and
        HTML in one message, use ``parts`` instead.
    role
        The message role. One of ``"assistant"``, ``"user"``, or
        ``"system"``. Defaults to ``"assistant"``.
    content_type
        The content type for string segments. One of ``"markdown"``,
        ``"html"``, ``"text"``, or ``"thinking"``. When ``content`` is a
        string, defaults to ``"markdown"``. When ``content`` is a tag or
        TagList, defaults to ``"html"``. When ``parts`` is passed,
        applies to every string part in the list.
    attachments
        Files attached to the message. Each item is an
        :class:`~shinychat.Attachment` or a dict that validates as one.
    blocks
        Structured blocks to append after the content. Cannot be
        combined with ``parts``.
    parts
        An ordered list of bare strings and structured blocks. Strings
        become segments stamped with ``content_type``. Blocks pass
        through in order. Cannot be combined with ``blocks`` or
        non-empty ``content``.
    """

    def __init__(
        self,
        content: TagChild,
        role: Role = "assistant",
        content_type: "ContentType | None" = None,
        attachments: "list[Attachment] | None" = None,
        blocks: "list[StructuredBlock] | None" = None,
        parts: "list[str | StructuredBlock] | None" = None,
    ):
        self.role: Role = role
        self.attachments: list[Attachment] = [
            Attachment.model_validate(a) if isinstance(a, dict) else a
            for a in (attachments or [])
        ]
        # Raw HTMLDependency objects per block index, parallel to the block
        # entries of `segments`. No session at construction time, so deps are
        # stashed here for session-processing at send/persist time.
        self._block_html_deps: dict[int, list[HTMLDependency]] = {}

        # Structured blocks travel as typed segments or `block_insert`
        # actions, never as markup in `content`.
        supplied_blocks: list[StructuredBlock] = list(blocks) if blocks else []

        resolved_type: ContentType
        deps: list[HTMLDependency] = []
        segments: list[ContentSegment | StructuredBlock]

        if parts is not None:
            if supplied_blocks:
                raise ValueError(
                    "`parts` and `blocks` are mutually exclusive: `parts` is "
                    "the ordered segment list and already carries its blocks."
                )
            if not isinstance(content, str) or content:
                raise ValueError(
                    "`parts` cannot be combined with `content`: the segment "
                    "list is the complete content spelling. Pass "
                    "`content=''`."
                )
            resolved_type = (
                content_type if content_type is not None else "markdown"
            )
            segments = self._parts_to_segments(parts, resolved_type)
        elif isinstance(content, str):
            resolved_type = (
                content_type if content_type is not None else "markdown"
            )
            segments = [
                ContentSegment(content=content, content_type=resolved_type),
                *supplied_blocks,
            ]
        else:
            segments, resolved_type, deps, block_html_deps = (
                content_to_segments(content, content_type)
            )
            self._block_html_deps.update(block_html_deps)
            # Supplied blocks trail the content-derived segments, preserving
            # prior flat-layout semantics.
            segments.extend(supplied_blocks)

        self.content_type: ContentType = resolved_type
        self.segments: list[ContentSegment | StructuredBlock] = segments
        self.html_deps: list[HTMLDependency] = deps

    @staticmethod
    def _parts_to_segments(
        parts: list[str | StructuredBlock], content_type: ContentType
    ) -> list[ContentSegment | StructuredBlock]:
        # Bare strings become segments stamped with the message content_type;
        # blocks pass through in order. Adjacent markdown strings join with a
        # paragraph break (direct concatenation is unsafe at a markdown seam);
        # other content types concatenate verbatim.
        segments: list[ContentSegment | StructuredBlock] = []
        for part in parts:
            if isinstance(part, str):
                last = segments[-1] if segments else None
                if isinstance(last, ContentSegment):
                    last.content += (
                        "\n\n" + part if content_type == "markdown" else part
                    )
                else:
                    segments.append(
                        ContentSegment(content=part, content_type=content_type)
                    )
            else:
                segments.append(part)
        return segments

    @property
    def content(self) -> str:
        """The string content of the message, joined from its string segments."""
        return "".join(
            s.content for s in self.segments if isinstance(s, ContentSegment)
        )

    @content.setter
    def content(self, value: str) -> None:
        # Replaces the string runs with a single segment stamped with the
        # message content_type; blocks are kept, trailing (flat layout).
        self.segments = [
            ContentSegment(content=value, content_type=self.content_type),
            *[s for s in self.segments if isinstance(s, dict)],
        ]

    @property
    def blocks(self) -> list[StructuredBlock]:
        """The structured blocks in the message, in content order."""
        return [s for s in self.segments if isinstance(s, dict)]

    @property
    def parts(self) -> list[str | StructuredBlock] | None:
        """The segment list as bare strings interleaved with blocks.

        ``None`` when the message has at most one segment.
        """
        if len(self.segments) <= 1:
            return None
        return [
            s.content if isinstance(s, ContentSegment) else s
            for s in self.segments
        ]

    @parts.setter
    def parts(self, value: "list[str | StructuredBlock] | None") -> None:
        if value is None:
            # Collapse to flat layout — the same shape the content setter
            # leaves (one string segment, blocks trailing).
            self.content = self.content
        else:
            if self.blocks:
                raise ValueError(
                    "`parts` cannot be set on a message with `blocks`: the "
                    "segment list is the complete content spelling and "
                    "setting it would discard the blocks."
                )
            self.segments = self._parts_to_segments(value, self.content_type)


class ChatGreeting:
    def __init__(
        self,
        content: Union[str, HTML, Tag, TagList, "AsyncIterable[str]"],
        *,
        persistent: "bool | MISSING_TYPE" = MISSING,
        dismissible: DEPRECATED_TYPE = DEPRECATED,
    ):
        if isinstance(persistent, MISSING_TYPE):
            if not isinstance(dismissible, DEPRECATED_TYPE):
                warnings.warn(
                    "The `dismissible` parameter is deprecated. "
                    "Use `persistent` (with inverted value) instead. "
                    "`dismissible=False` is equivalent to `persistent=True`.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                persistent = not dismissible
            else:
                persistent = False

        self.persistent = persistent

        if isinstance(content, AsyncIterable):
            self.content: Union[str, AsyncIterable[str]] = content
            self.content_type: ContentType = "markdown"
            self.html_deps: list[HTMLDependency] = []
            return

        deps: list[HTMLDependency] = []
        content_type: ContentType = "markdown"
        if not isinstance(content, str):
            # The greeting payload is a single string with no blocks channel.
            # TagList().render() escapes bare strings (safe under the
            # client's innerHTML). Mixed markdown and UI greetings need a
            # segments channel (follow-up: shinychat#2dzc).
            ui = TagList(content).render()
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
    persistent: "bool | MISSING_TYPE" = MISSING,
    dismissible: DEPRECATED_TYPE = DEPRECATED,
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
    persistent
        Whether the greeting stays visible after the user sends a message. When
        ``False`` (the default), the greeting is hidden once the user sends their first
        message. Set to ``True`` to keep the greeting visible throughout the
        conversation, which is useful for persistent instructions or navigation.

    Examples
    --------
    Basic greeting:

    ```python
    from shinychat import chat_greeting

    chat_greeting("## Welcome!\\n\\nHow can I help you today?")
    ```

    Persistent greeting that stays visible:

    ```python
    chat_greeting("Please select a topic to get started.", persistent=True)
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
    if isinstance(persistent, MISSING_TYPE):
        if not isinstance(dismissible, DEPRECATED_TYPE):
            warnings.warn(
                "The `dismissible` parameter is deprecated. "
                "Use `persistent` (with inverted value) instead. "
                "`dismissible=False` is equivalent to `persistent=True`.",
                DeprecationWarning,
                stacklevel=2,
            )
            persistent = not dismissible
        else:
            persistent = False

    return ChatGreeting(
        content,
        persistent=persistent,
    )


class _SegmentBase(BaseModel):
    content: str
    content_type: ContentType

    def __str__(self) -> str:
        return self.stringify(self.content, self.content_type)

    @staticmethod
    def stringify(content: str, content_type: ContentType) -> str:
        if content_type == "thinking":
            return f"<thinking>\n{content}\n</thinking>\n\n"
        return content


class ContentSegment(_SegmentBase):
    model_config = {"arbitrary_types_allowed": True}

    html_deps: list[HTMLDependency] | None = None


class StoredSegment(_SegmentBase):
    html_deps: list[SerializedDep] | None = None


class StoredMessage(BaseModel):
    role: Role
    # Interleaved in content order, mirroring ChatMessage.segments and the
    # wire format: StoredSegment entries for strings, StructuredBlock dicts
    # (distinguished by a "type" key) for blocks.
    segments: list[StoredSegment | StructuredBlock]
    attachments: list[Attachment] = []

    @property
    def content(self) -> str:
        return "".join(
            StoredSegment.stringify(s.content, s.content_type)
            for s in self.segments
            if isinstance(s, StoredSegment)
        )

    @property
    def blocks(self) -> list[StructuredBlock]:
        """The structured blocks in the message, in content order."""
        return [s for s in self.segments if isinstance(s, dict)]

    @property
    def html_deps(self) -> list[SerializedDep] | None:
        deps: list[SerializedDep] = []
        for s in self.segments:
            if isinstance(s, StoredSegment) and s.html_deps:
                deps.extend(s.html_deps)
        return deps or None

    def wire_segments(self) -> list[SegmentPayload]:
        return [
            {"content": s.content, "content_type": s.content_type}
            if isinstance(s, StoredSegment)
            else s
            for s in self.segments
        ]

    @classmethod
    def from_chat_message(
        cls,
        message: ChatMessage,
        html_deps: list[SerializedDep] | None = None,
    ) -> StoredMessage:
        segments: list[StoredSegment | StructuredBlock] = [
            StoredSegment(content=seg.content, content_type=seg.content_type)
            if isinstance(seg, ContentSegment)
            else seg
            for seg in message.segments
        ]
        if not any(isinstance(s, StoredSegment) for s in segments):
            # The wire always carries at least one string segment, even for
            # a blocks-only message.
            segments.insert(
                0,
                StoredSegment(content="", content_type=message.content_type),
            )
        first = next(s for s in segments if isinstance(s, StoredSegment))
        first.html_deps = html_deps
        return cls(
            role=message.role,
            segments=segments,
            attachments=message.attachments,
        )


def serialize_html_deps(
    deps: list[HTMLDependency] | None,
    session: Session | None,
) -> list[SerializedDep] | None:
    """Serialize HTML dependencies through the session's ``_process_ui``.

    Returns ``None`` when there is no session. Callers then keep any raw
    ``as_dict()`` fallback already present on the block.
    """
    if not deps:
        return None
    if session is None:
        return None
    processed = session._process_ui(TagList(*deps))
    return cast(list[SerializedDep], processed["deps"])


def _assemble_stored_message(
    message: ChatMessage,
    serialize_deps: "Callable[[list[HTMLDependency] | None], list[SerializedDep] | None]",
) -> StoredMessage:
    """Assemble a :class:`StoredMessage`, session-processing html deps.

    Overwrites each block's raw ``as_dict()`` ``html_deps`` with the
    session-processed form (see :func:`serialize_html_deps`).
    """
    html_deps = serialize_deps(message.html_deps)
    stored = StoredMessage.from_chat_message(message, html_deps=html_deps)
    for idx, dep_objs in message._block_html_deps.items():
        if idx < len(stored.blocks):
            processed = serialize_deps(dep_objs)
            block = stored.blocks[idx]
            if "html_deps" in block:
                if processed is not None:
                    block["html_deps"] = processed
                # No session: keep the raw as_dict() fallback already on the
                # block.
    return stored


def as_stored_message(
    message: ChatMessage, session: Session | None
) -> StoredMessage:
    """Assemble a :class:`StoredMessage` from a :class:`ChatMessage`.

    Session-processes message-level and per-block html deps through
    ``session._process_ui``.
    """
    return _assemble_stored_message(
        message, lambda deps: serialize_html_deps(deps, session)
    )


def initial_message_payload(
    message: ChatMessage,
) -> "tuple[dict[str, Any], list[HTMLDependency]]":
    """Build the ``data-initial-messages`` JSON entry for one message.

    No session exists at UI render time, so the payload omits every
    ``html_deps`` field. The raw :class:`~htmltools.HTMLDependency` objects
    are returned separately for the caller to attach to the container tag.

    The entry shape matches the ``message`` wire action's payload:
    ``{"role": ..., "segments": [...]}``, plus ``attachments`` when
    present.
    """
    stored = StoredMessage.from_chat_message(message)
    segments: list[SegmentPayload] = []
    for seg in stored.wire_segments():
        stripped = seg
        if is_structured_segment(stripped) and "html_deps" in stripped:
            stripped = cast(
                SegmentPayload,
                {k: v for k, v in stripped.items() if k != "html_deps"},
            )
        segments.append(stripped)
    payload: dict[str, Any] = {"role": stored.role, "segments": segments}
    if stored.attachments:
        payload["attachments"] = [a.model_dump() for a in stored.attachments]

    # Collect every dep object: message-level deps plus the per-block
    # stash, deduped by identity so island deps attached at both levels
    # aren't doubled on the container tag.
    deps: list[HTMLDependency] = []
    seen: set[int] = set()
    for dep in message.html_deps:
        if id(dep) not in seen:
            seen.add(id(dep))
            deps.append(dep)
    for dep_objs in message._block_html_deps.values():
        for dep in dep_objs:
            if id(dep) not in seen:
                seen.add(id(dep))
                deps.append(dep)
    return payload, deps
