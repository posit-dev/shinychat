from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, cast

import pytest
from htmltools import HTML, HTMLDependency, TagList, tags
from shiny.session import session_context
from shinychat import Chat, chat_greeting, chat_ui
from shinychat._chat_types import ChatGreeting, GreetingSnapshot

# ---------------------------------------------------------------------------
# ChatGreeting / chat_greeting() tests
# ---------------------------------------------------------------------------


def test_chat_greeting_defaults():
    g = chat_greeting("## Hello")
    assert isinstance(g, ChatGreeting)
    assert g.content == "## Hello"
    assert g.content_type == "markdown"
    assert g.persistent is False
    assert g.html_deps == []


def test_chat_greeting_all_options():
    g = chat_greeting(
        "hi",
        persistent=True,
    )
    assert g.persistent is True


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
    assert payload["options"]["persistent"] is False


def test_chat_ui_chat_greeting_object():
    g = chat_greeting("## Hi", persistent=True)
    tag = chat_ui("chat", greeting=g)
    payload = _greeting_payload(tag)
    assert payload["content"] == "## Hi"
    assert payload["content_type"] == "markdown"
    assert payload["options"]["persistent"] is True


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
    dep = HTMLDependency(
        "my-dep", "1.0.0", source={"package": None, "subdir": "."}
    )
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
    assert actions[0]["options"]["persistent"] is False


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


def test_set_greeting_persistent():
    chat, spy = _make_spy_chat()

    async def _run():
        await chat.set_greeting(chat_greeting("Hi", persistent=True))

    _run_async(_run)
    actions = _spy_actions(spy)
    assert actions[0]["options"]["persistent"] is True


# ---------------------------------------------------------------------------
# Chat._greeting_snapshot tracking
# ---------------------------------------------------------------------------


def test_greeting_snapshot_set_after_set_greeting_string():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")

    _run_async(_run)
    assert chat._greeting_snapshot == {
        "content": "Hello world",
        "content_type": "markdown",
        "options": {"persistent": False},
        "html_deps": [],
    }


def test_greeting_snapshot_cleared_after_set_greeting_none():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")
        await chat.set_greeting(None)

    _run_async(_run)
    assert chat._greeting_snapshot is None


def test_greeting_snapshot_cleared_after_clear_messages_with_greeting():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")
        await chat.clear_messages(greeting=True)

    _run_async(_run)
    assert chat._greeting_snapshot is None


def test_greeting_snapshot_static_has_all_fields(monkeypatch: pytest.MonkeyPatch):
    chat, _ = _make_spy_chat()

    def serialize(deps: Any) -> Any:
        if not deps:
            return None
        return [{"name": d.name, "version": str(d.version)} for d in deps]

    monkeypatch.setattr(chat, "_serialize_html_deps", serialize)

    dep = HTMLDependency(
        "greeting-style", "1.0.0", source={"package": None, "subdir": "."}
    )

    async def _run():
        await chat.set_greeting(
            chat_greeting(TagList(tags.strong("Welcome"), dep), persistent=True)
        )

    _run_async(_run)

    snapshot = chat._greeting_snapshot
    assert snapshot is not None
    expected: GreetingSnapshot = {
        "content": snapshot["content"],
        "content_type": "html",
        "options": {"persistent": True},
        "html_deps": [{"name": "greeting-style", "version": "1.0.0"}],
    }
    assert snapshot == expected
    assert "Welcome" in snapshot["content"]


def test_greeting_snapshot_streamed_stores_final_content_and_options():
    chat, _ = _make_spy_chat()

    async def _run():
        async def stream():
            yield "He"
            yield "llo"

        await chat.set_greeting(chat_greeting(stream(), persistent=True))

    _run_async(_run)

    assert chat._greeting_snapshot == {
        "content": "Hello",
        "content_type": "markdown",
        "options": {"persistent": True},
        "html_deps": [],
    }


def test_greeting_snapshot_not_stored_when_stream_raises():
    chat, _ = _make_spy_chat()

    async def _run():
        async def stream():
            yield "He"
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await chat.set_greeting(chat_greeting(stream()))

    _run_async(_run)
    assert chat._greeting_snapshot is None


def test_get_greeting_returns_content_after_set():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")

    _run_async(_run)
    assert chat.get_greeting() == "Hello world"


def test_get_greeting_returns_none_after_clear():
    chat, _ = _make_spy_chat()

    async def _run():
        await chat.set_greeting("Hello world")
        await chat.set_greeting(None)

    _run_async(_run)
    assert chat.get_greeting() is None


# ---------------------------------------------------------------------------
# enable_bookmarking() excludes greeting inputs
# ---------------------------------------------------------------------------


class _MockBookmark:
    """Minimal bookmark stub that records exclude appends and callback registrations."""

    def __init__(self):
        self.exclude: list[str] = []
        self.on_bookmark_fns: list[Any] = []
        self.on_restore_fns: list[Any] = []

    def on_bookmark(self, fn: object) -> object:
        self.on_bookmark_fns.append(fn)
        return fn

    def on_restore(self, fn: object) -> object:
        self.on_restore_fns.append(fn)
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


# ---------------------------------------------------------------------------
# Greeting bookmark save/restore
# ---------------------------------------------------------------------------


class _RecordingState:
    def __init__(self, values: dict[str, Any] | None = None):
        self.values: dict[str, Any] = values if values is not None else {}


def _find_hook(fns: list[Any], name: str) -> Any:
    return next(fn for fn in fns if fn.__name__ == name)


def test_bookmark_save_writes_full_snapshot(monkeypatch: pytest.MonkeyPatch):
    chat, bm_sess = _make_bookmark_chat("bm_greet_save")
    with session_context(cast(Any, bm_sess)):
        chat.enable_bookmarking(_MockClient())

    def serialize(deps: Any) -> Any:
        if not deps:
            return None
        return [{"name": d.name, "version": str(d.version)} for d in deps]

    monkeypatch.setattr(chat, "_serialize_html_deps", serialize)

    dep = HTMLDependency(
        "greeting-style", "1.0.0", source={"package": None, "subdir": "."}
    )

    async def _run():
        await chat.set_greeting(
            chat_greeting(TagList(tags.strong("Welcome"), dep), persistent=True)
        )

    _run_async(_run)

    on_bookmark_greeting = _find_hook(
        bm_sess.bookmark.on_bookmark_fns, "_on_bookmark_greeting"
    )
    state = _RecordingState()
    on_bookmark_greeting(state)

    key = "bm_greet_save--greeting"
    assert key in state.values
    snapshot = state.values[key]
    assert snapshot["content_type"] == "html"
    assert snapshot["options"] == {"persistent": True}
    assert snapshot["html_deps"] == [
        {"name": "greeting-style", "version": "1.0.0"}
    ]
    assert "Welcome" in snapshot["content"]


def test_bookmark_restore_sends_original_snapshot(monkeypatch: pytest.MonkeyPatch):
    chat, bm_sess = _make_bookmark_chat("bm_greet_restore")
    with session_context(cast(Any, bm_sess)):
        chat.enable_bookmarking(_MockClient())

    sent: list[tuple[dict[str, Any], Any]] = []

    async def capture(action: dict[str, Any], deps: Any = None) -> None:
        sent.append((action, deps))

    monkeypatch.setattr(chat, "_send_action", capture)

    on_restore_greeting = _find_hook(
        bm_sess.bookmark.on_restore_fns, "_on_restore_greeting"
    )

    snapshot: GreetingSnapshot = {
        "content": "<strong>Welcome</strong>",
        "content_type": "html",
        "options": {"persistent": True},
        "html_deps": [{"name": "greeting-style", "version": "1.0.0"}],
    }
    state = _RecordingState({"bm_greet_restore--greeting": snapshot})

    async def _run():
        await on_restore_greeting(state)

    _run_async(_run)

    assert len(sent) == 1
    action, deps = sent[0]
    assert action == {
        "type": "greeting",
        "content": "<strong>Welcome</strong>",
        "content_type": "html",
        "options": {"persistent": True},
    }
    assert deps == [{"name": "greeting-style", "version": "1.0.0"}]
    assert chat._greeting_snapshot == snapshot


def test_bookmark_restore_rejects_legacy_content_only_snapshot():
    chat, bm_sess = _make_bookmark_chat("bm_greet_legacy")
    with session_context(cast(Any, bm_sess)):
        chat.enable_bookmarking(_MockClient())

    on_restore_greeting = _find_hook(
        bm_sess.bookmark.on_restore_fns, "_on_restore_greeting"
    )

    state = _RecordingState({"bm_greet_legacy--greeting": {"content": "Hello"}})

    async def _run():
        await on_restore_greeting(state)

    with pytest.raises(ValueError, match="Cannot restore bookmark greeting"):
        _run_async(_run)

    assert chat._greeting_snapshot is None
