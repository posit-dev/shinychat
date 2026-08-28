from __future__ import annotations

import json
import sys
from functools import singledispatch
from typing import TYPE_CHECKING, Any, TypeGuard

from htmltools import HTML, HTMLDependency, Tag, Tagifiable, TagList

from ._chat_types import ChatMessage, StructuredBlock

if TYPE_CHECKING:
    from chatlas.types import ContentToolResult

__all__ = ["message_content", "message_content_chunk"]


@singledispatch
def message_content(message):
    """
    Extract content from various message types into a ChatMessage.

    This function uses `singledispatch` to allow for easy extension to support
    new message types. To add support for a new type, register a new function
    using the `@message_content.register` decorator.

    To render a `chatlas.ContentToolResult` subclass as fully custom,
    standalone UI after a tool call settles, register complete and streaming
    handlers for it here and in `message_content_chunk()`. The pending
    condensed activity row remains while the tool runs, then shinychat pairs
    the custom result with that call and renders the returned UI outside the
    default drill-down card.

    Examples
    --------

    ```python
    from chatlas import ContentToolResult
    from shiny import ui
    from shinychat import message_content, message_content_chunk
    from shinychat.types import ChatMessage


    class WeatherResult(ContentToolResult):
        location_name: str


    def weather_result_ui(result: WeatherResult) -> ChatMessage:
        temperature = result.value["temperature_2m"]
        return ChatMessage(
            content=ui.div(
                ui.h4(result.location_name),
                f"{temperature} C",
                class_="weather-result",
            )
        )


    @message_content.register
    def _(result: WeatherResult) -> ChatMessage:
        return weather_result_ui(result)


    @message_content_chunk.register
    def _(result: WeatherResult) -> ChatMessage:
        return weather_result_ui(result)
    ```

    Parameters
    ----------
    message
        The message object to extract content from (e.g., ChatCompletion,
        BaseMessage, etc.).

    Note
    ----
    This function is implicitly called by `Chat.append_message()` to support
    handling of various message types. It is not intended to be called directly
    by users, but may be useful for debugging or advanced use cases.

    Returns
    -------
    ChatMessage
        A ChatMessage object containing the extracted content and role.

    Raises
    ------
    ValueError
        If the message type is unsupported.
    """
    if isinstance(message, (str, HTML)) or message is None:
        return ChatMessage(content=message)
    if isinstance(message, ChatMessage):
        return message
    if isinstance(message, dict):
        if "content" not in message:
            raise ValueError("Message dictionary must have a 'content' key")
        return ChatMessage(
            content=message["content"],
            role=message.get("role", "assistant"),
            attachments=message.get("attachments"),
        )
    raise ValueError(
        f"Don't know how to extract content for message type {type(message)}: {message}. "
        "Consider registering a function to handle this type via `@message_content.register`"
    )


@singledispatch
def message_content_chunk(chunk):
    """
    Extract content from various message chunk types into a ChatMessage.

    This function uses `singledispatch` to allow for easy extension to support
    new chunk types. To add support for a new type, register a new function
    using the `@message_content_chunk.register` decorator.

    To render a `chatlas.ContentToolResult` subclass as fully custom,
    standalone UI after a tool call settles, register complete and streaming
    handlers for it here and in `message_content()`. The pending condensed
    activity row remains while the tool runs, then shinychat pairs the custom
    result with that call and renders the returned UI outside the default
    drill-down card.

    Examples
    --------

    ```python
    from chatlas import ContentToolResult
    from shiny import ui
    from shinychat import message_content, message_content_chunk
    from shinychat.types import ChatMessage


    class WeatherResult(ContentToolResult):
        location_name: str


    def weather_result_ui(result: WeatherResult) -> ChatMessage:
        temperature = result.value["temperature_2m"]
        return ChatMessage(
            content=ui.div(
                ui.h4(result.location_name),
                f"{temperature} C",
                class_="weather-result",
            )
        )


    @message_content.register
    def _(result: WeatherResult) -> ChatMessage:
        return weather_result_ui(result)


    @message_content_chunk.register
    def _(result: WeatherResult) -> ChatMessage:
        return weather_result_ui(result)
    ```

    Parameters
    ----------
    chunk
        The message chunk object to extract content from (e.g., ChatCompletionChunk,
        BaseMessageChunk, etc.).

    Note
    ----
    This function is implicitly called by `Chat.append_message_stream()` (on every
    chunk of a message stream). It is not intended to be called directly by
    users, but may be useful for debugging or advanced use cases.

    Returns
    -------
    ChatMessage
        A ChatMessage object containing the extracted content and role.

    Raises
    ------
    ValueError
        If the chunk type is unsupported.
    """
    if isinstance(chunk, (str, HTML)) or chunk is None:
        return ChatMessage(content=chunk)
    if isinstance(chunk, ChatMessage):
        return chunk
    if isinstance(chunk, dict):
        if "content" not in chunk:
            raise ValueError("Chunk dictionary must have a 'content' key")
        return ChatMessage(
            content=chunk["content"],
            role=chunk.get("role", "assistant"),
            attachments=chunk.get("attachments"),
        )
    raise ValueError(
        f"Don't know how to extract content for message chunk type {type(chunk)}: {chunk}. "
        "Consider registering a function to handle this type via `@message_content_chunk.register`"
    )


# ------------------------------------------------------------------
# Shiny tagifiable content extractor
# ------------------------------------------------------------------


@message_content.register
def _(message: Tagifiable):
    return ChatMessage(content=message)


@message_content_chunk.register
def _(chunk: Tagifiable):
    return ChatMessage(content=chunk)


# -----------------------------------------------------------------
# chatlas tool call display
# -----------------------------------------------------------------
try:
    from chatlas import ContentToolRequest, ContentToolResult, Turn
    from chatlas.types import Content, ContentText

    # Import here to avoid hard dependency on pydantic
    from ._chat_normalize_chatlas import (
        citation_aside,
        tool_display_override,
        tool_request_contents,
        tool_request_message,
        tool_result_contents,
        tool_result_message,
    )

    @message_content.register
    def _(message: Content):
        return ChatMessage(content=str(message))

    @message_content_chunk.register
    def _(chunk: Content):
        return message_content(chunk)

    @message_content.register
    def _(message: ContentText):
        text = message.text
        # chatlas' expand_tool_result() inserts <tool-content> XML wrapper
        # tags when moving images/PDFs out of tool results during UserTurn
        # construction. Suppress these so they don't appear as visible text.
        if text.startswith("<tool-content") or text.startswith(
            "</tool-content"
        ):
            return ChatMessage(content="")
        return ChatMessage(content=text)

    @message_content_chunk.register
    def _(chunk: ContentText):
        return message_content(chunk)

    from chatlas.types import ContentImageInline, ContentImageRemote, ContentPDF

    @message_content.register
    def _(message: ContentImageInline):
        src = f"data:{message.image_content_type};base64,{message.data}"
        return ChatMessage(content=Tag("img", src=src))

    @message_content_chunk.register
    def _(chunk: ContentImageInline):
        return message_content(chunk)

    @message_content.register
    def _(message: ContentImageRemote):
        return ChatMessage(content=Tag("img", src=message.url))

    @message_content_chunk.register
    def _(chunk: ContentImageRemote):
        return message_content(chunk)

    @message_content.register
    def _(message: ContentPDF):
        return ChatMessage(content=message.filename or "document.pdf")

    @message_content_chunk.register
    def _(chunk: ContentPDF):
        return message_content(chunk)

    @message_content.register
    def _(chunk: ContentToolRequest):
        return tool_request_message(tool_request_contents(chunk))

    @message_content_chunk.register
    def _(chunk: ContentToolRequest):
        return message_content(chunk)

    @message_content.register
    def _(chunk: ContentToolResult):
        result = tool_result_contents(chunk)
        return tool_result_message(result)

    @message_content_chunk.register
    def _(chunk: ContentToolResult):
        return message_content(chunk)

    try:
        from chatlas.types import (
            ContentCitation,
            ContentToolRequestFetch,
            ContentToolRequestSearch,
            ContentToolResponseFetch,
            ContentToolResponseSearch,
            WebSource,
        )

        @message_content.register
        def _(message: ContentToolRequestSearch):
            if tool_display_override() == "none":
                return ChatMessage(content="")
            return ChatMessage(
                content=Tag(
                    "shiny-web-search",
                    data_shinychat_react=True,
                    query=message.query,
                )
            )

        @message_content_chunk.register
        def _(chunk: ContentToolRequestSearch):
            return message_content(chunk)

        @message_content.register
        def _(message: ContentToolResponseSearch):
            if tool_display_override() == "none":
                return ChatMessage(content="")
            sources = [
                {
                    "url": s.url,
                    "title": s.title,
                }
                for s in message.sources
            ]
            return ChatMessage(
                content=Tag(
                    "shiny-web-search-results",
                    data_shinychat_react=True,
                    sources=json.dumps(sources),
                )
            )

        @message_content_chunk.register
        def _(chunk: ContentToolResponseSearch):
            return message_content(chunk)

        @message_content.register
        def _(message: ContentToolRequestFetch):
            return ChatMessage(content="")

        @message_content_chunk.register
        def _(chunk: ContentToolRequestFetch):
            return message_content(chunk)

        @message_content.register
        def _(message: ContentToolResponseFetch):
            if tool_display_override() == "none":
                return ChatMessage(content="")
            return ChatMessage(
                content=Tag(
                    "shiny-web-fetch",
                    data_shinychat_react=True,
                    url=message.url,
                    status=message.status,
                )
            )

        @message_content_chunk.register
        def _(chunk: ContentToolResponseFetch):
            return message_content(chunk)

        @message_content.register
        def _(message: ContentCitation):
            if tool_display_override() == "none" or not isinstance(
                message.source, WebSource
            ):
                return ChatMessage(content="")
            return ChatMessage(
                content=citation_aside(
                    message.source.url,
                    message.source.title,
                    grounded_span=message.grounded_span,
                    cited_quote=message.cited_quote,
                ),
                content_type="markdown",
            )

        @message_content_chunk.register
        def _(chunk: ContentCitation):
            return message_content(chunk)

    except ImportError:
        pass

    # ContentThinking is a complete thought stored in a turn, ContentThinkingDelta is
    # a thinking chunk from .stream(content="all")
    try:
        from chatlas.types import ContentThinking, ContentThinkingDelta

        @message_content.register
        def _(chunk: ContentThinking):
            return ChatMessage(content=chunk.thinking, content_type="thinking")

        @message_content.register
        def _(chunk: ContentThinkingDelta):
            return ChatMessage(content=chunk.thinking, content_type="thinking")

        @message_content_chunk.register
        def _(chunk: ContentThinking):
            return ChatMessage(content=chunk.thinking, content_type="thinking")

        @message_content_chunk.register
        def _(chunk: ContentThinkingDelta):
            return ChatMessage(content=chunk.thinking, content_type="thinking")
    except ImportError:
        pass

    @message_content.register
    def _(message: Turn):
        content = ""
        deps: list[HTMLDependency] = []
        blocks: list[StructuredBlock] = []
        # Ordered interleaving of string runs and structured blocks, so the
        # wire emission can reproduce the turn's original content order
        # (text/tool-result/text must not arrive as text/text/tool-result).
        parts: list[str | StructuredBlock] = []
        for x in message.contents:
            # Normalize and wrap per item, mirroring R's
            # `contents_shinychat_wrapped()`.
            # Converting a turn discards each `ContentToolResult` before any
            # caller could wrap it, so a turn carrying a custom tool result
            # would otherwise emit bare UI with no `<shiny-tool-result>` for
            # the client to pair its request against.
            item = normalize_message(x)
            content += item.content
            # Collected separately from the content: only the rendered *string*
            # is concatenated, so per-item dependencies would otherwise be
            # dropped and the item's UI would arrive unstyled and unscripted.
            deps += item.html_deps
            # Structured blocks (e.g. `tool_result`) can't be concatenated
            # into the content string; they travel alongside it.
            blocks.extend(item.blocks)
            if item.content:
                # Coalesce adjacent string items into one run: string runs
                # and blocks strictly alternate in `parts`.
                if parts and isinstance(parts[-1], str):
                    parts[-1] += item.content
                else:
                    parts.append(item.content)
            parts.extend(item.blocks)
        if all(isinstance(x, ContentToolResult) for x in message.contents):
            role = "assistant"
        else:
            role = message.role
        result = ChatMessage(
            content=content, role=role, blocks=blocks, parts=parts or None
        )
        result.html_deps = deps + result.html_deps
        return result

    @message_content_chunk.register
    def _(chunk: Turn):
        return message_content(chunk)

    # N.B., unlike R, Python Chat stores UI state and so can replay
    # it with additional workarounds. That's why R currently has a
    # shinychat_contents() method for Chat, but Python doesn't.
except ImportError:
    pass


def normalize_message(message: Any) -> ChatMessage:
    """Normalize a complete message and apply shared postprocessing."""
    return _wrap_custom_tool_result(message, message_content(message))


def normalize_message_chunk(chunk: Any) -> ChatMessage:
    """Normalize a message chunk and apply shared postprocessing."""
    return _wrap_custom_tool_result(chunk, message_content_chunk(chunk))


def _is_tool_result(value: object) -> TypeGuard["ContentToolResult"]:
    try:
        from chatlas.types import ContentToolResult

        return isinstance(value, ContentToolResult)
    except ImportError:
        return False


def _wrap_custom_tool_result(message: Any, msg: ChatMessage) -> ChatMessage:
    """Wrap custom tool-result UI in a routable result element."""
    if not _is_tool_result(message):
        return msg

    if message.request is None:
        return msg

    try:
        from ._chat_normalize_chatlas import (
            ShinyToolCardMessage,
            ValueType,
            is_legacy,
            resolve_tool_annotations,
            tool_display_override,
            wrap_custom_tool_result,
        )
    except ImportError:
        return msg

    if isinstance(msg, ShinyToolCardMessage):
        return msg

    # These are shinychat's own early returns, not an author's bypass.
    if tool_display_override() == "none" or is_legacy():
        return msg

    # Mirror the author's payload mode, while keeping the wrapper itself
    # routable as HTML.
    value_type: ValueType = (
        msg.content_type
        if msg.content_type in ("html", "markdown", "text")
        else "markdown"
    )
    annotations = resolve_tool_annotations(message.request.tool)
    wrapped = wrap_custom_tool_result(
        request_id=message.request.id,
        tool_name=message.request.name,
        # A custom renderer owns its error presentation; the wrapper only
        # carries the lifecycle signal needed by the client.
        status="success" if message.error is None else "error",
        value=TagList(HTML(msg.content))
        if value_type == "html"
        else msg.content,
        value_type=value_type,
        grouping=annotations.grouping,
    )

    result = ChatMessage(
        content=wrapped,
        role=msg.role,
        attachments=msg.attachments,
    )
    result.html_deps = list(msg.html_deps) + list(result.html_deps)
    return result


# ------------------------------------------------------------------
# LangChain content extractor
# ------------------------------------------------------------------

try:
    from langchain_core.messages import BaseMessage, BaseMessageChunk

    @message_content.register
    def _(message: BaseMessage):
        if isinstance(message.content, list):
            raise ValueError(
                "The `message.content` provided seems to represent numerous messages. "
                "Consider iterating over `message.content` and calling .append_message() on each iteration."
            )
        return ChatMessage(
            content=message.content,
            role="assistant",
        )

    @message_content_chunk.register
    def _(chunk: BaseMessageChunk):
        if isinstance(chunk.content, list):
            raise ValueError(
                "The `chunk.content` provided seems to represent numerous message chunks. "
                "Consider iterating over `chunk.content` and calling .append_message() on each iteration."
            )
        return ChatMessage(
            content=chunk.content,
            role="assistant",
        )
except ImportError:
    pass


# ------------------------------------------------------------------
# OpenAI content extractor
# ------------------------------------------------------------------

try:
    from openai.types.chat import ChatCompletion, ChatCompletionChunk

    @message_content.register
    def _(message: ChatCompletion):
        return ChatMessage(
            content=message.choices[0].message.content,
            role="assistant",
        )

    @message_content_chunk.register
    def _(chunk: ChatCompletionChunk):
        return ChatMessage(
            content=chunk.choices[0].delta.content,
            role="assistant",
        )
except ImportError:
    pass


# ------------------------------------------------------------------
# Anthropic content extractor
# ------------------------------------------------------------------

try:
    from anthropic.types import (  # pyright: ignore[reportMissingImports]
        Message as AnthropicMessage,
    )

    @message_content.register
    def _(message: AnthropicMessage):
        content = message.content[0]
        if content.type != "text":
            raise ValueError(
                f"Anthropic message type {content.type} not supported. "
                "Only 'text' type is currently supported"
            )
        return ChatMessage(content=content.text)

    # Old versions of singledispatch doesn't seem to support union types
    if sys.version_info >= (3, 11):
        from anthropic.types import (  # pyright: ignore[reportMissingImports]
            RawMessageStreamEvent,
        )

        @message_content_chunk.register
        def _(chunk: RawMessageStreamEvent):
            content = ""
            if chunk.type == "content_block_delta":
                if chunk.delta.type != "text_delta":
                    raise ValueError(
                        f"Anthropic message delta type {chunk.delta.type} not supported. "
                        "Only 'text_delta' type is supported"
                    )
                content = chunk.delta.text

            return ChatMessage(content=content)
except ImportError:
    pass


# ------------------------------------------------------------------
# Google content extractor
# ------------------------------------------------------------------

try:
    from google.genai.types import (
        Content,
        GenerateContentResponse,
    )

    @message_content.register
    def _(message: GenerateContentResponse):
        return ChatMessage(content=message.text)

    @message_content_chunk.register
    def _(chunk: GenerateContentResponse):
        return ChatMessage(content=chunk.text)

    @message_content.register
    def _(message: Content):
        content = ""
        parts = message.parts  # pyright: ignore[reportAttributeAccessIssue]
        if parts is not None:
            for part in parts:
                if hasattr(part, "text") and part.text:
                    content += part.text

        role_val: str | None = message.role  # pyright: ignore[reportAttributeAccessIssue]
        if role_val in ("user", "system"):
            role = role_val
        else:
            role = "assistant"
        return ChatMessage(content=content, role=role)

    @message_content_chunk.register
    def _(chunk: Content):
        # reuse the message logic
        return message_content(chunk)

except ImportError:
    pass


# ------------------------------------------------------------------
# Ollama content extractor
# ------------------------------------------------------------------

try:
    from ollama import ChatResponse

    @message_content.register
    def _(message: ChatResponse):
        msg = message.message
        return ChatMessage(msg.content)

    @message_content_chunk.register
    def _(chunk: ChatResponse):
        msg = chunk.message
        return ChatMessage(msg.content)

except ImportError:
    pass
