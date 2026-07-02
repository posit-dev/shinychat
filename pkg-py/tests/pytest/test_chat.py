from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from datetime import datetime
from typing import Any, cast

import pytest
from htmltools import HTMLDependency, TagList, tags
from shiny import Session, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_normalize import message_content, message_content_chunk
from shinychat._chat_types import (
    ChatMessage,
    ChatMessageDict,
    Role,
    StoredMessage,
    StoredSegment,
)
from shinychat._utils_types import MISSING

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    input: Any

    def __init__(self) -> None:
        from shiny import Inputs

        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


test_session = cast(Session, _MockSession())


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


def test_messages_format_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="format.*removed"):
            chat.messages(format="openai")  # type: ignore[arg-type]


def test_messages_token_limits_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="token_limits.*removed"):
            chat.messages(token_limits=(100, 0))  # type: ignore[arg-type]


def test_tokenizer_raises():
    with session_context(test_session):
        with pytest.raises(TypeError, match="tokenizer.*removed"):
            Chat(id="chat", tokenizer=object())  # type: ignore[arg-type]


def test_transform_user_input_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="transform_user_input.*removed"):
            chat.transform_user_input(lambda x: x)


def test_stream_replace_discards_stale_html_dependencies():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        custom_dep = HTMLDependency(
            name="custom-styled-card",
            version="1.0.0",
            source={"subdir": "."},
            stylesheet={"href": "custom.css"},
        )

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]
        chat._serialize_html_deps = lambda deps: (  # type: ignore[method-assign]
            None
            if not deps
            else [{"name": dep.name, "version": dep.version} for dep in deps]
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

        run_async(_exercise_stream)

        # The `chunk="end", operation="replace"` send is the "chunk" action
        # carrying the replaced content; find it and confirm the stale
        # dependency from the earlier chunk didn't survive the replace.
        replace_sends = [
            s
            for s in sent
            if s["action"]["type"] == "chunk"
            and s["action"]["operation"] == "replace"
        ]
        assert len(replace_sends) == 1
        final_send = replace_sends[0]
        assert final_send["action"]["content"] == "final"
        dep_names = [d["name"] for d in (final_send["deps"] or [])]
        assert "custom-styled-card" not in dep_names


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
            types.Part(
                inline_data=types.Blob(mime_type="image/png", data=b"AAAA")
            ),
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


def test_stored_message_content_joins_segments():
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="a ", content_type="markdown"),
            StoredSegment(content="<b>b</b>", content_type="html"),
        ],
    )
    assert msg.content == "a <b>b</b>"


def test_stored_message_from_chat_message_makes_one_segment():
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(content="hi", role="assistant")
    )
    assert len(sm.segments) == 1
    seg0 = sm.segments[0]
    assert isinstance(seg0, StoredSegment)
    assert seg0.content == "hi"
    assert seg0.content_type == "markdown"


def test_stored_message_from_chat_message_preserves_content_type():
    from htmltools import HTML
    from shinychat._chat_types import ChatMessage, StoredMessage

    html_msg = ChatMessage(content=HTML("<b>bold</b>"), role="assistant")
    sm_html = StoredMessage.from_chat_message(html_msg)
    assert isinstance(sm_html.segments[0], StoredSegment)
    assert sm_html.segments[0].content_type == "html"

    thinking_msg = ChatMessage(
        content="reasoning", role="assistant", content_type="thinking"
    )
    sm_thinking = StoredMessage.from_chat_message(thinking_msg)
    assert isinstance(sm_thinking.segments[0], StoredSegment)
    assert sm_thinking.segments[0].content_type == "thinking"


def test_slash_command_errors_on_duplicate_name():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        with pytest.raises(ValueError, match="already registered"):
            chat.slash_command("greet", "Say hi", fn=lambda: None)


def test_slash_command_allows_overwrite_with_force():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        chat.slash_command("greet", "Say hi", fn=lambda: None, force=True)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["greet"].definition["description"] == "Say hi"


def test_slash_command_remove():
    with session_context(test_session):
        chat = Chat(id="chat")
        remove = chat.slash_command("greet", "Say hello", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "greet" in cmds

        remove()
        with reactive.isolate():
            assert "greet" not in (chat._slash_commands() or {})

        # After removal, re-registering without force should succeed
        chat.slash_command("greet", "Say hello again", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["greet"].definition["description"] == "Say hello again"


def test_slash_command_remove_by_name():
    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("greet", "Say hello", fn=lambda: None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "greet" in cmds

        chat.remove_slash_command("greet")
        with reactive.isolate():
            assert "greet" not in (chat._slash_commands() or {})

        # Removing a non-existent command is a no-op
        chat.remove_slash_command("greet")


def test_slash_command_echo_defaults_to_handler_presence():
    with session_context(test_session):
        chat = Chat(id="chat")

        @chat.slash_command("withhandler", "Has a handler")
        async def _():
            ...

        chat.slash_command("nohandler", "No handler", fn=None)

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["withhandler"].definition["echo"] is True
            assert cmds["nohandler"].definition["echo"] is False
            assert cmds["nohandler"].handler is None


def test_slash_command_echo_explicit_override():
    with session_context(test_session):
        chat = Chat(id="chat")

        @chat.slash_command("sideeffect", "Side effect only", echo=False)
        async def _():
            ...

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["sideeffect"].definition["echo"] is False
            assert cmds["sideeffect"].handler is not None


def test_slash_command_fn_none_returns_remover():
    with session_context(test_session):
        chat = Chat(id="chat")

        remove = chat.slash_command("temp", "Temp", fn=None)
        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert "temp" in cmds
        remove()
        with reactive.isolate():
            assert "temp" not in (chat._slash_commands() or {})


def test_slash_command_fn_none_with_explicit_echo_true():
    with session_context(test_session):
        chat = Chat(id="chat")

        chat.slash_command("clientecho", "Client-side but echoed", fn=None, echo=True)

        with reactive.isolate():
            cmds = chat._slash_commands()
            assert cmds is not None
            assert cmds["clientecho"].definition["echo"] is True
            assert cmds["clientecho"].handler is None


def test_bookmark_round_trips_echoed_slash_command():
    # An echoed slash command stores the `/cmd args` text as a normal user
    # message (mirroring `_on_slash_command`), so it rides the generic
    # stored-message bookmark mechanism: saved, then restored as a static entry.
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        # `_messages_for_bookmark()` reads the client-reported snapshot input,
        # not the server-side append log, so seed that input directly.
        reported = (
            chat._as_stored_message(ChatMessage(content="/greet world", role="user")),
            chat._as_stored_message(
                ChatMessage(content="Hello! You said: world", role="assistant")
            ),
        )
        test_session.input[chat.messages_input_id]._set(reported)
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {"role": "user", "segments": [{"content": "/greet world", "content_type": "markdown"}]},
        {"role": "assistant", "segments": [{"content": "Hello! You said: world", "content_type": "markdown"}]},
    ]

    async def restore() -> list[tuple[Role, str]]:
        with session_context(test_session):
            restored = Chat(id="chat_restored")
            sent: list[dict[str, Any]] = []

            async def _capture(action: Any, deps: Any = None) -> None:
                sent.append(action)

            restored._send_action = _capture  # type: ignore[method-assign]

            for message_dict in saved:
                await restored._restore_bookmark_message(message_dict)

            # `_restore_bookmark_message` re-sends each message to the client
            # (which re-reports it into the messages snapshot on render); the
            # server no longer keeps its own append log to read back from.
            return [
                (cast(Role, a["message"]["role"]), a["message"]["segments"][0]["content"])
                for a in sent
                if a["type"] == "message"
            ]

    result: list[tuple[Role, str]] = []

    async def run() -> None:
        result.extend(await restore())

    run_async(run)

    assert result == [
        ("user", "/greet world"),
        ("assistant", "Hello! You said: world"),
    ]


def test_bookmark_omits_side_effect_only_slash_command():
    # A side-effect-only command (echo=False) never reports anything to the
    # client, so it never contributes to the bookmark even though its
    # handler runs.
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        chat.slash_command("note", "Side-effect only", echo=False)
        # `_messages_for_bookmark()` reads the client-reported snapshot
        # input, not the server-side append log, so seed that input
        # directly with only the explicit message (the echo=False command
        # reports nothing).
        reported = (chat._as_stored_message(ChatMessage(content="real message", role="user")),)
        test_session.input[chat.messages_input_id]._set(reported)
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {"role": "user", "segments": [{"content": "real message", "content_type": "markdown"}]},
    ]


def test_user_input_reads_latest_stored():
    from shiny import reactive
    from shinychat._chat import UserInput

    session = cast(Session, _MockSession())

    with session_context(session):
        chat = Chat(id="chat")

        with reactive.isolate():
            assert chat.user_input() is None

            from shinychat._attachments import Attachment
            from shinychat._chat_types import ChatMessage, StoredMessage

            attachments = [
                Attachment(
                    mime="image/png",
                    data_url="data:image/png;base64,AAA",
                    name="a.png",
                )
            ]
            stored = StoredMessage.from_chat_message(
                ChatMessage(content="hi", role="user", attachments=attachments)
            )
            chat._latest_user_input.set(stored)
            result = chat.user_input()
            assert result == UserInput(text="hi", attachments=attachments)
            assert result is not None
            text, atts = result
            assert text == "hi"
            assert atts == attachments


def test_chat_ui_allow_attachments_attribute():
    from shinychat import chat_ui

    def attachment_attr(ui_tag: object) -> object:
        return ui_tag.attrs.get("allow-attachments")  # type: ignore[attr-defined]

    assert attachment_attr(chat_ui("c", allow_attachments=MISSING)) is None
    assert attachment_attr(chat_ui("c", allow_attachments=True)) == "true"
    assert attachment_attr(chat_ui("c", allow_attachments=False)) == "false"


def test_chat_ui_accept_list_and_max_attachment_size(
    monkeypatch: pytest.MonkeyPatch,
):
    from shinychat import chat_ui

    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "5000000")
    tag = chat_ui("c", allow_attachments=["application/pdf"])
    assert tag.attrs.get("allow-attachments") == "true"
    assert tag.attrs.get("attachment-accept") == "application/pdf"
    assert tag.attrs.get("max-attachment-size") == "5000000"

    with pytest.raises(ValueError):
        chat_ui("c", allow_attachments=["application/msword"])


def test_user_submit_function_union_includes_two_arg_form():
    from typing import get_args

    from shinychat._chat import UserSubmitFunction, UserSubmitFunction2

    two_arg_forms = get_args(UserSubmitFunction2)
    top_level_forms = get_args(UserSubmitFunction)
    assert all(form in top_level_forms for form in two_arg_forms)


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


def test_stream_thinking_creates_thinking_segment():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk(
                "answer", chunk=True, stream_id="s1"
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        # Each chunk is sent individually on the wire; the client assembles
        # segments from the (content, content_type) pairs of each chunk.
        chunk_actions = [
            s["action"] for s in sent if s["action"]["type"] == "chunk"
        ]
        by_content = {a["content"]: a["content_type"] for a in chunk_actions}
        assert by_content["reasoning"] == "thinking"
        assert by_content["answer"] == "markdown"


def test_thinking_stream_stores_segment_not_tags():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append({"action": action, "deps": deps})

        chat._send_action = _capture  # type: ignore[method-assign]

        async def gen():
            yield ChatMessage(
                content="thinking hard",
                role="assistant",
                content_type="thinking",
            )
            yield "the answer"

        async def _exercise() -> None:
            await chat.append_message_stream(gen())

        run_async(_exercise)

        # The thinking chunk must travel as bare content paired with
        # content_type="thinking" -- not wrapped in literal <thinking> tags.
        chunk_actions = [
            s["action"] for s in sent if s["action"]["type"] == "chunk"
        ]
        thinking_actions = [
            a for a in chunk_actions if a["content_type"] == "thinking"
        ]
        assert len(thinking_actions) == 1
        assert thinking_actions[0]["content"] == "thinking hard"
        assert all("<thinking>" not in a["content"] for a in chunk_actions)


def test_send_message_payload_has_segments_with_thinking():
    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]
        stored = StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="reasoning", content_type="thinking"),
                StoredSegment(content="answer", content_type="markdown"),
            ],
        )

        async def _exercise() -> None:
            await chat._send_append_message(stored)

        run_async(_exercise)
        assert sent[0]["type"] == "message"
        assert sent[0]["message"]["segments"] == [
            {"content": "reasoning", "content_type": "thinking"},
            {"content": "answer", "content_type": "markdown"},
        ]


def test_bookmark_roundtrip_thinking_segment():
    from shiny import reactive

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]
        # `_messages_for_bookmark()` reads the client-reported snapshot
        # input, not the server-side append log, so seed that input
        # directly.
        reported = (
            StoredMessage(
                role="assistant",
                segments=[
                    StoredSegment(content="reasoning", content_type="thinking"),
                    StoredSegment(content="answer", content_type="markdown"),
                ],
            ),
        )
        test_session.input[chat.messages_input_id]._set(reported)
        with reactive.isolate():
            saved = chat._messages_for_bookmark()
        assert saved[0]["segments"][0]["content_type"] == "thinking"

        async def _exercise() -> None:
            await chat._restore_bookmark_message(saved[0])

        run_async(_exercise)
        assert sent[0]["type"] == "message"
        assert sent[0]["message"]["segments"][0]["content_type"] == "thinking"


def test_send_append_message_serializes_attachments():
    """Attachments in the outgoing payload must be plain dicts, not Attachment objects.

    json.dumps (used by Shiny's send_custom_message) cannot serialize Pydantic
    models, so _send_append_message must call model_dump() before building the
    wire payload.
    """
    import json

    from shinychat._attachments import Attachment

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        att = Attachment.from_data(b"hello", mime="text/plain", name="hello.txt")
        stored = StoredMessage(
            role="assistant",
            segments=[StoredSegment(content="here you go", content_type="markdown")],
            attachments=[att],
        )

        run_async(lambda: chat._send_append_message(stored))

        payload = sent[0]["message"]
        # Must not raise — the payload must be JSON-serializable.
        json.dumps(payload)

        # Attachments must arrive as plain dicts with the expected keys.
        assert payload["attachments"] == [
            {"mime": "text/plain", "name": "hello.txt", "size": 5, "data_url": att.data_url}
        ]


def test_stored_message_content_wraps_thinking_in_tags():
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content="reasoning", content_type="thinking"),
            StoredSegment(content="the answer", content_type="markdown"),
        ],
    )
    assert msg.content == "<thinking>\nreasoning\n</thinking>\n\nthe answer"


def test_append_message_stream_return_includes_tagged_thinking():
    # The single-string return value must agree with StoredMessage.content:
    # thinking is included, wrapped in <thinking> tags.
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")

        async def _noop_send(*a: object, **k: object) -> None:
            return None

        chat._send_action = _noop_send  # type: ignore[method-assign]

        async def gen():
            yield ChatMessage(
                content="reasoning", role="assistant", content_type="thinking"
            )
            yield "the answer"

        result: list[str] = []

        async def _exercise() -> None:
            result.append(await chat._append_message_stream(gen()))

        run_async(_exercise)
        assert result[0] == "<thinking>\nreasoning\n</thinking>\n\nthe answer"


def test_streaming_thinking_chunk_wire_content_not_empty():
    """Regression: a streamed thinking chunk must carry its text on the wire.

    The streaming chunk action's `content` must include the thinking text or the
    client renders an empty thinking panel.
    """
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        thinking_chunks = [
            a
            for a in sent
            if a.get("type") == "chunk" and a.get("content_type") == "thinking"
        ]
        assert thinking_chunks, "no thinking chunk action was sent"
        assert thinking_chunks[0]["content"] == "reasoning"


def test_streaming_chunk_content_type_follows_segment():
    """Each streamed chunk action carries the content_type of its own segment.

    Pins the wire content_type derivation across a mixed thinking->markdown
    stream so it stays correct after _send_append_message infers the type
    from the message segments rather than an explicitly threaded argument.
    """
    from shinychat._chat_types import ChatMessage

    with session_context(test_session):
        chat = Chat(id="chat")
        sent: list[dict[str, Any]] = []

        async def _capture(action: Any, deps: Any = None) -> None:
            sent.append(action)

        chat._send_action = _capture  # type: ignore[method-assign]

        async def _exercise() -> None:
            await chat._append_message_chunk("", chunk="start", stream_id="s1")
            await chat._append_message_chunk(
                ChatMessage(
                    content="reasoning",
                    role="assistant",
                    content_type="thinking",
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk(
                ChatMessage(
                    content="answer", role="assistant", content_type="markdown"
                ),
                chunk=True,
                stream_id="s1",
            )
            await chat._append_message_chunk("", chunk="end", stream_id="s1")

        run_async(_exercise)

        chunk_types = [
            (a["content"], a["content_type"])
            for a in sent
            if a.get("type") == "chunk"
        ]
        assert ("reasoning", "thinking") in chunk_types
        assert ("answer", "markdown") in chunk_types


def test_stored_message_attachments_stored_separately():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    msg = StoredMessage(
        role="user",
        segments=[StoredSegment(content="see this", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:image/png;base64,AAAA",
                name="chart.png",
                mime="image/png",
                size=3,
            )
        ],
    )
    assert msg.content == "see this"
    assert len(msg.attachments) == 1
    assert msg.attachments[0].name == "chart.png"


def test_chat_message_attachments_become_stored_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(
            content="here",
            role="assistant",
            attachments=[Attachment.from_data(b"x", mime="image/png", name="c.png")],
        )
    )
    assert len(sm.segments) == 1
    assert len(sm.attachments) == 1
    assert sm.attachments[0].name == "c.png"


def test_user_message_with_attachments_stores_correctly():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage, StoredMessage

    sm = StoredMessage.from_chat_message(
        ChatMessage(
            content="look",
            role="user",
            attachments=[Attachment.from_data(b"x", mime="image/png", name="c.png")],
        )
    )
    assert len(sm.segments) == 1
    assert len(sm.attachments) == 1
    assert sm.content == "look"


def test_bookmark_roundtrip_preserves_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    stored = StoredMessage(
        role="user",
        segments=[StoredSegment(content="look", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:image/png;base64,AAAA",
                name="c.png",
                mime="image/png",
                size=3,
            )
        ],
    )
    dumped = stored.model_dump(exclude_none=True)
    restored = StoredMessage.model_validate(dumped)
    assert len(restored.attachments) == 1
    assert restored.attachments[0].name == "c.png"
    assert restored.content == "look"


def test_wire_segments_excludes_attachments():
    from shinychat._attachments import Attachment
    from shinychat._chat_types import StoredMessage, StoredSegment

    stored = StoredMessage(
        role="assistant",
        segments=[StoredSegment(content="hi", content_type="markdown")],
        attachments=[
            Attachment(
                data_url="data:,x",
                name="c.png",
                mime="image/png",
                size=1,
            )
        ],
    )
    segs = stored.wire_segments()
    assert len(segs) == 1
    assert segs[0] == {"content": "hi", "content_type": "markdown"}
    assert len(stored.attachments) == 1
    assert stored.attachments[0].name == "c.png"


def test_messages_surfaces_attachments():
    from shiny import reactive
    from shinychat._attachments import Attachment
    from shinychat._chat_types import ChatMessage, StoredMessage

    with session_context(test_session):
        chat = Chat(id="chat")

        # `.messages()` reads the client-reported snapshot input, not the
        # server-side append log, so seed that input directly.
        reported = (
            StoredMessage.from_chat_message(
                ChatMessage(
                    "see attached",
                    role="assistant",
                    attachments=[
                        Attachment.from_data(
                            b"\x89PNG\r\n", mime="image/png", name="a.png"
                        ),
                    ],
                )
            ),
            StoredMessage.from_chat_message(ChatMessage("plain text", role="assistant")),
        )
        # Input values are read-only from application code; `_set()` is the
        # same mechanism Shiny itself uses to deliver client-reported values.
        test_session.input[chat.messages_input_id]._set(reported)

        with reactive.isolate():
            msgs = chat.messages()

        # First message: assistant with attachment. No `format=` was passed, so
        # messages() returns ChatMessageDict entries.
        att_msg = cast(ChatMessageDict, msgs[0])
        assert "attachments" in att_msg
        atts = att_msg["attachments"]
        assert len(atts) == 1
        assert atts[0].mime == "image/png"
        assert atts[0].name == "a.png"
        assert atts[0].data_url.startswith("data:image/png;base64,")

        # Second message: plain text — no attachments key
        assert "attachments" not in msgs[1]
