from __future__ import annotations

import warnings
from typing import Any, AsyncIterable, Callable, Literal, Union, cast

from htmltools import HTML, HTMLDependency, Tag, TagChild, TagList
from pydantic import BaseModel

from ._attachments import Attachment
from ._html_islands import (
    IslandBlockPart,
    derive_island_parts,
)
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
    in `js/src/transport/types.ts`). The envelope, not markup scanned from the
    text channel, is the trust signal. The client derives a `running` call from
    an unpaired request.
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
    """
    A typed, server-authored tool result envelope (mirrors `ToolResultBlock`
    in `js/src/transport/types.ts`). The envelope, not markup scanned from the
    text channel, is the trust signal.
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
    """
    One source in a `web_search_results` block (mirrors `WebSearchSource` in
    `js/src/transport/types.ts`). `url` is required; `title`/`domain` are
    display hints.
    """

    url: str
    title: NotRequired[str]
    domain: NotRequired[str]


class WebSearchBlock(TypedDict):
    """
    A typed, server-authored web-search envelope (mirrors `WebSearchBlock` in
    `js/src/transport/types.ts`). The envelope, not markup scanned from the
    text channel, is the trust signal. Consecutive web_* blocks group
    client-side into one `web_activity` block on arrival.
    """

    type: Literal["web_search"]
    version: Literal[1]
    query: str
    cited_sources: NotRequired[list[WebSearchSource]]


class WebSearchResultsBlock(TypedDict):
    """
    The results paired with a preceding `web_search` (mirrors
    `WebSearchResultsBlock` in `js/src/transport/types.ts`).
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
    status: NotRequired[Literal["success", "error"]]


class HtmlBlock(TypedDict):
    """
    A typed, server-authored raw-HTML island (mirrors `HtmlBlock` in
    `js/src/transport/types.ts`). The envelope, not markup scanned from the
    text channel, is the trust signal: `content` renders through the shared
    RawHTML sink. The block is opaque to the thinking-tag/fence state machine,
    which operates only on string content.
    """

    type: Literal["html_block"]
    version: Literal[1]
    content: str
    html_deps: NotRequired[list[SerializedDep]]


# The union of typed blocks carried in `MessagePayload.segments` (outside a
# stream) or via a `block_insert` action (mid-stream).
StructuredBlock = Union[
    ToolRequestBlock,
    ToolResultBlock,
    WebSearchBlock,
    WebSearchResultsBlock,
    WebFetchBlock,
    HtmlBlock,
]

# The subset of structured blocks the markdown-stream wire supports (mirrors
# `StreamBlock`/`asStreamBlock` in
# `js/src/markdown-stream/markdown-stream-entry.ts`): `html_block` and the
# web_* family. Tool blocks are out of scope for streams.
StreamBlock = Union[
    WebSearchBlock,
    WebSearchResultsBlock,
    WebFetchBlock,
    HtmlBlock,
]

# One entry of `MessagePayload.segments`: a string segment or a structured
# block (discriminated by the presence of `type`).
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
        # Server-authored structured blocks carried alongside the string
        # content. They travel the wire as typed segments/`block_insert`
        # actions, never as markup in `content`.
        supplied_blocks: list[StructuredBlock] = list(blocks) if blocks else []
        self.blocks: list[StructuredBlock] = list(supplied_blocks)
        # Ordered interleaving of string runs and structured blocks, set only
        # when the message was normalized from multi-part content. `parts`
        # preserves the original order so wire emission can reproduce it.
        self.parts: list[str | StructuredBlock] | None = parts
        # Parallel to self.blocks: HTMLDependency objects per block index.
        # ChatMessage.__init__ has no session, so raw dep objects are stashed
        # here for session-processing at send/persist time.
        self._block_html_deps: dict[int, list[HTMLDependency]] = {}

        # content _can_ be a TagChild, but it's most likely just a string (of
        # markdown), so only process it if it's not a string.
        deps: list[HTMLDependency] = []
        if not isinstance(content, str):
            # Walk the shared derive_island_parts() partition: trusted
            # non-React runs become HtmlBlock structured blocks; bare React
            # elements are rendered and concatenated as the residual string
            # content.
            content_parts: list[str | StructuredBlock] = []
            # Parallel to content_parts: dep objects for each block entry
            # (None for string entries). Used to populate _block_html_deps.
            content_part_deps: list[list[HTMLDependency] | None] = []
            for part in derive_island_parts(content):
                deps.extend(part.deps)
                if isinstance(part, IslandBlockPart):
                    block: HtmlBlock = {
                        "type": "html_block",
                        "version": 1,
                        "content": part.html,
                    }
                    if part.deps:
                        # Stash the dep objects for this block so the
                        # session-aware send path can serialize them through
                        # session._process_ui. The raw as_dict() copy here is
                        # the no-session fallback, overwritten at send time.
                        block["html_deps"] = [d.as_dict() for d in part.deps]
                        content_part_deps.append(part.deps)
                    else:
                        content_part_deps.append(None)
                    content_parts.append(block)
                else:
                    content_parts.append(part.html)
                    content_part_deps.append(None)
            residual_html = "".join(
                p for p in content_parts if isinstance(p, str)
            )
            if residual_html:
                content = residual_html
                if content_type is None:
                    self.content_type = "html"
            else:
                content = ""
                if content_parts and content_type is None:
                    self.content_type = "html"
            # Merge supplied blocks after the content-derived parts,
            # preserving prior flat-layout semantics (string segments
            # first, then blocks).
            merged_parts = list(content_parts) + supplied_blocks
            self.blocks = [p for p in merged_parts if not isinstance(p, str)]
            # Map block index → dep objects for content-derived blocks.
            block_idx = 0
            for i, p in enumerate(content_parts):
                if not isinstance(p, str):
                    block_deps = content_part_deps[i]
                    if block_deps:
                        self._block_html_deps[block_idx] = block_deps
                    block_idx += 1
            # Only set parts when the content was multi-part (string + block
            # interleaving). A single block with no string content keeps
            # parts = None so the flat layout path in from_chat_message
            # handles it.
            if merged_parts and (
                len(merged_parts) > 1 or not isinstance(merged_parts[0], str)
            ):
                # Coalesce adjacent string runs.
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
            # Greetings are entirely server-authored, so the payload is
            # trusted by construction: tag content renders as a single HTML
            # string with content_type "html". The greeting wire payload has
            # no blocks channel, so there is nowhere to carry html_block
            # envelopes. Bare data-shinychat-react elements stay inline in
            # the string and resolve through the client's component map.
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
    segments: list[StoredSegment]
    attachments: list[Attachment] = []
    # Server-authored structured blocks carried by this message. Stored
    # separately from the string `segments`; `wire_segments()` recombines
    # them.
    blocks: list[StructuredBlock] = []
    # Parallel to `blocks`: how many string `segments` precede each block in
    # the source content. `wire_segments()` re-interleaves instead of
    # appending all blocks after the string segments.
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
        # Multi-part layout: re-interleave each block at its recorded
        # position so the wire order matches the source content order.
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
            # Flat layout (also covers a blocks-only multi-part message).
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


def serialize_html_deps(
    deps: list[HTMLDependency] | None,
    session: Any,
) -> list[SerializedDep] | None:
    """Serialize HTML dependencies through the session's ``_process_ui``.

    Session processing registers web-dependency routes and applies
    ``lib_prefix``; without a session there is nothing to serialize against,
    so ``None`` is returned (callers then keep any raw ``as_dict()`` fallback
    already present).
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

    ``ChatMessage`` stashes raw :class:`~htmltools.HTMLDependency` objects
    per block in ``_block_html_deps`` (it has no session at construction
    time); ``serialize_deps`` serializes dep objects for the current session
    (registering web-dependency routes, applying ``lib_prefix``), and each
    block's raw ``as_dict()`` ``html_deps`` fallback is overwritten with the
    processed form.
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


def as_stored_message(message: ChatMessage, session: Any) -> StoredMessage:
    """Assemble a :class:`StoredMessage` from a :class:`ChatMessage`.

    This is the in-memory wire assembly shared by live send
    (:meth:`Chat._send_append_message`), history save (turns-based
    derivation), and replay emission. Message-level and per-block html deps
    are session-processed through ``session._process_ui``.
    """
    return _assemble_stored_message(
        message, lambda deps: serialize_html_deps(deps, session)
    )


def initial_message_payload(
    message: ChatMessage,
) -> "tuple[dict[str, Any], list[HTMLDependency]]":
    """Build the ``data-initial-messages`` JSON entry for one message.

    This is the session-free complement to :func:`as_stored_message` for
    ``chat_ui(messages=)`` initial messages: it runs at UI render time,
    where no session may exist (e.g. a dynamically rendered ``render_ui``
    output), so it cannot session-process html deps. Instead the payload
    omits every ``html_deps`` field and the raw
    :class:`~htmltools.HTMLDependency` objects (message-level and
    per-block) are returned separately so the caller can attach them to
    the container tag — Shiny's dependency system renders them, session
    or not.

    The entry shape mirrors the ``message`` wire action's payload:
    ``{"role": ..., "segments": [...]}`` where ``segments`` is the same
    ordered union (:meth:`StoredMessage.wire_segments`) — string parts as
    ``{"content", "content_type"}`` and structured blocks as their block
    dicts — plus ``attachments`` when present.
    """
    stored = StoredMessage.from_chat_message(message)
    segments: list[MessagePayloadSegment] = []
    for seg in stored.wire_segments():
        # NB: an inline `in` check (not a TypeGuard) so pyright narrows
        # both branches of the TypedDict union. Copy before stripping so
        # the block dict stays intact for other consumers.
        stripped = seg
        if "type" in stripped and "html_deps" in stripped:
            stripped = cast(
                MessagePayloadSegment,
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
