"""Fast unit/serialization tests for the condensed tool view (no browser).

Covers:
- `chat_ui(tool_grouping=...)` container attribute emission.
- `ToolResultDisplay(label=..., value_preview=...)` serialization onto
  `<shiny-tool-result>`.
- Per-tool `grouping` annotation propagation onto both
  `<shiny-tool-request>` and `<shiny-tool-result>`, including graceful
  degradation for invalid/non-scalar annotation values.
- The `SHINYCHAT_TOOL_DISPLAY` env override x grouping matrix.
"""

from __future__ import annotations

import gc
import json
from typing import Any, cast

import pytest
from chatlas._tools import Tool
from chatlas.types import ContentToolRequest, ContentToolResult, ToolInfo
from htmltools import HTML, HTMLDependency, Tag, TagList
from shinychat import chat_ui, message_content, message_content_chunk
from shinychat._chat_normalize_chatlas import (
    ShinyToolCardMessage,
    ToolRequestComponent,
    ToolResultDisplay,
    tool_request_contents,
    tool_result_contents,
)
from shinychat._chat_types import ToolResultBlock
from shinychat.types import ChatMessage


def _tool(annotations: dict[str, Any] | None = None) -> Tool:
    def my_tool(x: int) -> int:
        return x

    # Tests pass ad-hoc annotation dicts (including unknown keys); chatlas types
    # this as the `ToolAnnotations` TypedDict, so cast to keep pyright quiet.
    return Tool.from_func(my_tool, annotations=cast(Any, annotations))


def _request(
    tool: Tool | None = None, arguments: dict[str, Any] | None = None
) -> ContentToolRequest:
    req = ContentToolRequest(
        id="call-1", name="my_tool", arguments=arguments or {"x": 1}
    )
    if tool is not None:
        # Mirrors what chatlas itself does internally: `x.tool =
        # ToolInfo.from_tool(tool)`. Going through `ToolInfo` (a pydantic
        # model with a typed `annotations` field) is important -- unknown
        # top-level annotation keys survive at runtime, but are outside
        # chatlas's `ToolAnnotations` typing; `annotations["extra"]` is the
        # type-checker-friendly spelling.
        req.tool = ToolInfo.from_tool(tool)
    return req


def _result(request: ContentToolRequest, **kwargs: Any) -> ContentToolResult:
    return ContentToolResult(value=2, request=request, **kwargs)


def _render(component: Any) -> str:
    return TagList(component.tagify()).render()["html"]


# ---------------------------------------------------------------------------
# 1. chat_ui(tool_grouping=...) container attribute
# ---------------------------------------------------------------------------


def test_chat_ui_tool_grouping_all_emits_attribute():
    html = chat_ui("chat", tool_grouping="all").get_html_string()
    assert 'tool-grouping="all"' in html


def test_chat_ui_tool_grouping_none_emits_attribute():
    html = chat_ui("chat", tool_grouping="none").get_html_string()
    assert 'tool-grouping="none"' in html


def test_chat_ui_tool_grouping_default_omits_attribute():
    html = chat_ui("chat").get_html_string()
    assert "tool-grouping" not in html


def test_chat_ui_tool_grouping_explicit_tool_omits_attribute():
    # Explicit "tool" (== default) should also not emit the attribute.
    html = chat_ui("chat", tool_grouping="tool").get_html_string()
    assert "tool-grouping" not in html


def test_chat_ui_tool_grouping_invalid_raises():
    # The client silently falls back to "tool" for an unknown value, so a typo
    # must fail on the server (mirrors R's `arg_match()`).
    with pytest.raises(ValueError, match="`tool_grouping` must be one of"):
        chat_ui("chat", tool_grouping=cast(Any, "bogus"))


# ---------------------------------------------------------------------------
# 2. ToolResultDisplay(label=..., value_preview=...) serialization
# ---------------------------------------------------------------------------


def test_tool_result_display_label_and_value_preview_serialize():
    request = _request()
    display = ToolResultDisplay(label="query.csv", value_preview="42 rows")
    result = _result(request, extra={"display": display})

    rendered = _render(tool_result_contents(result))
    assert 'label="query.csv"' in rendered
    assert 'value-preview="42 rows"' in rendered


def test_tool_result_display_open_serializes_expanded():
    request = _request()
    display = ToolResultDisplay(open=True)
    result = _result(request, extra={"display": display})

    rendered = _render(tool_result_contents(result))
    assert "expanded" in rendered


def test_tool_result_display_open_absent_by_default():
    request = _request()
    result = _result(request)

    assert "expanded" not in _render(tool_result_contents(result))


def test_tool_request_never_serializes_expanded():
    kwargs: dict[str, Any] = {
        "request_id": "call-1",
        "tool_name": "my_tool",
        "arguments": '{"x": 1}',
        # Pydantic ignores unknown constructor fields by default. Preserve that
        # compatibility while ensuring a request cannot leak this stale wire
        # attribute.
        "expanded": True,
    }
    request = ToolRequestComponent(**kwargs)

    assert not hasattr(request, "expanded")
    assert "expanded" not in _render(request)


def test_tool_result_display_label_and_value_preview_absent_by_default():
    request = _request()
    result = _result(request)

    rendered = _render(tool_result_contents(result))
    assert "label=" not in rendered
    assert "value-preview=" not in rendered


# ---------------------------------------------------------------------------
# 3. Per-tool `grouping` annotation propagation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grouping_value", ["all", "none"])
def test_tool_annotation_grouping_propagates_to_request_and_result(
    grouping_value: str,
):
    tool = _tool(
        annotations={"title": "My Tool", "extra": {"grouping": grouping_value}}
    )
    request = _request(tool=tool)
    result = _result(request)

    request_html = _render(tool_request_contents(request))
    result_html = _render(tool_result_contents(result))

    assert f'grouping="{grouping_value}"' in request_html
    assert f'grouping="{grouping_value}"' in result_html


@pytest.mark.parametrize(
    "bogus_grouping",
    ["bogus", ["all"], {"nested": "all"}],
)
def test_tool_annotation_invalid_grouping_omits_attribute(bogus_grouping: Any):
    tool = _tool(
        annotations={"title": "My Tool", "extra": {"grouping": bogus_grouping}}
    )
    request = _request(tool=tool)
    result = _result(request)

    request_html = _render(tool_request_contents(request))
    result_html = _render(tool_result_contents(result))

    assert "grouping=" not in request_html
    assert "grouping=" not in result_html


def test_tool_annotation_grouping_top_level_also_supported():
    # Top-level annotation keys survive at runtime, but are outside chatlas's
    # `ToolAnnotations` typing; `annotations["extra"]` is the
    # type-checker-friendly spelling. This test exercises the top-level
    # fallback with a hand-built `ContentToolRequest.tool` value.
    request = _request()
    request.tool = ToolInfo(
        name="my_tool",
        description="",
        parameters={},
    )
    request.tool.annotations = {"grouping": "all"}  # type: ignore[assignment]

    request_html = _render(tool_request_contents(request))
    assert 'grouping="all"' in request_html


def _request_with_raw_annotations(annotations: Any) -> ContentToolRequest:
    # Bypasses `ToolInfo`'s validation so that malformed annotations (which a
    # hand-built or mutated `ToolInfo` can carry) reach the rendering path.
    request = _request()
    request.tool = ToolInfo(name="my_tool", description="", parameters={})
    request.tool.annotations = annotations
    return request


def test_tool_annotation_non_dict_extra_falls_back_to_top_level():
    request = _request_with_raw_annotations(
        {"extra": "oops", "grouping": "all", "icon": "<span>i</span>"}
    )
    result = _result(request)

    request_html = _render(tool_request_contents(request))
    result_html = _render(tool_result_contents(result))

    assert 'grouping="all"' in request_html
    assert 'grouping="all"' in result_html
    assert 'icon="&lt;span&gt;i&lt;/span&gt;"' in request_html
    assert 'icon="&lt;span&gt;i&lt;/span&gt;"' in result_html


def test_tool_annotation_non_dict_extra_omits_grouping_and_icon():
    request = _request_with_raw_annotations(
        {"title": "My Tool", "extra": "oops"}
    )
    result = _result(request)

    request_html = _render(tool_request_contents(request))
    result_html = _render(tool_result_contents(result))

    assert "grouping=" not in request_html
    assert "grouping=" not in result_html
    assert "icon=" not in request_html
    assert "icon=" not in result_html
    assert 'tool-title="My Tool"' in result_html


# ---------------------------------------------------------------------------
# 3b. Definition icon on the request, so the client can spot a result-specific
#     icon (the request card itself renders no icon).
# ---------------------------------------------------------------------------


def test_tool_annotation_icon_propagates_to_request_and_result():
    tool = _tool(annotations={"extra": {"icon": "<span>i</span>"}})
    request = _request(tool=tool)
    result = _result(request)

    escaped = 'icon="&lt;span&gt;i&lt;/span&gt;"'
    assert escaped in _render(tool_request_contents(request))
    # The result echoes the definition icon when it sets none of its own, so the
    # client sees the two as equal and treats the icon as the tool's identity.
    assert escaped in _render(tool_result_contents(result))


def test_tool_result_display_icon_differs_from_the_request_icon():
    tool = _tool(annotations={"extra": {"icon": "<span>i</span>"}})
    request = _request(tool=tool)
    result = _result(
        request, extra={"display": ToolResultDisplay(icon="<span>j</span>")}
    )

    # The request keeps the definition icon while the result carries its own:
    # the difference is exactly what makes it result-specific on the client.
    assert 'icon="&lt;span&gt;i&lt;/span&gt;"' in _render(
        tool_request_contents(request)
    )
    assert 'icon="&lt;span&gt;j&lt;/span&gt;"' in _render(
        tool_result_contents(result)
    )


def test_tool_request_omits_icon_without_an_annotation():
    request = _request(tool=_tool(annotations={"title": "My Tool"}))

    assert "icon=" not in _render(tool_request_contents(request))


# ---------------------------------------------------------------------------
# 4. SHINYCHAT_TOOL_DISPLAY x grouping matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("override", ["basic", "none"])
def test_tool_display_override_renders_without_crashing(
    override: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", override)

    tool = _tool(annotations={"title": "My Tool", "extra": {"grouping": "all"}})
    request = _request(tool=tool)
    display = ToolResultDisplay(label="query.csv", value_preview="42 rows")
    result = _result(request, extra={"display": display})

    # Should not raise regardless of override.
    request_component = tool_request_contents(request)
    result_component = tool_result_contents(result)

    if override == "none":
        # Bare fallback: no component, nothing rendered.
        assert request_component is None
        assert result_component is None
    else:
        # "basic": still renders a tool result element, but suppresses the
        # per-call display metadata (label / value_preview) -- only the raw
        # model-visible value comes through.
        result_html = _render(result_component)
        assert "shiny-tool-result" in result_html
        assert "label=" not in result_html
        assert "value-preview=" not in result_html


def test_tool_display_override_basic_suppresses_display_but_keeps_title(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", "basic")

    tool = _tool(annotations={"title": "My Tool"})
    request = _request(tool=tool)
    result = _result(
        request,
        extra={"display": ToolResultDisplay(title="Overridden title")},
    )

    rendered = _render(tool_result_contents(result))
    # display.title is suppressed by the "basic" override, so the tool
    # annotation's title is used instead.
    assert 'tool-title="My Tool"' in rendered
    assert "Overridden title" not in rendered


# ---------------------------------------------------------------------------
# 5. Fully-custom tool result UI: `_append_message_chunk` wraps an author's
#    `message_content_chunk` override for a `ContentToolResult` subclass in a
#    real `<shiny-tool-result custom-display>`, so the client always has an
#    element to pair against the request.
# ---------------------------------------------------------------------------


class _CustomToolResult(ContentToolResult):
    """Stand-in for an author's own `ContentToolResult` subclass."""


@pytest.fixture
def custom_display_handler():
    """Register a `message_content_chunk` handler and undo it afterward.

    `singledispatch` registries (like `message_content_chunk`'s) are
    process-global, so a handler left registered here would leak into
    unrelated tests that happen to run later in the same process.
    """
    registry = gc.get_referents(message_content_chunk.registry)[0]
    before = set(registry)

    def _register(handler: Any) -> None:
        message_content_chunk.register(_CustomToolResult, handler)

    yield _register

    for key in list(registry):
        if key not in before:
            del registry[key]
    message_content_chunk._clear_cache()


@pytest.fixture
def custom_message_handler():
    """Register a complete-message handler and undo it afterward."""
    registry = gc.get_referents(message_content.registry)[0]
    before = set(registry)

    def _register(handler: Any) -> None:
        message_content.register(_CustomToolResult, handler)

    yield _register

    for key in list(registry):
        if key not in before:
            del registry[key]
    message_content._clear_cache()


async def _stream_custom_result(result: ContentToolResult) -> list[Any]:
    """Drive `result` through `chat._append_message_chunk`, capturing what's sent."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_append(message: Any, **kwargs: Any) -> None:
        sent.append(message)

    async def capture_action(*args: Any, **kwargs: Any) -> None:
        pass

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_append_message = capture_append  # type: ignore[method-assign]
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._append_message_chunk(result, stream_id="s1")

    return sent


@pytest.mark.anyio
async def test_custom_tool_result_handler_is_wrapped_in_a_result_element(
    custom_display_handler: Any,
) -> None:
    """An author's bare custom UI must still reach the client as a structured
    `tool_result` block, or the client has no block to pair against the request
    and the request row spins forever."""

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=Tag("div", "Custom UI", class_="my-custom-ui")
        )

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block["request_id"] == "call-1"
    assert block["tool_name"] == "my_tool"
    assert block["status"] == "success"
    assert block.get("value_type") == "html"
    assert "Custom UI" in block.get("value", "")
    assert "my-custom-ui" in block.get("value", "")


@pytest.mark.anyio
async def test_custom_tool_result_fold_escapes_bare_strings(
    custom_display_handler: Any,
) -> None:
    """roborev 1166 regression: a bare string carrying executable HTML inside
    a custom display TagList must reach the HTML-valued tool_result fold
    escaped. TagList content is an HTML container, so TagList().render()
    escapes the string before the fold; the client renders value_type="html"
    via RawHTML (innerHTML), where an unescaped string would be an XSS sink.
    """

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=TagList(
                '<img src=x onerror="alert(1)">', Tag("div", "safe")
            )
        )

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    block = sent[0].blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("value_type") == "html"
    value = block.get("value", "")
    assert "<img src=x onerror=" not in value
    assert "&lt;img src=x onerror=" in value
    assert "safe" in value


@pytest.mark.anyio
async def test_custom_string_result_stays_markdown(
    custom_display_handler: Any,
) -> None:
    """A handler returning a plain string must keep `value_type="markdown"`.

    `ChatMessage.__init__` only renders non-strings, so such a message keeps
    `content_type="markdown"` and an unrendered payload. Forcing `"html"` would
    drop the markdown formatting *and* move the string off the client's
    markdown pipeline (inert React elements) onto `RawHTML`'s live `innerHTML`,
    where event-handler attributes fire.
    """

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content="**Sunny**, 72F")

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block.get("value_type") == "markdown"
    assert block.get("value") == "**Sunny**, 72F"


@pytest.mark.anyio
async def test_custom_result_via_append_message_is_wrapped(
    custom_message_handler: Any,
) -> None:
    """`append_message()` must wrap too, not just the streaming path.

    Its own docs point authors at `message_content`, and a handler registered
    there returns custom UI with no structured block at all unless this path
    wraps as well.
    """
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    def handler(message: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=Tag("div", "Custom UI", class_="my-custom-ui")
        )

    custom_message_handler(handler)
    sent: list[Any] = []

    async def capture_append(message: Any, **kwargs: Any) -> None:
        sent.append(message)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_append_message = capture_append  # type: ignore[method-assign]
        await chat.append_message(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block["request_id"] == "call-1"
    assert "my-custom-ui" in block.get("value", "")


def test_custom_result_via_chat_ui_messages_is_wrapped(
    custom_message_handler: Any,
) -> None:
    """A direct static result must be wrapped even outside a Turn.

    A Turn already wraps each content item in its own normalizer, but
    chat_ui(messages=[request, result]) normalizes the two items separately.
    The result therefore needs the same post-normalization wrap as
    append_message().
    """
    dep = HTMLDependency(
        "static-custom-widget",
        "1.0.0",
        head=HTML("<meta name='static-custom-widget'>"),
    )

    def handler(message: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=Tag("div", dep, "Custom UI", class_="my-custom-ui")
        )

    custom_message_handler(handler)
    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)

    ui = chat_ui("chat", messages=[request, result])

    messages_container = next(
        child
        for child in ui.children
        if isinstance(child, Tag) and child.name == "shiny-chat-messages"
    )
    assert not [
        child
        for child in messages_container.children
        if isinstance(child, Tag) and child.name == "shiny-chat-message"
    ]

    attr = ui.attrs.get("data-initial-messages")
    assert isinstance(attr, str)
    entries = json.loads(attr)
    assert len(entries) == 2
    request_entry, result_entry = entries

    request_blocks = [s for s in request_entry["segments"] if "type" in s]
    assert [b["type"] for b in request_blocks] == ["tool_request"]
    assert request_blocks[0]["request_id"] == "call-1"

    result_blocks = [s for s in result_entry["segments"] if "type" in s]
    assert [b["type"] for b in result_blocks] == ["tool_result"]
    block = cast(ToolResultBlock, result_blocks[0])
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block["request_id"] == "call-1"
    assert "my-custom-ui" in block.get("value", "")


@pytest.mark.anyio
async def test_custom_tool_result_error_renders_like_a_successful_one(
    custom_display_handler: Any,
) -> None:
    """A failed custom call must still be wrapped -- `status="error"`, with
    `custom_display` still present -- not silently dropped."""

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content=Tag("div", "Something went wrong"))

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(
        value=None, error=Exception("boom"), request=request
    )
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block["status"] == "error"


@pytest.mark.anyio
async def test_plain_tool_result_is_not_misread_as_custom_display() -> None:
    """shinychat's own tool card (no author override) must never carry
    `custom_display` -- that flag is reserved for the bypass path."""
    result = _result(_request(tool=_tool()))
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    msg = sent[0]
    assert "<shiny-tool-result" not in msg.content
    assert len(msg.blocks) == 1
    block = msg.blocks[0]
    assert block["type"] == "tool_result"
    assert "custom_display" not in block


def test_plain_tool_result_uses_marker_message() -> None:
    result = _result(_request(tool=_tool()))

    msg = message_content(result)

    assert isinstance(msg, ShinyToolCardMessage)
    assert not hasattr(msg, "_tool_result")


@pytest.mark.anyio
async def test_custom_tool_result_wrap_uses_tool_grouping_annotation(
    custom_display_handler: Any,
) -> None:
    """Custom result wrapping shares the request/result annotation policy."""

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content=Tag("div", "Custom UI"))

    custom_display_handler(handler)

    request = _request(tool=_tool(annotations={"extra": {"grouping": "all"}}))
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("grouping") == "all"


@pytest.mark.anyio
async def test_tool_display_none_is_not_misread_as_custom_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`SHINYCHAT_TOOL_DISPLAY=none` yields an empty message -- shinychat's
    own return, not an author bypass -- so no `custom-display` either."""
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", "none")

    result = _result(_request(tool=_tool()))
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "custom-display" not in sent[0].content


@pytest.mark.anyio
async def test_custom_tool_result_html_dependencies_survive_the_wrap(
    custom_display_handler: Any,
) -> None:
    """Wrapping the author's UI in a structured `tool_result` block must not
    drop the `HTMLDependency` objects the UI carries -- they still need to reach
    the client."""
    dep = HTMLDependency("custom-widget", "1.0.0", head=HTML("<meta name='x'>"))

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content=Tag("div", dep, "Custom UI"))

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    dep_names = [d.name for d in sent[0].html_deps]
    assert "custom-widget" in dep_names


@pytest.mark.anyio
async def test_custom_tool_result_interleaved_content_preserves_order(
    custom_display_handler: Any,
) -> None:
    """When the author's custom UI has mixed content (a React element between
    two HTML islands), `_wrap_custom_tool_result` must rebuild from `parts` so
    the interleaving order is preserved — not concatenate all string content
    then all html_block content (which would reorder the islands around the
    React element)."""
    from htmltools import Tag, TagList, div

    react_el = Tag(
        "shiny-tool-result",
        data_shinychat_react=True,
        request_id="abc",
        class_="react-mid",
    )
    # Island → React → Island: parts should be [block, str, block]
    ui = TagList(div("before"), react_el, div("after"))

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content=ui)

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    # The wrapper carries the folded content in its `value` (HTML string).
    value = block.get("value", "")
    before_pos = value.index("before")
    react_pos = value.index("react-mid")
    after_pos = value.index("after")
    assert before_pos < react_pos < after_pos


@pytest.mark.anyio
async def test_custom_result_inside_a_turn_is_wrapped() -> None:
    """A `Turn` carrying a custom tool result must wrap it too."""
    from chatlas import Turn
    from shinychat import message_content

    registry = gc.get_referents(message_content.registry)[0]
    before = set(registry)

    def handler(message: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=Tag("div", "Custom UI", class_="my-custom-ui")
        )

    message_content.register(_CustomToolResult, handler)
    try:
        request = _request(tool=_tool())
        turn = Turn(
            [_CustomToolResult(value=2, request=request)], role="assistant"
        )
        msg = message_content(turn)
    finally:
        for key in list(registry):
            if key not in before:
                del registry[key]
        message_content._clear_cache()

    assert "<shiny-tool-result" not in msg.content
    blocks = msg.blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block["request_id"] == "call-1"
    assert "my-custom-ui" in block.get("value", "")


@pytest.mark.anyio
async def test_custom_result_inside_a_turn_keeps_html_dependencies() -> None:
    """Pairing the result is not enough -- its dependencies must arrive too."""
    from chatlas import Turn
    from shinychat import message_content

    dep = HTMLDependency("turn-widget", "1.0.0", head=HTML("<meta name='y'>"))

    registry = gc.get_referents(message_content.registry)[0]
    before = set(registry)

    def handler(message: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content=Tag("div", dep, "Custom UI"))

    message_content.register(_CustomToolResult, handler)
    try:
        request = _request(tool=_tool())
        turn = Turn(
            [_CustomToolResult(value=2, request=request)], role="assistant"
        )
        msg = message_content(turn)
    finally:
        for key in list(registry):
            if key not in before:
                del registry[key]
        message_content._clear_cache()

    assert "<shiny-tool-result" not in msg.content
    assert len(msg.blocks) == 1
    assert msg.blocks[0]["type"] == "tool_result"
    assert "turn-widget" in [d.name for d in msg.html_deps]


@pytest.mark.anyio
async def test_custom_tool_result_attachments_survive_the_wrap(
    custom_display_handler: Any,
) -> None:
    """Wrapping replaces the author's `ChatMessage`, so anything it set beyond
    the content -- notably `attachments` -- must be carried across rather than
    silently reset to the constructor defaults."""
    from shinychat.types import Attachment

    attachment = Attachment(
        mime="image/png",
        data_url="data:image/png;base64,AAA",
        name="chart.png",
    )

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(
            content=Tag("div", "Custom UI"), attachments=[attachment]
        )

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    assert len(sent[0].blocks) == 1
    assert sent[0].blocks[0]["type"] == "tool_result"
    assert [a.name for a in sent[0].attachments] == ["chart.png"]


@pytest.mark.anyio
async def test_custom_text_result_stays_routable(
    custom_display_handler: Any,
) -> None:
    """A `content_type="text"` handler must still produce a routable message.

    The client deliberately excludes text blocks from tool routing ("text"
    means display literally), so the wrapped element has to travel in an
    html/markdown container or it renders as visible markup and never pairs
    with its request. `value_type` still records that the payload itself is
    text.
    """

    def handler(chunk: _CustomToolResult) -> ChatMessage:
        return ChatMessage(content="Sunny, 72F", content_type="text")

    custom_display_handler(handler)

    request = _request(tool=_tool())
    result = _CustomToolResult(value=2, request=request)
    sent = await _stream_custom_result(result)

    assert len(sent) == 1
    assert "<shiny-tool-result" not in sent[0].content
    blocks = sent[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "tool_result"
    assert block.get("custom_display") is True
    assert block.get("value_type") == "text"


# ---------------------------------------------------------------------------
# Structured `tool_result` blocks
# ---------------------------------------------------------------------------


def test_plain_tool_result_normalizes_to_structured_block() -> None:
    """A plain ContentToolResult must normalize to a ChatMessage carrying a
    structured `tool_result` block."""
    result = _result(_request(tool=_tool()))

    msg = message_content(result)

    assert "<shiny-tool-result" not in msg.content
    assert len(msg.blocks) == 1
    block = msg.blocks[0]
    assert block["type"] == "tool_result"
    assert block["version"] == 1
    assert block["request_id"] == "call-1"
    assert block["tool_name"] == "my_tool"
    assert block["status"] == "success"
    assert block.get("value") == "2"
    assert block.get("value_type") == "code"


@pytest.mark.anyio
async def test_stream_emits_block_insert_action_for_structured_block() -> None:
    """Mid-stream, a structured block must travel as a `block_insert` action
    while string content keeps flowing through ordered `chunk` actions."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._append_message_chunk("", chunk="start", stream_id="s1")
        await chat._append_message_chunk("working", chunk=True, stream_id="s1")
        await chat._append_message_chunk(
            _result(_request(tool=_tool())), stream_id="s1"
        )
        await chat._append_message_chunk("done", chunk=True, stream_id="s1")

    types = [a["type"] for a in sent]
    assert types == ["chunk_start", "chunk", "block_insert", "chunk"]

    chunks = [a for a in sent if a["type"] == "chunk"]
    assert [c["content"] for c in chunks] == ["working", "done"]
    assert all("<shiny-tool-result" not in c["content"] for c in chunks)

    block_action = sent[2]
    assert block_action["block"]["type"] == "tool_result"
    assert block_action["block"]["request_id"] == "call-1"


@pytest.mark.anyio
async def test_append_message_includes_structured_block_in_segments() -> None:
    """A non-streaming `append_message` must carry the structured block as a
    typed entry in the message payload's `segments`."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat.append_message(_result(_request(tool=_tool())))

    assert len(sent) == 1
    action = sent[0]
    assert action["type"] == "message"
    segments = action["message"]["segments"]

    block_segments = [s for s in segments if s.get("type") == "tool_result"]
    assert len(block_segments) == 1
    block = block_segments[0]
    assert block["version"] == 1
    assert block["request_id"] == "call-1"
    assert block["tool_name"] == "my_tool"
    assert block["status"] == "success"
    assert block["value"] == "2"
    assert block["value_type"] == "code"

    string_segments = [s for s in segments if "content" in s]
    assert all(
        "<shiny-tool-result" not in s["content"] for s in string_segments
    )


# ---------------------------------------------------------------------------
# Structured `tool_request` blocks
# ---------------------------------------------------------------------------


def test_plain_tool_request_normalizes_to_structured_block() -> None:
    """A plain ContentToolRequest must normalize to a ChatMessage carrying a
    structured `tool_request` block."""
    request = _request(tool=_tool())

    msg = message_content(request)

    assert "<shiny-tool-request" not in msg.content
    assert not isinstance(msg, ShinyToolCardMessage)
    assert len(msg.blocks) == 1
    block = msg.blocks[0]
    assert block["type"] == "tool_request"
    assert block["version"] == 1
    assert block["request_id"] == "call-1"
    assert block["tool_name"] == "my_tool"
    assert block.get("arguments") == '{"x": 1}'


def test_tool_request_block_maps_the_full_field_surface() -> None:
    """Definition title/icon, `_intent`, and the grouping annotation all map
    onto the typed envelope."""
    tool = _tool(
        annotations={
            "title": "Looking up weather",
            "extra": {"icon": "<span>i</span>", "grouping": "all"},
        }
    )
    request = _request(
        tool=tool, arguments={"x": 1, "_intent": "check weather"}
    )

    msg = message_content(request)

    assert len(msg.blocks) == 1
    block = msg.blocks[0]
    assert block.get("title") == "Looking up weather"
    assert block.get("icon") == "<span>i</span>"
    assert block.get("intent") == "check weather"
    assert block.get("grouping") == "all"
    assert block.get("arguments") == '{"x": 1, "_intent": "check weather"}'


@pytest.mark.anyio
async def test_stream_emits_block_insert_action_for_tool_request() -> None:
    """Mid-stream, a structured request block must travel as a `block_insert`
    action while string content keeps flowing through ordered `chunk`
    actions."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat._append_message_chunk("", chunk="start", stream_id="s1")
        await chat._append_message_chunk("working", chunk=True, stream_id="s1")
        await chat._append_message_chunk(_request(tool=_tool()), stream_id="s1")
        await chat._append_message_chunk("done", chunk=True, stream_id="s1")

    types = [a["type"] for a in sent]
    assert types == ["chunk_start", "chunk", "block_insert", "chunk"]

    chunks = [a for a in sent if a["type"] == "chunk"]
    assert [c["content"] for c in chunks] == ["working", "done"]
    assert all("<shiny-tool-request" not in c["content"] for c in chunks)

    block_action = sent[2]
    assert block_action["block"]["type"] == "tool_request"
    assert block_action["block"]["request_id"] == "call-1"


@pytest.mark.anyio
async def test_append_message_includes_tool_request_block_in_segments() -> None:
    """A non-streaming `append_message` must carry the structured request
    block as a typed entry in the message payload's `segments`."""
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context
    from shinychat import Chat

    sent: list[Any] = []

    async def capture_action(action: Any, deps: Any = None) -> None:
        sent.append(action)

    with session_context(ExpressStubSession()):
        chat = Chat(id="chat")
        chat._send_action = capture_action  # type: ignore[method-assign]
        await chat.append_message(_request(tool=_tool()))

    assert len(sent) == 1
    action = sent[0]
    assert action["type"] == "message"
    segments = action["message"]["segments"]

    block_segments = [s for s in segments if s.get("type") == "tool_request"]
    assert len(block_segments) == 1
    block = block_segments[0]
    assert block["version"] == 1
    assert block["request_id"] == "call-1"
    assert block["tool_name"] == "my_tool"
    assert block["arguments"] == '{"x": 1}'

    string_segments = [s for s in segments if "content" in s]
    assert all(
        "<shiny-tool-request" not in s["content"] for s in string_segments
    )
