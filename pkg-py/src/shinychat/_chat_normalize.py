from __future__ import annotations

import sys
from functools import singledispatch

from htmltools import HTML, Tagifiable

from ._chat_types import ChatMessage

__all__ = ["message_content", "message_content_chunk"]


@singledispatch
def message_content(message):
    """
    Extract content from various message types into a ChatMessage.

    This function uses `singledispatch` to allow for easy extension to support
    new message types. To add support for a new type, register a new function
    using the `@message_content.register` decorator.

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
        tool_request_contents,
        tool_result_contents,
    )

    @message_content.register
    def _(message: Content):
        return ChatMessage(content=str(message))

    @message_content_chunk.register
    def _(chunk: Content):
        return message_content(chunk)

    @message_content.register
    def _(message: ContentText):
        return ChatMessage(content=message.text)

    @message_content_chunk.register
    def _(chunk: ContentText):
        return message_content(chunk)

    @message_content.register
    def _(chunk: ContentToolRequest):
        return ChatMessage(content=tool_request_contents(chunk))

    @message_content_chunk.register
    def _(chunk: ContentToolRequest):
        return message_content(chunk)

    @message_content.register
    def _(chunk: ContentToolResult):
        return ChatMessage(content=tool_result_contents(chunk))

    @message_content_chunk.register
    def _(chunk: ContentToolResult):
        return message_content(chunk)

    @message_content.register
    def _(message: Turn):
        from chatlas import ContentToolResult

        content = ""
        for x in message.contents:
            content += message_content(x).content
        if all(isinstance(x, ContentToolResult) for x in message.contents):
            role = "assistant"
        else:
            role = message.role
        return ChatMessage(content=content, role=role)

    @message_content_chunk.register
    def _(chunk: Turn):
        return message_content(chunk)

    # N.B., unlike R, Python Chat stores UI state and so can replay
    # it with additional workarounds. That's why R currently has a
    # shinychat_contents() method for Chat, but Python doesn't.
except ImportError:
    pass

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
    from google.generativeai.types.generation_types import (
        GenerateContentResponse,
    )

    @message_content.register
    def _(message: GenerateContentResponse):
        return ChatMessage(content=message.text)

    @message_content_chunk.register
    def _(chunk: GenerateContentResponse):
        return ChatMessage(content=chunk.text)

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
