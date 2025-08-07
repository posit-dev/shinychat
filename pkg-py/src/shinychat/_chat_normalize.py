from __future__ import annotations

import sys
from functools import singledispatch

from htmltools import HTML, Tagifiable

from ._chat_types import ChatMessage

__all__ = ["get_message_content", "get_message_chunk_content"]


@singledispatch
def get_message_content(message) -> ChatMessage:
    """
    Extract content from various message types into a ChatMessage.

    This function uses `singledispatch` to allow for easy extension to support
    new message types. To add support for a new type, register a new function
    using the `@get_message_content.register` decorator.

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
        return ChatMessage(content=message, role="assistant")
    if isinstance(message, dict):
        if "content" not in message:
            raise ValueError("Message dictionary must have a 'content' key")
        return ChatMessage(
            content=message["content"],
            role=message.get("role", "assistant"),
        )
    raise ValueError(
        f"Don't know how to extract content for message type {type(message)}: {message}. "
        "Consider registering a function to handle this type via `@get_message_content.register`"
    )


@singledispatch
def get_message_chunk_content(chunk) -> ChatMessage:
    """
    Extract content from various message chunk types into a ChatMessage.

    This function uses `singledispatch` to allow for easy extension to support
    new chunk types. To add support for a new type, register a new function
    using the `@get_message_chunk_content.register` decorator.

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
        return ChatMessage(content=chunk, role="assistant")
    if isinstance(chunk, dict):
        if "content" not in chunk:
            raise ValueError("Chunk dictionary must have a 'content' key")
        return ChatMessage(
            content=chunk["content"],
            role=chunk.get("role", "assistant"),
        )
    raise ValueError(
        f"Don't know how to extract content for message chunk type {type(chunk)}: {chunk}. "
        "Consider registering a function to handle this type via `@get_message_chunk_content.register`"
    )


# ------------------------------------------------------------------
# Shiny tagifiable content extractor
# ------------------------------------------------------------------


@get_message_content.register
def _(message: Tagifiable) -> ChatMessage:
    return ChatMessage(content=message, role="assistant")


@get_message_chunk_content.register
def _(chunk: Tagifiable) -> ChatMessage:
    return ChatMessage(content=chunk, role="assistant")


# ------------------------------------------------------------------
# LangChain content extractor
# ------------------------------------------------------------------

try:
    from langchain_core.messages import BaseMessage, BaseMessageChunk

    @get_message_content.register
    def _(message: BaseMessage) -> ChatMessage:
        if isinstance(message.content, list):
            raise ValueError(
                "The `message.content` provided seems to represent numerous messages. "
                "Consider iterating over `message.content` and calling .append_message() on each iteration."
            )
        return ChatMessage(
            content=message.content,
            role="assistant",
        )

    @get_message_chunk_content.register
    def _(chunk: BaseMessageChunk) -> ChatMessage:
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

    @get_message_content.register
    def _(message: ChatCompletion) -> ChatMessage:
        return ChatMessage(
            content=message.choices[0].message.content,
            role="assistant",
        )

    @get_message_chunk_content.register
    def _(chunk: ChatCompletionChunk) -> ChatMessage:
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

    @get_message_content.register
    def _(message: AnthropicMessage) -> ChatMessage:
        content = message.content[0]
        if content.type != "text":
            raise ValueError(
                f"Anthropic message type {content.type} not supported. "
                "Only 'text' type is currently supported"
            )
        return ChatMessage(content=content.text, role="assistant")

    # Old versions of singledispatch doesn't seem to support union types
    if sys.version_info >= (3, 11):
        from anthropic.types import RawMessageStreamEvent

        @get_message_chunk_content.register
        def _(chunk: RawMessageStreamEvent) -> ChatMessage:
            content = ""
            if chunk.type == "content_block_delta":
                if chunk.delta.type != "text_delta":
                    raise ValueError(
                        f"Anthropic message delta type {chunk.delta.type} not supported. "
                        "Only 'text_delta' type is supported"
                    )
                content = chunk.delta.text

            return ChatMessage(content=content, role="assistant")
except ImportError:
    pass


# ------------------------------------------------------------------
# Google content extractor
# ------------------------------------------------------------------

try:
    from google.generativeai.types.generation_types import (
        GenerateContentResponse,
    )

    @get_message_content.register
    def _(message: GenerateContentResponse) -> ChatMessage:
        return ChatMessage(content=message.text, role="assistant")

    @get_message_chunk_content.register
    def _(chunk: GenerateContentResponse) -> ChatMessage:
        return ChatMessage(content=chunk.text, role="assistant")

except ImportError:
    pass


# ------------------------------------------------------------------
# Ollama content extractor
# ------------------------------------------------------------------

try:
    from ollama import ChatResponse

    @get_message_content.register
    def _(message: ChatResponse) -> ChatMessage:
        msg = message.message
        return ChatMessage(msg.content, role="assistant")

    @get_message_chunk_content.register
    def _(chunk: ChatResponse) -> ChatMessage:
        msg = chunk.message
        return ChatMessage(msg.content, role="assistant")

except ImportError:
    pass
