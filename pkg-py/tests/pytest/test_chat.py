from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import types
from datetime import datetime
from typing import Any, Union, cast, get_args, get_origin

import pytest
from htmltools import HTMLDependency, TagList, tags
from shiny import Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_normalize import message_content, message_content_chunk
from shinychat._chat_types import (
    ChatMessage,
    ChatMessageDict,
    Role,
    StoredMessage,
)
from shinychat._utils_types import MISSING

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"

    def on_ended(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass


test_session = cast(Session, _MockSession())


# Check if a type is part of a Union
def is_type_in_union(type: object, union: object) -> bool:
    origin = get_origin(union)
    # Handle both typing.Union and types.UnionType (from | operator in Python 3.10+)
    if origin is Union or origin is types.UnionType:
        return type in get_args(union)
    return False


def stored_message(content: str, role: Role) -> StoredMessage:
    return StoredMessage.from_chat_message(
        ChatMessage(content=content, role=role)
    )


def test_chat_user_input_no_longer_accepts_transform_argument():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError):
            cast(Any, chat.user_input)(transform=True)


def test_chat_message_trimming():
    with session_context(test_session):
        chat = Chat(id="chat")

        # Default tokenizer gives a token count
        def generate_content(token_count: int) -> str:
            n = int(token_count / 2)
            return " ".join(["foo" for _ in range(1, n)])

        msgs = (
            stored_message(
                content=generate_content(102),
                role="system",
            ),
        )

        # Throws since system message is too long
        with pytest.raises(ValueError):
            chat._trim_messages(msgs, token_limits=(100, 0), format=MISSING)

        msgs = (
            stored_message(content=generate_content(100), role="system"),
            stored_message(content=generate_content(2), role="user"),
        )

        # Throws since only the system message fits
        with pytest.raises(ValueError):
            chat._trim_messages(msgs, token_limits=(100, 0), format=MISSING)

        # Raising the limit should allow both messages to fit
        trimmed = chat._trim_messages(
            msgs, token_limits=(103, 0), format=MISSING
        )
        assert len(trimmed) == 2

        content1 = generate_content(100)
        content2 = generate_content(10)
        content3 = generate_content(2)

        msgs = (
            stored_message(
                content=content1,
                role="system",
            ),
            stored_message(
                content=content2,
                role="user",
            ),
            stored_message(
                content=content3,
                role="user",
            ),
        )

        # Should discard the 1st user message
        trimmed = chat._trim_messages(
            msgs, token_limits=(103, 0), format=MISSING
        )
        assert len(trimmed) == 2
        contents = [str(msg.content) for msg in trimmed]
        assert contents == [content1, content3]

        content1 = generate_content(50)
        content2 = generate_content(10)
        content3 = generate_content(50)
        content4 = generate_content(2)

        msgs = (
            stored_message(
                content=content1,
                role="system",
            ),
            stored_message(
                content=content2,
                role="user",
            ),
            stored_message(
                content=content3,
                role="system",
            ),
            stored_message(
                content=content4,
                role="user",
            ),
        )

        # Should discard the 1st user message
        trimmed = chat._trim_messages(
            msgs, token_limits=(103, 0), format=MISSING
        )
        assert len(trimmed) == 3
        contents = [str(msg.content) for msg in trimmed]
        assert contents == [content1, content3, content4]

        content1 = generate_content(50)
        content2 = generate_content(10)

        msgs = (
            stored_message(
                content=content1,
                role="assistant",
            ),
            stored_message(
                content=content2,
                role="user",
            ),
        )

        # Anthropic requires 1st message to be a user message
        trimmed = chat._trim_messages(
            msgs, token_limits=(30, 0), format="anthropic"
        )
        assert len(trimmed) == 1
        contents = [str(msg.content) for msg in trimmed]
        assert contents == [content2]


def test_stream_replace_discards_stale_html_dependencies():
    with session_context(test_session):
        chat = Chat(id="chat")
        captured: list[StoredMessage] = []

        custom_dep = HTMLDependency(
            name="custom-styled-card",
            version="1.0.0",
            source={"subdir": "."},
            stylesheet={"href": "custom.css"},
        )

        async def _noop_send(*args: object, **kwargs: object) -> None:
            return None

        def _capture_store(
            message: StoredMessage | ChatMessage,
            index: int | None = None,
            deps: list[HTMLDependency] | None = None,
        ) -> None:
            del index
            captured.append(chat._as_stored_message(message, deps=deps))

        chat._send_append_message = _noop_send  # type: ignore[method-assign]
        chat._store_message = _capture_store  # type: ignore[method-assign]
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            None
            if not deps
            else [
                {"name": dep.name, "version": dep.version} for dep in deps
            ]
        )

        async def _exercise_stream() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="stream-id"
            )
            await chat._append_message_chunk(
                TagList(custom_dep, tags.div("ephemeral")),
                chunk=True,
                stream_id="stream-id",
            )
            await chat._append_message_chunk(
                "final",
                chunk="end",
                operation="replace",
                stream_id="stream-id",
            )

        exc: list[BaseException] = []

        def _run_in_thread() -> None:
            try:
                asyncio.run(_exercise_stream())
            except BaseException as err:
                exc.append(err)

        thread = threading.Thread(target=_run_in_thread)
        thread.start()
        thread.join()

        if exc:
            raise exc[0]

        assert len(captured) == 1
        assert captured[0].content == "final"
        assert captured[0].html_deps is None


def test_chat_message_dicts_hide_html_deps_but_bookmark_dicts_keep_them():
    with session_context(test_session):
        chat = Chat(id="chat")
        expected_html_deps: list[dict[str, object]] = [
            {"name": "custom-styled-card", "version": "1.0.0"}
        ]
        chat._store_message(
            StoredMessage(
                content="Restored message",
                role="assistant",
                html_deps=expected_html_deps,
            )
        )

        assert chat._message_dicts() == (
            ChatMessageDict(content="Restored message", role="assistant"),
        )
        assert chat._stored_message_dicts() == (
            {
                "content": "Restored message",
                "role": "assistant",
                "html_deps": expected_html_deps,
            },
        )


# ------------------------------------------------------------------------------------
# Unit tests for message_content() and message_content_chunk().
#
# This is where we go from provider's response object to ChatMessage.
#
# The general idea is to check that the provider's output message type match our
# expectations. If these tests fail, it doesn't not necessarily mean that our code is
# wrong (i.e., updating the test may be sufficient), but we'll still want to be aware
# and double-check our code.
# ------------------------------------------------------------------------------------


def test_string_normalization():
    m = message_content("Hello world!")
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk("Hello world!")
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_dict_normalization():
    m = message_content({"content": "Hello world!", "role": "assistant"})
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk({"content": "Hello world!"})
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_chat_message_normalization():
    m = message_content(ChatMessage(content="Hello world!", role="assistant"))
    assert m.content == "Hello world!"
    assert m.role == "assistant"
    mc = message_content_chunk(ChatMessage(content="Hello world!"))
    assert mc.content == "Hello world!"
    assert mc.role == "assistant"


def test_tagifiable_normalization():
    from shiny.ui import HTML, div

    # Interpreted as markdown (without escaping)
    m = message_content("Hello <span>world</span>!")
    assert m.content == "Hello <span>world</span>!"
    assert m.role == "assistant"

    # Interpreted as HTML (without escaping)
    m = message_content(HTML("Hello <span>world</span>!"))
    assert (
        m.content
        == "\n\n<shinychat-raw-html>Hello <span>world</span>!</shinychat-raw-html>\n\n"
    )
    assert m.role == "assistant"

    # Interpreted as HTML (if top-level object is tag-like, inner string contents get escaped)
    m = message_content(div("Hello <span>world</span>!"))
    assert (
        m.content
        == "\n\n<shinychat-raw-html>\n  <div>Hello &lt;span&gt;world&lt;/span&gt;!</div>\n</shinychat-raw-html>\n\n"
    )
    assert m.role == "assistant"


def test_langchain_normalization():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage, BaseMessageChunk

    # Make sure return type of the .invoke()/.stream() methods haven't changed
    # (If they do, we may need to update the mock and normalization functions)
    assert BaseChatModel.invoke.__annotations__["return"] == "AIMessage"
    assert (
        BaseChatModel.stream.__annotations__["return"]
        == "Iterator[AIMessageChunk]"
    )

    # Mock & normalize return value of BaseChatModel.invoke()
    msg = BaseMessage(content="Hello world!", role="assistant", type="foo")
    m = message_content(msg)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock & normalize return value of BaseChatModel.stream()
    chunk = BaseMessageChunk(content="Hello ", type="foo")
    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_google_content_object_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai import types

    # Test Content object normalization
    c = types.Content(parts=[types.Part(text="Hello world!")], role="model")
    m = message_content(c)
    assert m.content == "Hello world!"
    assert m.role == "assistant"


def test_google_multimodal_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai import types

    # Text part, image part, text part.
    c = types.Content(
        parts=[
            types.Part(text="Here is an image:"),
            types.Part(inline_data=types.Blob(mime_type="image/png", data=b"AAAA")),
            types.Part(text=" described above."),
        ],
        role="model",
    )

    m = message_content(c)
    assert m.content == "Here is an image: described above."
    assert m.role == "assistant"


def test_google_normalization():
    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai.models import Models
    from google.genai.types import GenerateContentResponse

    assert (
        inspect.signature(Models.generate_content).return_annotation
        == GenerateContentResponse
    )


def test_anthropic_normalization():
    if sys.version_info < (3, 11):
        pytest.skip("Anthropic is only available for Python 3.11+")

    from anthropic import (  # pyright: ignore[reportMissingImports]
        Anthropic,
        AsyncAnthropic,
    )
    from anthropic.resources.messages import (  # pyright: ignore[reportMissingImports]
        AsyncMessages,
        Messages,
    )
    from anthropic.types import (  # pyright: ignore[reportMissingImports]
        TextBlock,
        Usage,
    )
    from anthropic.types.message import (  # pyright: ignore[reportMissingImports]
        Message,
    )
    from anthropic.types.raw_content_block_delta_event import (  # pyright: ignore[reportMissingImports]
        RawContentBlockDeltaEvent,
    )
    from anthropic.types.text_delta import (  # pyright: ignore[reportMissingImports]
        TextDelta,
    )

    # Make sure return type of Anthropic().messages.create() hasn't changed
    assert isinstance(Anthropic().messages, Messages)
    assert isinstance(AsyncAnthropic().messages, AsyncMessages)

    # Make sure return type of llm.messages.create() hasn't changed
    assert (
        AsyncMessages.create.__annotations__["return"]
        == "Message | AsyncStream[RawMessageStreamEvent]"
    )
    assert (
        Messages.create.__annotations__["return"]
        == "Message | Stream[RawMessageStreamEvent]"
    )

    # Mock return object from Anthropic().messages.create()
    msg = Message(
        content=[
            TextBlock(type="text", text="Hello world!"),
        ],
        role="assistant",
        id="foo",
        type="message",
        model="foo",
        usage=Usage(input_tokens=0, output_tokens=0),
    )

    m = message_content(msg)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock return object from Anthropic().messages.create(stream=True)
    chunk = RawContentBlockDeltaEvent(
        delta=TextDelta(type="text_delta", text="Hello "),
        type="content_block_delta",
        index=0,
    )

    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_openai_normalization():
    import openai.types.chat.chat_completion as cc
    import openai.types.chat.chat_completion_chunk as ccc
    from openai import AsyncOpenAI, OpenAI
    from openai.resources.chat.completions import AsyncCompletions, Completions
    from openai.types.chat import (
        ChatCompletion,
        ChatCompletionChunk,
        ChatCompletionMessage,
    )

    # Make sure return type of OpenAI().chat.completions hasn't changed
    assert isinstance(OpenAI(api_key="fake").chat.completions, Completions)
    assert isinstance(
        AsyncOpenAI(api_key="fake").chat.completions, AsyncCompletions
    )

    assert (
        Completions.create.__annotations__["return"]
        == "ChatCompletion | Stream[ChatCompletionChunk]"
    )
    assert (
        AsyncCompletions.create.__annotations__["return"]
        == "ChatCompletion | AsyncStream[ChatCompletionChunk]"
    )

    # Mock return object from OpenAI().chat.completions.create()
    completion = ChatCompletion(
        id="foo",
        model="gpt-4",
        object="chat.completion",
        choices=[
            cc.Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    content="Hello world!",
                    role="assistant",
                ),
            )
        ],
        created=int(datetime.now().timestamp()),
    )

    m = message_content(completion)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    # Mock return object from OpenAI().chat.completions.create(stream=True)
    chunk = ChatCompletionChunk(
        id="foo",
        object="chat.completion.chunk",
        model="gpt-4o",
        created=int(datetime.now().timestamp()),
        choices=[
            ccc.Choice(
                index=0,
                delta=ccc.ChoiceDelta(
                    content="Hello ",
                    role="assistant",
                ),
            )
        ],
    )

    m = message_content_chunk(chunk)
    assert m.content == "Hello "
    assert m.role == "assistant"


def test_ollama_normalization():
    from ollama import ChatResponse
    from ollama import Message as OllamaMessage

    # Mock return object from ollama.chat()
    msg = ChatResponse(
        message=OllamaMessage(content="Hello world!", role="assistant"),
    )

    msg_dict = {"content": "Hello world!", "role": "assistant"}
    m = message_content(msg)
    assert m.content == msg_dict["content"]
    assert m.role == msg_dict["role"]

    m = message_content_chunk(msg)
    assert m.content == msg_dict["content"]
    assert m.role == msg_dict["role"]


# ------------------------------------------------------------------------------------
# Unit tests for as_provider_message()
#
# This is where we go from our ChatMessage to a provider's message object
#
# The general idea is to check that the provider's input message type match our
# expectations. If these tests fail, it doesn't not necessarily mean that our code is
# wrong (i.e., updating the test may be sufficient), but we'll still want to be aware
# and double-check our code.
# ------------------------------------------------------------------------------------


def test_as_anthropic_message():
    if sys.version_info < (3, 11):
        pytest.skip("Anthropic is only available for Python 3.11+")

    from anthropic.resources.messages import (  # pyright: ignore[reportMissingImports]
        AsyncMessages,
        Messages,
    )
    from anthropic.types import (  # pyright: ignore[reportMissingImports]
        MessageParam,
    )
    from shinychat._chat_provider_types import as_anthropic_message

    # Make sure return type of llm.messages.create() hasn't changed
    assert (
        AsyncMessages.create.__annotations__["messages"]
        == "Iterable[MessageParam]"
    )
    assert (
        Messages.create.__annotations__["messages"] == "Iterable[MessageParam]"
    )

    msg = ChatMessageDict(content="I have a question", role="user")
    assert as_anthropic_message(msg) == MessageParam(
        content="I have a question", role="user"
    )


def test_as_google_message():
    from shinychat._chat_provider_types import as_google_message

    # Not available for Python 3.9
    if sys.version_info < (3, 10):
        return

    from google.genai import types
    from google.genai.models import Models

    contents_annotation = (
        inspect.signature(Models.generate_content).parameters["contents"].annotation
    )
    assert is_type_in_union(types.Content, contents_annotation)

    msg = ChatMessageDict(content="I have a question", role="user")
    assert as_google_message(msg) == types.Content(
        parts=[types.Part(text="I have a question")], role="user"
    )


def test_as_langchain_message():
    from langchain_core.language_models.base import LanguageModelInput
    from langchain_core.language_models.base import (
        Sequence as LangchainSequence,  # pyright: ignore[reportPrivateImportUsage]
    )
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        MessageLikeRepresentation,
        SystemMessage,
    )
    from shinychat._chat_provider_types import as_langchain_message

    assert BaseChatModel.invoke.__annotations__["input"] == "LanguageModelInput"
    assert BaseChatModel.stream.__annotations__["input"] == "LanguageModelInput"

    assert is_type_in_union(
        # Use `LangchainSequence` instead of `Sequence` to avoid incorrect comparison
        # between `typing.Sequence` and `collections.abc.Sequence`
        LangchainSequence[MessageLikeRepresentation],
        LanguageModelInput,
    )
    assert is_type_in_union(BaseMessage, MessageLikeRepresentation)

    assert issubclass(AIMessage, BaseMessage)
    assert issubclass(HumanMessage, BaseMessage)
    assert issubclass(SystemMessage, BaseMessage)

    msg = ChatMessageDict(content="I have a question", role="user")
    assert as_langchain_message(msg) == HumanMessage(
        content="I have a question"
    )


def test_as_openai_message():
    from openai.resources.chat.completions import AsyncCompletions, Completions
    from openai.types.chat import (
        ChatCompletionAssistantMessageParam,
        ChatCompletionMessageParam,
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
    )
    from shinychat._chat_provider_types import as_openai_message

    assert (
        Completions.create.__annotations__["messages"]
        == "Iterable[ChatCompletionMessageParam]"
    )

    assert (
        AsyncCompletions.create.__annotations__["messages"]
        == "Iterable[ChatCompletionMessageParam]"
    )

    assert is_type_in_union(
        ChatCompletionAssistantMessageParam, ChatCompletionMessageParam
    )
    assert is_type_in_union(
        ChatCompletionSystemMessageParam, ChatCompletionMessageParam
    )
    assert is_type_in_union(
        ChatCompletionUserMessageParam, ChatCompletionMessageParam
    )

    msg = ChatMessageDict(content="I have a question", role="user")
    assert as_openai_message(msg) == ChatCompletionUserMessageParam(
        content="I have a question", role="user"
    )


def test_as_ollama_message():
    import ollama
    from ollama import Message as OllamaMessage

    assert "ollama._types.Message" in str(
        ollama.chat.__annotations__["messages"]
    )

    from shinychat._chat_provider_types import as_ollama_message

    msg = ChatMessageDict(content="I have a question", role="user")
    assert as_ollama_message(msg) == OllamaMessage(
        content="I have a question", role="user"
    )


class MyObject:
    content = "Hello world!"


class MyObjectChunk:
    content = "Hello world!"


@message_content.register
def _(message: MyObject) -> ChatMessage:
    return ChatMessage(content=message.content, role="assistant")


@message_content_chunk.register
def _(chunk: MyObjectChunk) -> ChatMessage:
    return ChatMessage(content=chunk.content, role="assistant")


def test_custom_objects():
    obj = MyObject()
    m = message_content(obj)
    assert m.content == "Hello world!"
    assert m.role == "assistant"

    chunk = MyObjectChunk()
    m = message_content_chunk(chunk)
    assert m.content == "Hello world!"
    assert m.role == "assistant"
