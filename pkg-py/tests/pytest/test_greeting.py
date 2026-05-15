from __future__ import annotations

import json

import pytest
from htmltools import HTML, tags
from shinychat import chat_greeting, chat_ui
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


# ---------------------------------------------------------------------------
# chat_ui(greeting=) tests
# ---------------------------------------------------------------------------


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


