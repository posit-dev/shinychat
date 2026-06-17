from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, cast

import pytest
from htmltools import HTML, HTMLDependency, tags
from shiny.session import session_context
from shinychat import Chat, chat_greeting, chat_ui
from shinychat._chat_types import ChatGreeting

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
    assert isinstance(g.content, str)
    assert "<b>bold</b>" in g.content


def test_chat_greeting_tag_content_type():
    g = chat_greeting(tags.div("hello"))
    assert g.content_type == "html"
    assert isinstance(g.content, str)
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


def test_chat_greeting_custom_async_iterable():
    """Objects that implement __aiter__ without subclassing AsyncIterator should be treated as streams."""

    class CustomAsyncIterable:
        def __init__(self, items):
            self._items = items

        def __aiter__(self):
            return self._Iterator(self._items)

        class _Iterator:
            def __init__(self, items):
                self._items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

    it = CustomAsyncIterable(["hello", " ", "world"])
    g = chat_greeting(it)
    assert g.content is it
    assert g.content_type == "markdown"
    assert g.html_deps == []


# ---------------------------------------------------------------------------
# chat_ui(greeting=) tests
# ---------------------------------------------------------------------------


def _greeting_payload(tag):
    """Extract and parse the greeting JSON attribute from a chat_ui tag."""
    greeting_json = tag.attrs.get("greeting")
    assert greeting_json is not None, "No greeting attribute on chat_ui tag"
    return json.loads(greeting_json)


def test_chat_ui_plain_string_greeting():
    tag = chat_ui("chat", greeting="## Hi")
    payload = _greeting_payload(tag)
    assert payload["content"] == "## Hi"
    assert payload["content_type"] == "markdown"
    assert payload["options"]["dismissible"] is True


def test_chat_ui_chat_greeting_object():
    g = chat_greeting("## Hi", dismissible=False)
    tag = chat_ui("chat", greeting=g)
    payload = _greeting_payload(tag)
    assert payload["content"] == "## Hi"
    assert payload["content_type"] == "markdown"
    assert payload["options"]["dismissible"] is False


def test_chat_ui_tag_greeting_has_html_content_type():
    g = chat_greeting(tags.div("hi"))
    tag = chat_ui("chat", greeting=g)
    payload = _greeting_payload(tag)
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


def test_chat_greeting_tag_with_dependency_has_html_deps():
    dep = HTMLDependency("my-dep", "1.0.0", source={"package": None, "subdir": "."})
    g = chat_greeting(tags.div("hello", dep))
    assert g.content_type == "html"
    dep_names = [d.name for d in g.html_deps]
    assert "my-dep" in dep_names


# ---------------------------------------------------------------------------
# Chat.set_greeting() unit tests
# ---------------------------------------------------------------------------


class _SpySession:
    """Minimal mock that captures custom messages sent by Chat."""

    ns: Any = ""
    app: object = None
    id: str = "spy-session"
    messages: list[tuple[str, dict]] = []

    def __init__(self):
        self.messages = []

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: dict) -> None:
        self.messages.append((type, message))


def _spy_actions(spy: _SpySession) -> list[dict]:
    return [msg[1]["action"] for msg in spy.messages]


def _make_spy_chat():
    from shiny.module import ResolvedId

    spy = _SpySession()
    spy.ns = ResolvedId("")
    with session_context(cast(Any, spy)):
        chat = Chat(id="chat")
    chat._session = cast(Any, spy)
    return chat, spy


def _run_async(coro_fn):
    """Run an async function in a separate thread to avoid event loop conflicts."""
    exc: list[BaseException] = []

    def _target():
        try:
            asyncio.run(coro_fn())
        except BaseException as err:
            exc.append(err)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    if exc:
        raise exc[0]


def test_set_greeting_none_sends_greeting_clear():
    chat, spy = _make_spy_chat()

    async def _run():
        await chat.set_greeting(None)

    _run_async(_run)
    actions = _spy_actions(spy)
    assert len(actions) == 1
    assert actions[0]["type"] == "greeting_clear"


def test_set_greeting_string_sends_greeting_action():
    chat, spy = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello")

    _run_async(_run)
    actions = _spy_actions(spy)
    assert len(actions) == 1
    assert actions[0]["type"] == "greeting"
    assert actions[0]["content"] == "Hello"
    assert actions[0]["content_type"] == "markdown"
    assert actions[0]["options"]["dismissible"] is True


def test_set_greeting_html_sends_html_content_type():
    chat, spy = _make_spy_chat()

    async def _run():
        await chat.set_greeting(chat_greeting(HTML("<b>hi</b>")))

    _run_async(_run)
    actions = _spy_actions(spy)
    assert len(actions) == 1
    assert actions[0]["type"] == "greeting"
    assert actions[0]["content_type"] == "html"
    assert "<b>hi</b>" in actions[0]["content"]


def test_set_greeting_stream_sends_start_chunks_end():
    chat, spy = _make_spy_chat()

    async def _run():
        async def stream():
            yield "He"
            yield "llo"

        await chat.set_greeting(chat_greeting(stream()))

    _run_async(_run)
    actions = _spy_actions(spy)
    types = [a["type"] for a in actions]
    assert types[0] == "greeting_start"
    assert types[-1] == "greeting_end"
    chunk_actions = [a for a in actions if a["type"] == "greeting_chunk"]
    assert len(chunk_actions) >= 1
    assert all(a["operation"] == "append" for a in chunk_actions)


def test_set_greeting_non_dismissible():
    chat, spy = _make_spy_chat()

    async def _run():
        await chat.set_greeting(chat_greeting("Hi", dismissible=False))

    _run_async(_run)
    actions = _spy_actions(spy)
    assert actions[0]["options"]["dismissible"] is False


# ---------------------------------------------------------------------------
# Chat._greeting_content tracking
# ---------------------------------------------------------------------------


def test_greeting_content_set_after_set_greeting_string():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")

    _run_async(_run)
    assert chat._greeting_content == "Hello world"


def test_greeting_content_cleared_after_set_greeting_none():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")
        await chat.set_greeting(None)

    _run_async(_run)
    assert chat._greeting_content is None


def test_greeting_content_cleared_after_clear_messages_with_greeting():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")
        await chat.clear_messages(greeting=True)

    _run_async(_run)
    assert chat._greeting_content is None


# ---------------------------------------------------------------------------
# enable_bookmarking() excludes greeting inputs
# ---------------------------------------------------------------------------


class _MockBookmark:
    """Minimal bookmark stub that records exclude appends and callback registrations."""

    def __init__(self):
        self.exclude: list[str] = []

    def on_bookmark(self, fn: object) -> object:
        return fn

    def on_restore(self, fn: object) -> object:
        return fn

    def on_bookmarked(self, fn: object) -> object:
        return fn


class _MockBookmarkSession:
    """Minimal session stub for enable_bookmarking() unit tests."""

    def __init__(self):
        from shiny.module import ResolvedId

        self.ns = ResolvedId("")
        self.app = None
        self.id = "bm-session"
        self.bookmark = _MockBookmark()

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> "_MockBookmarkSession":
        return self

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: dict) -> None:
        pass


class _MockClient:
    """Minimal client with async get_state/set_state for enable_bookmarking()."""

    async def get_state(self) -> dict:
        return {}

    async def set_state(self, state: object) -> None:
        pass


def _make_bookmark_chat(chat_id: str):
    """Create a Chat with a session that has bookmark support."""
    from shiny.session import session_context

    bm_sess = _MockBookmarkSession()
    with session_context(cast(Any, bm_sess)):
        chat = Chat(id=chat_id)
    chat._session = cast(Any, bm_sess)
    return chat, bm_sess


def test_enable_bookmarking_excludes_greeting_requested():
    chat, bm_sess = _make_bookmark_chat("bm_chat_req")
    with session_context(cast(Any, bm_sess)):
        chat.enable_bookmarking(_MockClient())
    assert "bm_chat_req_greeting_requested" in bm_sess.bookmark.exclude


def test_enable_bookmarking_excludes_greeting_dismissed():
    chat, bm_sess = _make_bookmark_chat("bm_chat_dis")
    with session_context(cast(Any, bm_sess)):
        chat.enable_bookmarking(_MockClient())
    assert "bm_chat_dis_greeting_dismissed" in bm_sess.bookmark.exclude


