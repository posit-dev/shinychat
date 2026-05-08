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
    StoredContentSegment,
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


def run_async(coro_fn: Any) -> None:
    exc: list[BaseException] = []

    def _run() -> None:
        try:
            asyncio.run(coro_fn())
        except BaseException as err:
            exc.append(err)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exc:
        raise exc[0]


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


def test_stream_accumulates_segments_by_content_type():
    """Chunks with different content types create separate segments."""
    from htmltools import HTML

    with session_context(test_session):
        chat = Chat(id="chat")
        captured: list[StoredMessage] = []

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

        async def _exercise_stream() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="s1"
            )
            # Markdown chunk
            await chat._append_message_chunk(
                "hello ", chunk=True, stream_id="s1"
            )
            # Another markdown chunk (same type, should merge)
            await chat._append_message_chunk(
                "world", chunk=True, stream_id="s1"
            )
            # HTML chunk (different type, new segment)
            await chat._append_message_chunk(
                HTML("<b>!</b>"), chunk=True, stream_id="s1"
            )
            await chat._append_message_chunk(
                "", chunk="end", stream_id="s1"
            )

        run_async(_exercise_stream)

        assert len(captured) == 1
        msg = captured[0]
        assert msg.segments is not None
        assert len(msg.segments) == 2
        assert msg.segments[0]["content"] == "hello world"
        assert msg.segments[0]["content_type"] == "markdown"
        assert msg.segments[1]["content"] == "<b>!</b>"
        assert msg.segments[1]["content_type"] == "html"
        # Flat content is the join of all segments
        assert str(msg.content) == "hello world<b>!</b>"


def test_messages_for_bookmark_includes_segments():
    with session_context(test_session):
        chat = Chat(id="chat")

        seg1 = StoredContentSegment(content="hello ", content_type="markdown")
        seg2 = StoredContentSegment(content="<b>world</b>", content_type="html")

        chat._store_message(
            StoredMessage(
                content="hello <b>world</b>",
                role="assistant",
                segments=[seg1, seg2],
            )
        )

        result = chat._messages_for_bookmark()
        assert len(result) == 1
        msg = result[0]
        assert msg["content"] == "hello <b>world</b>"
        assert msg["role"] == "assistant"
        assert "segments" in msg
        assert len(msg["segments"]) == 2
        assert msg["segments"][0]["content_type"] == "markdown"
        assert msg["segments"][1]["content_type"] == "html"
        # When segments exist, top-level html_deps should NOT be present
        # (deps live per-segment to avoid double-sending on restore)
        assert "html_deps" not in msg


def test_messages_for_bookmark_without_segments():
    """Messages without segments still serialize correctly (legacy path)."""
    with session_context(test_session):
        chat = Chat(id="chat")

        chat._store_message(
            StoredMessage(content="plain text", role="user")
        )

        result = chat._messages_for_bookmark()
        assert len(result) == 1
        msg = result[0]
        assert msg["content"] == "plain text"
        assert msg["role"] == "user"
        assert "segments" not in msg


def test_restore_message_with_segments_sends_single_message():
    """Messages with segments restore as a single 'message' action carrying segments."""
    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]

        bookmark_data = {
            "content": "hello <b>world</b>",
            "role": "assistant",
            "segments": [
                {"content": "hello ", "content_type": "markdown"},
                {"content": "<b>world</b>", "content_type": "html"},
            ],
        }

        async def _exercise() -> None:
            await chat._restore_bookmark_message(bookmark_data)

        run_async(_exercise)

        assert len(sent_actions) == 1
        assert sent_actions[0]["type"] == "message"
        payload = sent_actions[0]["message"]
        assert payload["segments"] == [
            {"content": "hello ", "content_type": "markdown"},
            {"content": "<b>world</b>", "content_type": "html"},
        ]


def test_restore_legacy_message_without_segments():
    """Legacy bookmarks (no segments key) restore as a single complete message."""
    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]

        legacy_data = {"content": "hello world", "role": "assistant"}

        async def _exercise() -> None:
            await chat._restore_bookmark_message(legacy_data)

        run_async(_exercise)

        # Legacy: sent as a single complete message
        assert len(sent_actions) == 1
        assert sent_actions[0]["type"] == "message"


def test_send_message_includes_segments_in_payload():
    """When a StoredMessage has segments, the 'message' action payload includes them."""
    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]

        stored = StoredMessage(
            content="hello <b>world</b>",
            role="assistant",
            segments=[
                StoredContentSegment(content="hello ", content_type="markdown"),
                StoredContentSegment(content="<b>world</b>", content_type="html"),
            ],
        )

        async def _exercise() -> None:
            await chat._send_append_message(stored)

        run_async(_exercise)

        assert len(sent_actions) == 1
        assert sent_actions[0]["type"] == "message"
        payload = sent_actions[0]["message"]
        assert "segments" in payload
        assert payload["segments"] == [
            {"content": "hello ", "content_type": "markdown"},
            {"content": "<b>world</b>", "content_type": "html"},
        ]


def test_stream_html_deps_survive_segment_serialization():
    """HTML deps from a TagList chunk are preserved in the serialized segment."""
    with session_context(test_session):
        chat = Chat(id="chat")
        captured: list[StoredMessage] = []

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
            else [{"name": dep.name, "version": dep.version} for dep in deps]
        )

        custom_dep = HTMLDependency(
            name="my-widget", version="2.0", source={"subdir": "."}
        )

        async def _exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="s1"
            )
            await chat._append_message_chunk(
                TagList(custom_dep, tags.div("widget")),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk(
                "", chunk="end", stream_id="s1"
            )

        run_async(_exercise)

        assert len(captured) == 1
        msg = captured[0]
        assert msg.segments is not None
        assert len(msg.segments) == 1
        assert msg.segments[0]["content_type"] == "markdown"
        seg_deps = msg.segments[0].get("html_deps")
        assert seg_deps is not None
        assert seg_deps[0]["name"] == "my-widget"


def test_restore_single_segment_sends_single_message():
    """Single-segment messages also restore as a single 'message' action."""
    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]

        bookmark_data = {
            "content": "<div>only html</div>",
            "role": "assistant",
            "segments": [
                {"content": "<div>only html</div>", "content_type": "html"},
            ],
        }

        async def _exercise() -> None:
            await chat._restore_bookmark_message(bookmark_data)

        run_async(_exercise)

        assert len(sent_actions) == 1
        assert sent_actions[0]["type"] == "message"
        assert sent_actions[0]["message"]["segments"] == [
            {"content": "<div>only html</div>", "content_type": "html"},
        ]


def test_restore_segment_deps_hoisted_to_envelope():
    """Segment html_deps are hoisted to the envelope, not sent per-segment on the wire."""
    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []
        sent_deps: list[Any] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)
            sent_deps.append(deps)

        chat._send_action = _capture_send  # type: ignore[method-assign]

        bookmark_data = {
            "content": "<div>only html</div>",
            "role": "assistant",
            "segments": [
                {
                    "content": "<div>only html</div>",
                    "content_type": "html",
                    "html_deps": [{"name": "my-widget", "version": "1.0"}],
                },
            ],
        }

        async def _exercise() -> None:
            await chat._restore_bookmark_message(bookmark_data)

        run_async(_exercise)

        assert len(sent_actions) == 1
        assert sent_actions[0]["type"] == "message"
        # Wire segments should NOT contain html_deps
        for seg in sent_actions[0]["message"]["segments"]:
            assert "html_deps" not in seg
        # Deps hoisted to envelope
        assert sent_deps[0] == [{"name": "my-widget", "version": "1.0"}]


def test_nested_stream_checkpoint_preserves_segments():
    """Nested message_stream_context restores checkpoint segments correctly on replace."""
    with session_context(test_session):
        chat = Chat(id="chat")
        captured: list[StoredMessage] = []

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
            None if not deps else [{"name": d.name} for d in deps]
        )

        async def _exercise() -> None:
            async with chat.message_stream_context() as outer:
                await outer.append("before ")
                async with chat.message_stream_context() as inner:
                    await inner.append("ephemeral")
                    await inner.replace("replaced")
                await outer.append(" after")

        run_async(_exercise)

        assert len(captured) == 1
        msg = captured[0]
        assert str(msg.content) == "before replaced after"

        assert msg.segments is not None
        # All chunks are markdown, so they should merge into one segment
        assert len(msg.segments) == 1
        assert msg.segments[0]["content_type"] == "markdown"
        assert msg.segments[0]["content"] == "before replaced after"


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


def test_stream_sends_correct_content_type_per_chunk():
    """Each chunk sent to the client carries the content type of its segment."""
    from htmltools import HTML

    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]
        chat._store_message = lambda *a, **kw: None  # type: ignore[method-assign]
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            None if not deps else [{"name": d.name} for d in deps]
        )

        async def _exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="s1"
            )
            await chat._append_message_chunk(
                "markdown text", chunk=True, stream_id="s1"
            )
            await chat._append_message_chunk(
                HTML("<div>html</div>"), chunk=True, stream_id="s1"
            )
            await chat._append_message_chunk(
                "", chunk="end", stream_id="s1"
            )

        run_async(_exercise)

        # Filter to chunk actions (skip chunk_start, chunk_end)
        chunks = [a for a in sent_actions if a.get("type") == "chunk"]
        assert len(chunks) >= 2
        # First chunk is markdown
        assert chunks[0]["content_type"] == "markdown"
        # Second chunk is html
        assert chunks[1]["content_type"] == "html"


def test_stream_transform_uses_transformed_content_type():
    from htmltools import HTML

    with session_context(test_session):
        chat = Chat(id="chat")
        sent_actions: list[dict[str, Any]] = []

        async def _capture_send(action: Any, deps: Any = None) -> None:
            sent_actions.append(action)

        chat._send_action = _capture_send  # type: ignore[method-assign]
        chat._store_message = lambda *a, **kw: None  # type: ignore[method-assign]

        @chat.transform_assistant_response
        def transform(content: str, chunk: str, done: bool) -> str | HTML:
            del chunk
            if done:
                return HTML(f"<b>{content}</b>")
            return content

        async def _exercise() -> None:
            await chat._append_message_chunk(
                "", chunk="start", stream_id="s1"
            )
            await chat._append_message_chunk(
                "hello", chunk="end", stream_id="s1"
            )

        run_async(_exercise)

        chunks = [a for a in sent_actions if a.get("type") == "chunk"]
        assert len(chunks) == 1
        assert chunks[0]["content"] == "<b>hello</b>"
        assert chunks[0]["content_type"] == "html"
