from __future__ import annotations

import asyncio
import json
import threading
from typing import cast

import pytest
from htmltools import HTML, tags
from shiny import Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat, chat_greeting, chat_ui
from shinychat._chat_types import ChatGreeting

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    _sent: list[tuple[str, object]]

    def __init__(self):
        self._sent = []

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: object) -> None:
        self._sent.append((type, message))


def make_session() -> tuple[_MockSession, Session]:
    mock = _MockSession()
    return mock, cast(Session, mock)


def run_async(coro):
    exc: list[BaseException] = []
    result: list[object] = []

    def _target():
        try:
            result.append(asyncio.run(coro))
        except BaseException as e:
            exc.append(e)

    t = threading.Thread(target=_target)
    t.start()
    t.join()
    if exc:
        raise exc[0]
    return result[0] if result else None


# ---------------------------------------------------------------------------
# ChatGreeting / chat_greeting() tests
# ---------------------------------------------------------------------------


def test_chat_greeting_defaults():
    g = chat_greeting("## Hello")
    assert isinstance(g, ChatGreeting)
    assert g.content == "## Hello"
    assert g.content_type == "markdown"
    assert g.dismissible is True
    assert g.html_deps == []


def test_chat_greeting_all_options():
    g = chat_greeting(
        "hi",
        dismissible=False,
    )
    assert g.dismissible is False


def test_chat_greeting_str_content_type():
    g = chat_greeting("## Markdown greeting")
    assert g.content_type == "markdown"
    assert g.content == "## Markdown greeting"


def test_chat_greeting_html_content_type():
    g = chat_greeting(HTML("<b>bold</b>"))
    assert g.content_type == "html"
    assert "<b>bold</b>" in g.content


def test_chat_greeting_tag_content_type():
    g = chat_greeting(tags.div("hello"))
    assert g.content_type == "html"
    assert "hello" in g.content


def test_chat_greeting_async_iterator_not_consumed():
    async def stream():
        for tok in ["a", "b", "c"]:
            yield tok

    it = stream()
    g = chat_greeting(it)
    assert g.content is it
    assert g.content_type == "markdown"
    assert g.html_deps == []


# ---------------------------------------------------------------------------
# chat_ui(greeting=) tests
# ---------------------------------------------------------------------------


def _greeting_attr(tag) -> dict:
    """Extract and parse the `greeting` attribute JSON from the returned tag."""
    rendered = tag.get_html_string()
    import re

    m = re.search(r'greeting="([^"]*)"', rendered)
    assert m is not None, "No greeting attribute found in rendered tag"
    return json.loads(m.group(1).replace("&quot;", '"'))


def test_chat_ui_plain_string_greeting():
    tag = chat_ui("chat", greeting="## Hi")
    rendered = tag.get_html_string()
    import re

    m = re.search(r'greeting="([^"]*)"', rendered)
    assert m is not None, "No greeting attribute in chat_ui output"
    payload = json.loads(m.group(1).replace("&quot;", '"'))
    assert payload["content"] == "## Hi"
    assert payload["content_type"] == "markdown"
    assert payload["options"]["dismissible"] is True


def test_chat_ui_chat_greeting_object():
    g = chat_greeting("## Hi", dismissible=False)
    tag = chat_ui("chat", greeting=g)
    rendered = tag.get_html_string()
    import re

    m = re.search(r'greeting="([^"]*)"', rendered)
    assert m is not None
    payload = json.loads(m.group(1).replace("&quot;", '"'))
    assert payload["content"] == "## Hi"
    assert payload["content_type"] == "markdown"
    assert payload["options"]["dismissible"] is False


def test_chat_ui_tag_greeting_has_html_content_type():
    g = chat_greeting(tags.div("hi"))
    tag = chat_ui("chat", greeting=g)
    rendered = tag.get_html_string()
    import re

    m = re.search(r'greeting="([^"]*)"', rendered)
    assert m is not None
    payload = json.loads(m.group(1).replace("&quot;", '"'))
    assert payload["content_type"] == "html"
    assert "hi" in payload["content"]


def test_chat_ui_no_greeting_no_attribute():
    tag = chat_ui("chat")
    rendered = tag.get_html_string()
    assert 'greeting="' not in rendered


def test_chat_ui_async_iterator_raises():
    async def stream():
        yield "hi"

    with pytest.raises(ValueError, match="async iterator"):
        chat_ui("chat", greeting=chat_greeting(stream()))


# ---------------------------------------------------------------------------
# Chat.set_greeting() tests
# ---------------------------------------------------------------------------


def test_set_greeting_none_sends_greeting_clear():
    mock, sess = make_session()

    async def _run():
        with session_context(sess):
            chat = Chat(id="chat")
            await chat.set_greeting(None)

    run_async(_run())

    assert len(mock._sent) == 1
    type_, envelope = mock._sent[0]
    assert type_ == "shinyChatMessage"
    assert envelope["action"]["type"] == "greeting_clear"


def test_set_greeting_static_string_sends_greeting_action():
    mock, sess = make_session()

    async def _run():
        with session_context(sess):
            chat = Chat(id="chat")
            await chat.set_greeting("## Welcome!")

    run_async(_run())

    assert len(mock._sent) == 1
    type_, envelope = mock._sent[0]
    assert type_ == "shinyChatMessage"
    action = envelope["action"]
    assert action["type"] == "greeting"
    assert action["content"] == "## Welcome!"
    assert action["content_type"] == "markdown"
    assert action["options"]["dismissible"] is True


def test_set_greeting_html_content_type():
    mock, sess = make_session()

    async def _run():
        with session_context(sess):
            chat = Chat(id="chat")
            await chat.set_greeting(chat_greeting(HTML("<b>hi</b>")))

    run_async(_run())

    assert len(mock._sent) == 1
    _, envelope = mock._sent[0]
    action = envelope["action"]
    assert action["type"] == "greeting"
    assert action["content_type"] == "html"
    assert "<b>hi</b>" in action["content"]


def test_set_greeting_async_iterator_streams_chunks():
    mock, sess = make_session()

    async def stream():
        for token in ["Hello", " world", "!"]:
            yield token

    async def _run():
        with session_context(sess):
            chat = Chat(id="chat")
            await chat.set_greeting(chat_greeting(stream()))

    run_async(_run())

    types = [env["action"]["type"] for _, env in mock._sent]
    assert types[0] == "greeting_start"
    assert all(t == "greeting_chunk" for t in types[1:-1])
    assert types[-1] == "greeting_end"

    chunks = [env["action"]["content"] for _, env in mock._sent[1:-1]]
    assert chunks == ["Hello", " world", "!"]

    for _, env in mock._sent[1:-1]:
        assert env["action"]["operation"] == "append"
