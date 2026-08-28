from __future__ import annotations

import warnings
from typing import Any, AsyncIterable, Literal, Union

from htmltools import HTML, HTMLDependency, Tag, TagChild, TagifiedTag, TagList
from pydantic import BaseModel

from ._attachments import Attachment
from ._html_islands import split_html_islands
from ._typing_extensions import NotRequired, TypedDict
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
    """
    A typed, server-authored tool request envelope (mirrors `ToolRequestBlock`
    in `js/src/transport/types.ts`). The envelope itself is the trust signal:
    only the server can construct these blocks. The client derives a `running`
    call from an unpaired request.
    """

    type: Literal["tool_request"]
    version: Literal[1]
    # Correlates with the result; keys transcript-wide request suppression.
    request_id: str
    tool_name: str
    title: NotRequired[str]  # HTML -> RawHTML (the tool definition's title)
    icon: NotRequired[str]  # HTML -> RawHTML (the tool definition's icon)
    intent: NotRequired[str]  # text -> escaped
    # JSON string, rendered as a markdown code block (escaped).
    arguments: NotRequired[str]
    grouping: NotRequired[Literal["none", "tool", "all"]]


class ToolResultBlock(TypedDict):
    """
    A typed, server-authored tool result envelope (mirrors `ToolResultBlock`
    in `js/src/transport/types.ts`). The envelope itself is the trust signal:
    only the server can construct these blocks.
    """

    type: Literal["tool_result"]
    version: Literal[1]
    # Correlates with the request; keys transcript-wide request suppression.
    request_id: str
    tool_name: str
    # "running" is NOT a wire value; the client derives it from an unpaired
    # request.
    status: Literal["success", "error"]
    value: NotRequired[str]
    value_type: NotRequired[
        Literal["html", "markdown", "text", "code", "content_extra"]
    ]
    request_call: NotRequired[str]
    title: NotRequired[str]  # HTML -> RawHTML
    icon: NotRequired[str]  # HTML -> RawHTML
    intent: NotRequired[str]  # text -> escaped
    label: NotRequired[str]  # text -> escaped
    value_preview: NotRequired[str]  # text -> escaped
    grouping: NotRequired[Literal["none", "tool", "all"]]
    show_request: NotRequired[bool]
    expanded: NotRequired[bool]
    open_style: NotRequired[Literal["minimal", "framed"]]
    full_screen: NotRequired[bool]
    # Internal-only: set by wrap_custom_tool_result, never author-facing.
    custom_display: NotRequired[bool]
    footer: NotRequired[str]  # HTML -> RawHTML


class WebSearchSource(TypedDict):
    """
    One source in a `web_search_results` block (mirrors `WebSearchSource` in
    `js/src/transport/types.ts`): a real JSON array entry, not a stringified
    attribute. `url` is required; `title`/`domain` are display hints (the
    client derives a domain from the URL when absent).
    """

    url: str
    title: NotRequired[str]
    domain: NotRequired[str]


class WebSearchBlock(TypedDict):
    """
    A typed, server-authored web-search envelope (mirrors `WebSearchBlock`
    in `js/src/transport/types.ts`). The envelope itself is the trust signal:
    only the server can construct these blocks. Consecutive web_* blocks
    group client-side into one `web_activity` block on arrival.
    """

    type: Literal["web_search"]
    version: Literal[1]
    query: str
    # Answer-citation fallback (the structured re-expression of the markup
    # path's rehypeAttachCitedSources): sources the answer cited, shown only
    # while no provider results attach to this search.
    cited_sources: NotRequired[list[WebSearchSource]]


class WebSearchResultsBlock(TypedDict):
    """
    The results paired with a preceding `web_search` (mirrors
    `WebSearchResultsBlock` in `js/src/transport/types.ts`): the client
    attaches the sources to the earliest still-pending search in the
    activity (the adjacency pairing `WebActivity.parseItems` uses on the
    markup path).
    """

    type: Literal["web_search_results"]
    version: Literal[1]
    sources: list[WebSearchSource]


class WebFetchBlock(TypedDict):
    """
    A typed, server-authored web-fetch envelope (mirrors `WebFetchBlock` in
    `js/src/transport/types.ts`).
    """

    type: Literal["web_fetch"]
    version: Literal[1]
    url: str
    # Absent when the server didn't report one (chatlas allows None).
    status: NotRequired[Literal["success", "error"]]


class HtmlBlock(TypedDict):
    """
    A typed, server-authored raw-HTML island (mirrors `HtmlBlock` in
    `js/src/transport/types.ts`). The envelope itself is the trust signal:
    only the server can construct these blocks, so `content` renders through
    the shared RawHTML sink. The block is opaque to the thinking-tag/fence
    state machine, which operates only on string content.
    """

    type: Literal["html_block"]
    version: Literal[1]
    # Trusted HTML -> RawHTML
    content: str
    # Dependencies this island needs, rendered before its HTML mounts (the
    # block-level complement to the envelope's `html_deps`).
    html_deps: NotRequired[list[SerializedDep]]


# The union of typed blocks carried in `MessagePayload.segments` (outside a
# stream) or via a `block_insert` action (mid-stream). The union grows per
# the design.
StructuredBlock = Union[
    ToolRequestBlock,
    ToolResultBlock,
    WebSearchBlock,
    WebSearchResultsBlock,
    WebFetchBlock,
    HtmlBlock,
]

# One entry of `MessagePayload.segments`: a string segment
# (`{content, content_type}`) or a structured block (discriminated by the
# presence of `type`).
MessagePayloadSegment = Union[StringSegment, StructuredBlock]


class MessagePayload(TypedDict):
    role: Literal["user", "assistant"]
    segments: list[MessagePayloadSegment]
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
    """
    Delivers one complete structured block while a message stream is in
    flight. The client appends it to the in-flight message's block list.
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
        self.content_type: ContentType = (
            content_type if content_type is not None else "markdown"
        )
        # Server-authored structured blocks (e.g. `tool_result`) carried
        # alongside the string content. They travel the wire as typed
        # segments/`block_insert` actions, never as markup in `content`.
        # When the caller also passes non-string (tag-like) content that
        # generates html_blocks, the supplied blocks follow the
        # content-derived parts (preserving prior flat-layout semantics:
        # string segments first, then blocks).
        supplied_blocks: list[StructuredBlock] = list(blocks) if blocks else []
        self.blocks: list[StructuredBlock] = list(supplied_blocks)
        # Ordered interleaving of string runs and structured blocks, set only
        # when the message was normalized from multi-part content (e.g. a
        # chatlas `Turn` with text/tool-result/text). `content` and `blocks`
        # remain the flat views; `parts` preserves the original order so wire
        # emission can reproduce it. String runs and blocks strictly
        # alternate (adjacent string items are coalesced).
        self.parts: list[str | StructuredBlock] | None = parts

        # content _can_ be a TagChild, but it's most likely just a string (of
        # markdown), so only process it if it's not a string.
        deps: list[HTMLDependency] = []
        if not isinstance(content, str):
            # Walk the split_html_islands() output: island wrappers
            # (<shiny-chat-raw-html>) become HtmlBlock structured blocks
            # carrying the trusted server-authored HTML; bare React elements
            # are rendered and concatenated as the residual string content.
            # The string-segment path (isinstance(content, str)) is retained
            # for string-typed content — this branch only fires for non-string
            # (tag-like) content.
            split = split_html_islands(content)
            content_parts: list[str | StructuredBlock] = []
            for item in split:
                if (
                    isinstance(item, (Tag, TagifiedTag))
                    and item.name == "shiny-chat-raw-html"
                ):
                    # Island wrapper: render its children (not the wrapper
                    # itself) as the block's trusted HTML content.
                    island = TagList(*item.children).render()
                    island_html, island_deps = (
                        island["html"],
                        island["dependencies"],
                    )
                    deps.extend(island_deps)
                    block: HtmlBlock = {
                        "type": "html_block",
                        "version": 1,
                        "content": island_html,
                    }
                    if island_deps:
                        block["html_deps"] = [d.as_dict() for d in island_deps]
                    content_parts.append(block)
                else:
                    # Bare React element: render it bare and keep it as a
                    # string part inline, so `parts` preserves the original
                    # interleaving with html_blocks.
                    rendered = TagList(item).render()
                    deps.extend(rendered["dependencies"])
                    # Surround with blank lines so the markdown parser treats
                    # block-level custom elements correctly.
                    run = f"\n\n{rendered['html']}\n\n"
                    if content_parts and isinstance(content_parts[-1], str):
                        content_parts[-1] += run
                    else:
                        content_parts.append(run)
            residual_html = "".join(
                p for p in content_parts if isinstance(p, str)
            )
            if residual_html:
                content = residual_html
                if content_type is None:
                    self.content_type = "html"
            else:
                content = ""
                # Even with no residual string, html_blocks carry trusted
                # HTML: the message is html-typed (unless the caller passed
                # an explicit content_type).
                if content_parts and content_type is None:
                    self.content_type = "html"
            # Merge supplied blocks after the content-derived parts,
            # preserving prior flat-layout semantics (string segments
            # first, then blocks). Derive self.blocks from the merged
            # list so ordering is consistent.
            merged_parts = list(content_parts) + supplied_blocks
            self.blocks = [p for p in merged_parts if not isinstance(p, str)]
            # Only set parts when the content was multi-part (string + block
            # interleaving). A single block with no string content keeps
            # parts = None so the flat layout path in from_chat_message
            # handles it (one empty string segment carrying html_deps + the
            # block appended after).
            if merged_parts and (
                len(merged_parts) > 1 or not isinstance(merged_parts[0], str)
            ):
                # Coalesce adjacent string runs (string runs and blocks
                # strictly alternate in parts).
                coalesced: list[str | StructuredBlock] = []
                for p in merged_parts:
                    if (
                        isinstance(p, str)
                        and coalesced
                        and isinstance(coalesced[-1], str)
                    ):
                        coalesced[-1] += p
                    else:
                        coalesced.append(p)
                self.parts = coalesced
            elif parts:
                self.parts = parts

        self.content = content
        self.html_deps: list[HTMLDependency] = deps


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
    segments: list[StoredSegment]
    attachments: list[Attachment] = []
    # Server-authored structured blocks carried by this message. Stored
    # separately from the string `segments` (which keep their flat
    # content/content_type shape); `wire_segments()` recombines them.
    blocks: list[StructuredBlock] = []
    # Parallel to `blocks`: how many string `segments` precede each block in
    # the source content. Set only when the message was normalized from
    # multi-part content (e.g. a chatlas `Turn`) that interleaves string runs
    # and blocks; `wire_segments()` then re-interleaves instead of appending
    # all blocks after the string segments.
    block_positions: list[int] | None = None

    @property
    def content(self) -> str:
        return "".join(
            StoredSegment.stringify(s.content, s.content_type)
            for s in self.segments
        )

    @property
    def html_deps(self) -> list[SerializedDep] | None:
        deps: list[SerializedDep] = []
        for s in self.segments:
            if s.html_deps:
                deps.extend(s.html_deps)
        return deps or None

    def wire_segments(self) -> list[MessagePayloadSegment]:
        segments: list[MessagePayloadSegment] = [
            {"content": s.content, "content_type": s.content_type}
            for s in self.segments
        ]
        if self.block_positions is None or len(self.block_positions) != len(
            self.blocks
        ):
            # Flat layout: blocks follow the string segments.
            segments.extend(self.blocks)
            return segments
        # Multi-part layout (e.g. a chatlas `Turn` with text/tool-result/
        # text): re-interleave each block at its recorded position so the
        # wire order matches the source content order.
        out: list[MessagePayloadSegment] = []
        positioned = list(zip(self.block_positions, self.blocks))
        bi = 0
        for i, seg in enumerate(segments):
            while bi < len(positioned) and positioned[bi][0] <= i:
                out.append(positioned[bi][1])
                bi += 1
            out.append(seg)
        while bi < len(positioned):
            out.append(positioned[bi][1])
            bi += 1
        return out

    @classmethod
    def from_chat_message(
        cls,
        message: ChatMessage,
        html_deps: list[SerializedDep] | None = None,
    ) -> StoredMessage:
        parts = message.parts
        if not parts or not any(isinstance(p, str) for p in parts):
            # Flat layout (also covers a blocks-only multi-part message: with
            # no string runs to interleave with, appending blocks after the
            # single — possibly empty — string segment is already correct,
            # and keeps a segment to carry `html_deps`).
            return cls(
                role=message.role,
                segments=[
                    StoredSegment(
                        content=str(message.content),
                        content_type=message.content_type,
                        html_deps=html_deps,
                    )
                ],
                attachments=message.attachments,
                blocks=list(message.blocks),
            )
        # Multi-part layout: split the string runs into their own segments so
        # the blocks can be re-interleaved at their original positions.
        segments: list[StoredSegment] = []
        blocks: list[StructuredBlock] = []
        positions: list[int] = []
        for part in parts:
            if isinstance(part, str):
                segments.append(
                    StoredSegment(
                        content=part,
                        content_type=message.content_type,
                    )
                )
            else:
                positions.append(len(segments))
                blocks.append(part)
        if segments:
            segments[0].html_deps = html_deps
        return cls(
            role=message.role,
            segments=segments,
            attachments=message.attachments,
            blocks=blocks,
            block_positions=positions or None,
        )
