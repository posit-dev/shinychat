from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from datetime import datetime
from typing import Any, AsyncIterator, cast

import pytest
from htmltools import HTML, HTMLDependency, TagList, tags
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

    def _decrement_busy_count(self) -> None:
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


def test_messages_input_id_is_an_inert_compatibility_field():
    with session_context(test_session):
        chat = Chat(id="chat", history=False)

        assert chat.messages_input_id == ResolvedId("chat_messages")
        test_session.input[chat.messages_input_id]._set(
            (stored_message("browser snapshot", "assistant"),)
        )

        with reactive.isolate():
            assert chat.messages() == ()


def test_tokenizer_raises():
    with session_context(test_session):
        with pytest.raises(TypeError, match="tokenizer.*removed"):
            Chat(id="chat", tokenizer=object())  # type: ignore[arg-type]


def test_transform_user_input_raises():
    with session_context(test_session):
        chat = Chat(id="chat")

        with pytest.raises(TypeError, match="transform_user_input.*removed"):
            chat.transform_user_input(lambda x: x)


def test_same_flush_append_message_updates_messages():
    with session_context(test_session):
        chat = Chat("chat", history=False)

        run_async(lambda: chat.append_message("server message"))

        with reactive.isolate():
            assert chat.messages() == (
                {"content": "server message", "role": "assistant"},
            )


def test_send_failure_does_not_append_message(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        chat = Chat("chat", history=False)

        run_async(lambda: chat.append_message("settled message"))

        async def send_failure(action: Any, deps: Any = None) -> None:
            raise RuntimeError("send failed")

        monkeypatch.setattr(chat, "_send_action", send_failure)

        with pytest.raises(RuntimeError, match="send failed"):
            run_async(lambda: chat.append_message("failed message"))

        with reactive.isolate():
            assert chat.messages() == (
                {"content": "settled message", "role": "assistant"},
            )


def test_stream_send_failures_do_not_commit_active_or_settled_state(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        failed_start = Chat("failed_start", history=False)

        async def fail_start(action: Any, deps: Any = None) -> None:
            raise RuntimeError("start failed")

        monkeypatch.setattr(failed_start, "_send_action", fail_start)
        with pytest.raises(RuntimeError, match="start failed"):
            run_async(
                lambda: failed_start._append_message_chunk(
                    "", chunk="start", stream_id="stream"
                )
            )
        assert failed_start._current_stream_id is None
        assert failed_start._current_stream_segments == []

        failed_chunk = Chat("failed_chunk", history=False)

        async def fail_chunk(action: Any, deps: Any = None) -> None:
            if action["type"] == "chunk":
                raise RuntimeError("chunk failed")

        monkeypatch.setattr(failed_chunk, "_send_action", fail_chunk)
        run_async(
            lambda: failed_chunk._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
        )
        with pytest.raises(RuntimeError, match="chunk failed"):
            run_async(
                lambda: failed_chunk._append_message_chunk(
                    "partial", chunk=True, stream_id="stream"
                )
            )
        assert failed_chunk._current_stream_id == "stream"
        assert failed_chunk._current_stream_segments == []

        failed_end = Chat("failed_end", history=False)

        async def succeed(action: Any, deps: Any = None) -> None:
            return None

        monkeypatch.setattr(failed_end, "_send_action", succeed)
        run_async(
            lambda: failed_end._append_message_chunk(
                "", chunk="start", stream_id="stream"
            )
        )
        run_async(
            lambda: failed_end._append_message_chunk(
                "partial", chunk=True, stream_id="stream"
            )
        )

        async def fail_end(action: Any, deps: Any = None) -> None:
            raise RuntimeError("end failed")

        monkeypatch.setattr(failed_end, "_send_action", fail_end)
        with pytest.raises(RuntimeError, match="end failed"):
            run_async(
                lambda: failed_end._append_message_chunk(
                    "", chunk="end", stream_id="stream"
                )
            )
        assert failed_end._current_stream_id is None
        assert failed_end._current_stream_segments == []
        with reactive.isolate():
            assert failed_end.messages() == ()


@pytest.mark.anyio
async def test_concurrent_stream_start_queues_other_streams_and_messages(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        chat = Chat("concurrent_start", history=False)
        first_start_sent = asyncio.Event()
        release_first_start = asyncio.Event()
        second_start_sent = asyncio.Event()
        message_sent = asyncio.Event()

        async def send_action(action: Any, deps: Any = None) -> None:
            if action["type"] == "chunk_start":
                if first_start_sent.is_set():
                    second_start_sent.set()
                    return
                first_start_sent.set()
                await release_first_start.wait()
            elif action["type"] == "message":
                message_sent.set()

        monkeypatch.setattr(chat, "_send_action", send_action)
        first_start = asyncio.create_task(
            chat._append_message_chunk("", chunk="start", stream_id="first")
        )
        await first_start_sent.wait()

        second_start = asyncio.create_task(
            chat._append_message_chunk("", chunk="start", stream_id="second")
        )
        await asyncio.sleep(0)
        queued_message = asyncio.create_task(chat.append_message("queued"))
        await asyncio.sleep(0)

        assert not second_start_sent.is_set()
        assert not message_sent.is_set()

        release_first_start.set()
        await asyncio.gather(first_start, second_start, queued_message)

        assert chat._current_stream_id == "first"
        assert chat._current_stream_segments == []
        assert chat._pending_messages == [
            ("", "start", "append", "second"),
            ("queued", False, "append", None),
        ]
        assert not second_start_sent.is_set()
        assert not message_sent.is_set()


@pytest.mark.anyio
async def test_concurrent_stream_chunks_commit_in_send_order(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        chat = Chat("concurrent_chunks", history=False)
        first_chunk_sent = asyncio.Event()
        release_first_chunk = asyncio.Event()
        second_chunk_sent = asyncio.Event()

        async def send_action(action: Any, deps: Any = None) -> None:
            if action["type"] != "chunk":
                return
            if action["content"] == "one":
                first_chunk_sent.set()
                await release_first_chunk.wait()
            if action["content"] == "two":
                second_chunk_sent.set()

        monkeypatch.setattr(chat, "_send_action", send_action)
        await chat._append_message_chunk("", chunk="start", stream_id="stream")
        first_chunk = asyncio.create_task(
            chat._append_message_chunk("one", chunk=True, stream_id="stream")
        )
        await first_chunk_sent.wait()

        second_chunk = asyncio.create_task(
            chat._append_message_chunk("two", chunk=True, stream_id="stream")
        )
        await asyncio.sleep(0)
        assert not second_chunk_sent.is_set()

        release_first_chunk.set()
        await asyncio.gather(first_chunk, second_chunk)

        assert [segment.content for segment in chat._current_stream_segments] == [
            "onetwo"
        ]
        assert second_chunk_sent.is_set()


def test_clear_messages_discards_active_and_pending_stream_state(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        chat = Chat("clear_state", history=False)
        state_during_clear: list[tuple[str | None, int, int]] = []

        async def send_action(action: Any, deps: Any = None) -> None:
            if action["type"] == "clear":
                state_during_clear.append(
                    (
                        chat._current_stream_id,
                        len(chat._current_stream_segments),
                        len(chat._pending_messages),
                    )
                )

        monkeypatch.setattr(chat, "_send_action", send_action)
        chat._store_message(stored_message("settled", "assistant"))
        run_async(
            lambda: chat._append_message_chunk(
                "", chunk="start", stream_id="active"
            )
        )
        run_async(
            lambda: chat._append_message_chunk(
                "draft", chunk=True, stream_id="active"
            )
        )
        run_async(
            lambda: chat._append_message_chunk(
                "queued", chunk=True, stream_id="other"
            )
        )

        run_async(chat.clear_messages)

        assert state_during_clear == [("active", 1, 1)]
        assert chat._current_stream_id is None
        assert chat._current_stream_segments == []
        assert chat._message_stream_segments_checkpoint == []
        assert chat._pending_messages == []
        with reactive.isolate():
            assert chat.messages() == ()
        run_async(
            lambda: chat._append_message_chunk(
                "stale", chunk=True, stream_id="active"
            )
        )
        run_async(
            lambda: chat._append_message_chunk(
                "", chunk="end", stream_id="active"
            )
        )
        assert chat._current_stream_id is None
        assert chat._current_stream_segments == []
        with reactive.isolate():
            assert chat.messages() == ()


def test_user_submit_messages_include_attachments_before_callback():
    from shinychat._attachments import Attachment

    session = cast(Session, _MockSession())
    attachment = Attachment.from_data(
        b"file contents", mime="text/plain", name="note.txt"
    )
    messages_seen_by_callback: list[tuple[ChatMessageDict, ...]] = []

    with session_context(session):
        chat = Chat("chat", history=False)

        @chat.on_user_submit
        async def on_submit() -> None:
            messages_seen_by_callback.append(chat.messages())

        cast(Any, session.input[chat.user_input_id])._set(
            {"text": "message from user", "attachments": [attachment]}
        )
        run_async(reactive.flush)

    assert len(messages_seen_by_callback) == 1
    message = messages_seen_by_callback[0][0]
    assert message["content"] == "message from user"
    assert message["role"] == "user"
    assert message.get("attachments") == [attachment]


def test_slash_command_messages_are_stored_before_handler():
    session = cast(Session, _MockSession())
    messages_seen_by_handler: list[tuple[ChatMessageDict, ...]] = []

    with session_context(session):
        chat = Chat("chat", history=False)

        @chat.slash_command("help", "Show help")
        async def help_command(_: str) -> None:
            messages_seen_by_handler.append(chat.messages())

        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "help", "userText": "topic", "echo": True}
        )
        run_async(reactive.flush)

    assert messages_seen_by_handler == [
        ({"content": "/help topic", "role": "user"},)
    ]


def test_slash_command_messages_skip_echo_false():
    session = cast(Session, _MockSession())
    messages_seen_by_handler: list[tuple[ChatMessageDict, ...]] = []

    with session_context(session):
        chat = Chat("chat", history=False)

        @chat.slash_command("help", "Show help", echo=False)
        async def help_command(_: str) -> None:
            messages_seen_by_handler.append(chat.messages())

        cast(Any, session.input[chat._slash_command_id])._set(
            {"command": "help", "userText": "topic", "echo": False}
        )
        run_async(reactive.flush)

    assert messages_seen_by_handler == [()]


@pytest.mark.filterwarnings(
    "ignore:The `.transform_assistant_response` decorator is deprecated"
)
def test_transformed_complete_message_preserves_dependencies_and_attachments(
    monkeypatch: pytest.MonkeyPatch,
):
    from shinychat._attachments import Attachment

    with session_context(test_session):
        chat = Chat("chat", history=False)
        sent: list[tuple[dict[str, Any], list[dict[str, object]] | None]] = []
        attachment = Attachment.from_data(
            b"file contents", mime="text/plain", name="note.txt"
        )
        dependency = HTMLDependency(
            name="transformed-widget",
            version="1.0.0",
            source={"subdir": "."},
        )

        async def capture(
            action: dict[str, Any], deps: list[dict[str, object]] | None = None
        ) -> None:
            sent.append((action, deps))

        def serialize(
            deps: list[HTMLDependency] | None,
        ) -> list[dict[str, object]] | None:
            if not deps:
                return None
            return [{"name": dep.name, "version": str(dep.version)} for dep in deps]

        monkeypatch.setattr(chat, "_send_action", capture)
        monkeypatch.setattr(chat, "_serialize_html_deps", serialize)

        @chat.transform_assistant_response
        def transform(_: str) -> HTML:
            return HTML("<strong>transformed</strong>")

        run_async(
            lambda: chat.append_message(
                ChatMessage(
                    TagList(dependency, tags.div("original")),
                    attachments=[attachment],
                )
            )
        )

        with reactive.isolate():
            messages = chat.messages()

    assert messages == (
        {
            "content": "\n\n<shinychat-raw-html><strong>transformed</strong></shinychat-raw-html>\n\n",
            "role": "assistant",
            "html_deps": [{"name": "transformed-widget", "version": "1.0.0"}],
            "attachments": [attachment],
        },
    )
    action, deps = sent[-1]
    assert action["message"]["segments"] == [
        {
            "content": "\n\n<shinychat-raw-html><strong>transformed</strong></shinychat-raw-html>\n\n",
            "content_type": "html",
        }
    ]
    assert action["message"]["attachments"] == [attachment.model_dump()]
    assert deps == [{"name": "transformed-widget", "version": "1.0.0"}]


@pytest.mark.filterwarnings(
    "ignore:The `.transform_assistant_response` decorator is deprecated"
)
def test_streamed_messages_store_mixed_segments_and_transformed_content(
    monkeypatch: pytest.MonkeyPatch,
):
    with session_context(test_session):
        chat = Chat("chat", history=False)
        sent: list[tuple[dict[str, Any], list[dict[str, object]] | None]] = []
        dependency = HTMLDependency(
            name="streamed-widget",
            version="1.0.0",
            source={"subdir": "."},
        )

        async def capture(
            action: dict[str, Any], deps: list[dict[str, object]] | None = None
        ) -> None:
            sent.append((action, deps))

        def serialize(
            deps: list[HTMLDependency] | None,
        ) -> list[dict[str, object]] | None:
            if not deps:
                return None
            return [{"name": dep.name, "version": str(dep.version)} for dep in deps]

        monkeypatch.setattr(chat, "_send_action", capture)
        monkeypatch.setattr(chat, "_serialize_html_deps", serialize)

        async def mixed_stream() -> AsyncIterator[ChatMessage]:
            yield ChatMessage(
                content="reasoning",
                role="assistant",
                content_type="thinking",
            )
            yield ChatMessage(
                content=TagList(dependency, tags.div("answer")),
                role="assistant",
            )

        run_async(lambda: chat._append_message_stream(mixed_stream()))

        with reactive.isolate():
            mixed_messages = chat.messages()

    assert mixed_messages == (
        {
            "content": "<thinking>\nreasoning\n</thinking>\n\n\n\n<shinychat-raw-html>\n  <div>answer</div>\n</shinychat-raw-html>\n\n",
            "role": "assistant",
            "html_deps": [{"name": "streamed-widget", "version": "1.0.0"}],
        },
    )
    chunk_actions = [action for action, _ in sent if action["type"] == "chunk"]
    assert chunk_actions == [
        {
            "type": "chunk",
            "content": "reasoning",
            "operation": "append",
            "content_type": "thinking",
        },
        {
            "type": "chunk",
            "content": "\n\n<shinychat-raw-html>\n  <div>answer</div>\n</shinychat-raw-html>\n\n",
            "operation": "append",
            "content_type": "html",
        },
    ]

    with session_context(test_session):
        transformed = Chat("transformed", history=False)

        async def noop(
            action: dict[str, Any], deps: list[dict[str, object]] | None = None
        ) -> None:
            return None

        monkeypatch.setattr(transformed, "_send_action", noop)

        @transformed.transform_assistant_response
        def transform(content: str, _: str, done: bool) -> str:
            return f"{content} done" if done else content

        async def transformed_stream() -> AsyncIterator[str]:
            yield "one"
            yield " two"

        run_async(
            lambda: transformed._append_message_stream(transformed_stream())
        )

        with reactive.isolate():
            transformed_messages = transformed.messages()

    assert transformed_messages == (
        {"content": "one two done", "role": "assistant"},
    )


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
        == "\n\n<shiny-chat-raw-html>Hello <span>world</span>!</shiny-chat-raw-html>\n\n"
    )
    assert m.role == "assistant"

    # Interpreted as HTML (if top-level object is tag-like, inner string contents get escaped)
    m = message_content(div("Hello <span>world</span>!"))
    assert (
        m.content
        == "\n\n<shiny-chat-raw-html>\n  <div>Hello &lt;span&gt;world&lt;/span&gt;!</div>\n</shiny-chat-raw-html>\n\n"
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
        async def _(): ...

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
        async def _(): ...

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

        chat.slash_command(
            "clientecho", "Client-side but echoed", fn=None, echo=True
        )

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
        reported = (
            chat._as_stored_message(
                ChatMessage(content="/greet world", role="user")
            ),
            chat._as_stored_message(
                ChatMessage(content="Hello! You said: world", role="assistant")
            ),
        )
        chat._replace_messages(reported)
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {
            "role": "user",
            "segments": [
                {"content": "/greet world", "content_type": "markdown"}
            ],
        },
        {
            "role": "assistant",
            "segments": [
                {
                    "content": "Hello! You said: world",
                    "content_type": "markdown",
                }
            ],
        },
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

            with reactive.isolate():
                assert restored._messages() == reported

            return [
                (
                    cast(Role, a["message"]["role"]),
                    a["message"]["segments"][0]["content"],
                )
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
        reported = (
            chat._as_stored_message(
                ChatMessage(content="real message", role="user")
            ),
        )
        chat._replace_messages(reported)
        with reactive.isolate():
            saved = chat._messages_for_bookmark()

    assert saved == [
        {
            "role": "user",
            "segments": [
                {"content": "real message", "content_type": "markdown"}
            ],
        },
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
            await chat._append_message_stream(gen())

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
        reported = (
            StoredMessage(
                role="assistant",
                segments=[
                    StoredSegment(content="reasoning", content_type="thinking"),
                    StoredSegment(content="answer", content_type="markdown"),
                ],
            ),
        )
        chat._replace_messages(reported)
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

        att = Attachment.from_data(
            b"hello", mime="text/plain", name="hello.txt"
        )
        stored = StoredMessage(
            role="assistant",
            segments=[
                StoredSegment(content="here you go", content_type="markdown")
            ],
            attachments=[att],
        )

        run_async(lambda: chat._send_append_message(stored))

        payload = sent[0]["message"]
        # Must not raise — the payload must be JSON-serializable.
        json.dumps(payload)

        # Attachments must arrive as plain dicts with the expected keys.
        assert payload["attachments"] == [
            {
                "mime": "text/plain",
                "name": "hello.txt",
                "size": 5,
                "data_url": att.data_url,
            }
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
            attachments=[
                Attachment.from_data(b"x", mime="image/png", name="c.png")
            ],
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
            attachments=[
                Attachment.from_data(b"x", mime="image/png", name="c.png")
            ],
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
            StoredMessage.from_chat_message(
                ChatMessage("plain text", role="assistant")
            ),
        )
        chat._replace_messages(reported)

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
