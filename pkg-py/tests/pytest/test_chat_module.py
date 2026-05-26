from __future__ import annotations

import inspect
from typing import Any, cast

import pytest
from htmltools import HTML, Tag, TagList, tags
from shiny import Session
from shiny.module import ResolvedId
from shiny.session import session_context

from shinychat import ChatServerState, chat_mod_ui, chat_mod_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass


test_session = cast(Session, _MockSession())


# ---------------------------------------------------------------------------
# chat_mod_ui() tests
# ---------------------------------------------------------------------------


def test_chat_mod_ui_returns_tag():
    with session_context(test_session):
        result = chat_mod_ui("mymod")
    assert isinstance(result, Tag)


def test_chat_mod_ui_namespaced_id():
    with session_context(test_session):
        result = chat_mod_ui("mymod")
    html = result.get_html_string()
    assert 'id="mymod-chat"' in html


def test_chat_mod_ui_different_ids_are_distinct():
    with session_context(test_session):
        result_a = chat_mod_ui("alpha")
        result_b = chat_mod_ui("beta")
    html_a = result_a.get_html_string()
    html_b = result_b.get_html_string()
    assert 'id="alpha-chat"' in html_a
    assert 'id="beta-chat"' in html_b
    assert 'id="beta-chat"' not in html_a
    assert 'id="alpha-chat"' not in html_b


def test_chat_mod_ui_enable_cancel_attribute():
    with session_context(test_session):
        result = chat_mod_ui("mymod")
    html = result.get_html_string()
    assert "enable-cancel" in html


def test_chat_mod_ui_default_placeholder():
    with session_context(test_session):
        result = chat_mod_ui("mymod")
    html = result.get_html_string()
    assert "Enter a message..." in html


def test_chat_mod_ui_custom_placeholder():
    with session_context(test_session):
        result = chat_mod_ui("mymod", placeholder="Ask me anything")
    html = result.get_html_string()
    assert "Ask me anything" in html


def test_chat_mod_ui_custom_width():
    with session_context(test_session):
        result = chat_mod_ui("mymod", width="400px")
    html = result.get_html_string()
    assert "400px" in html


def test_chat_mod_ui_custom_height():
    with session_context(test_session):
        result = chat_mod_ui("mymod", height="600px")
    html = result.get_html_string()
    assert "600px" in html


def test_chat_mod_ui_with_footer():
    footer = tags.div("footer content", id="my-footer")
    with session_context(test_session):
        result = chat_mod_ui("mymod", footer=footer)
    html = result.get_html_string()
    assert "footer content" in html
    assert "my-footer" in html


def test_chat_mod_ui_with_tag_icon_assistant():
    icon = tags.span("bot", id="robot-icon")
    with session_context(test_session):
        result = chat_mod_ui("mymod", icon_assistant=icon)
    html = result.get_html_string()
    assert "robot-icon" in html


def test_chat_mod_ui_with_html_icon_assistant():
    icon = HTML("<span>bot</span>")
    with session_context(test_session):
        result = chat_mod_ui("mymod", icon_assistant=icon)
    html = result.get_html_string()
    assert "bot" in html


def test_chat_mod_ui_with_messages():
    messages = [{"role": "assistant", "content": "Hello there!"}]
    with session_context(test_session):
        result = chat_mod_ui("mymod", messages=messages)
    html = result.get_html_string()
    assert "Hello there!" in html


def test_chat_mod_ui_fill_true_by_default():
    with session_context(test_session):
        result = chat_mod_ui("mymod")
    html = result.get_html_string()
    assert "fill" in html.lower()


def test_chat_mod_ui_fill_false():
    with session_context(test_session):
        result = chat_mod_ui("mymod", fill=False)
    html = result.get_html_string()
    assert "html-fill-container" not in html


# ---------------------------------------------------------------------------
# ChatServerState structural tests
# ---------------------------------------------------------------------------


def test_chat_server_state_has_last_input_method():
    assert callable(getattr(ChatServerState, "last_input", None))


def test_chat_server_state_has_last_turn_method():
    assert callable(getattr(ChatServerState, "last_turn", None))


def test_chat_server_state_has_status_method():
    assert callable(getattr(ChatServerState, "status", None))


def test_chat_server_state_client_is_property():
    members = dict(
        inspect.getmembers(ChatServerState, lambda v: isinstance(v, property))
    )
    assert "client" in members


def test_chat_server_state_has_update_user_input_method():
    assert callable(getattr(ChatServerState, "update_user_input", None))


def test_chat_server_state_has_append_method():
    method = getattr(ChatServerState, "append", None)
    assert callable(method)
    assert inspect.iscoroutinefunction(method)


def test_chat_server_state_has_clear_method():
    method = getattr(ChatServerState, "clear", None)
    assert callable(method)
    assert inspect.iscoroutinefunction(method)


def test_chat_server_state_has_set_greeting_method():
    method = getattr(ChatServerState, "set_greeting", None)
    assert callable(method)
    assert inspect.iscoroutinefunction(method)


def test_chat_server_state_has_set_client_method():
    assert callable(getattr(ChatServerState, "set_client", None))


def test_chat_server_state_update_user_input_signature():
    sig = inspect.signature(ChatServerState.update_user_input)
    params = list(sig.parameters.keys())
    assert "value" in params
    assert "placeholder" in params
    assert "submit" in params
    assert "focus" in params


def test_chat_server_state_clear_signature():
    sig = inspect.signature(ChatServerState.clear)
    params = list(sig.parameters.keys())
    assert "messages" in params
    assert "greeting" in params
    assert "client_history" in params


def test_chat_server_state_set_client_signature():
    sig = inspect.signature(ChatServerState.set_client)
    params = list(sig.parameters.keys())
    assert "new_client" in params
    assert "sync" in params


def test_chat_server_state_append_signature():
    sig = inspect.signature(ChatServerState.append)
    params = list(sig.parameters.keys())
    assert "response" in params
    assert "role" in params
    assert "icon" in params


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_import_chat_mod_ui():
    from shinychat import chat_mod_ui as _fn

    assert callable(_fn)


def test_import_chat_mod_server():
    from shinychat import chat_mod_server as _fn

    assert callable(_fn)


def test_import_chat_server_state():
    from shinychat import ChatServerState as _cls

    assert isinstance(_cls, type)


def test_chatlas_importable():
    """chatlas must be importable since chat_mod_server requires it."""
    try:
        import chatlas  # noqa: F401

        chatlas_available = True
    except ImportError:
        chatlas_available = False

    if not chatlas_available:
        pytest.skip("chatlas is not installed")

    assert chatlas_available
