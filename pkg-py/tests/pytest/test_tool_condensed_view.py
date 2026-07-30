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

from typing import Any, cast

import pytest
from chatlas._tools import Tool
from chatlas.types import ContentToolRequest, ContentToolResult, ToolInfo
from htmltools import TagList
from shinychat import chat_ui
from shinychat._chat_normalize_chatlas import (
    ToolResultDisplay,
    tool_request_contents,
    tool_result_contents,
)


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
        # top-level annotation keys get silently dropped by pydantic, while
        # keys nested under `annotations["extra"]` survive untouched.
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
    # Top-level annotation keys are stripped by chatlas's `ToolInfo` model
    # once a tool round-trips through the real request pipeline, but the
    # top-level key is still honored as a fallback (e.g. for hand-built
    # `ContentToolRequest.tool` values that bypass that validation).
    request = _request()
    request.tool = ToolInfo(
        name="my_tool",
        description="",
        parameters={},
    )
    request.tool.annotations = {"grouping": "all"}  # type: ignore[assignment]

    request_html = _render(tool_request_contents(request))
    assert 'grouping="all"' in request_html


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

    request_html = _render(request_component)
    result_html = _render(result_component)

    if override == "none":
        # Bare fallback: nothing rendered at all.
        assert request_html == ""
        assert result_html == ""
    else:
        # "basic": still renders a tool result element, but suppresses the
        # per-call display metadata (label / value_preview) -- only the raw
        # model-visible value comes through.
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
