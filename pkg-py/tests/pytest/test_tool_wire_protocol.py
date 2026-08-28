"""Canonical serializer fixture for the cross-language tool wire contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from chatlas.types import ContentToolRequest, ContentToolResult
from htmltools import HTML, Tagifiable, TagList
from pydantic import ValidationError
from shinychat._chat_normalize_chatlas import (
    ToolRequestComponent,
    ToolResultComponent,
    tool_result_contents,
)
from shinychat.types import ToolResultDisplay


def _render(component: Tagifiable) -> str:
    return TagList(component.tagify()).render()["html"]


def _protocol_components() -> tuple[ToolRequestComponent, ToolResultComponent]:
    request = ToolRequestComponent(
        request_id="wire-1",
        tool_name="search",
        tool_title="Searching",
        icon=HTML("<i>search</i>"),
        grouping="all",
        intent="Find docs",
        arguments='{"q":"shiny"}',
    )
    result = ToolResultComponent(
        request_id="wire-1",
        tool_name="search",
        tool_title="Searched",
        icon=HTML("<i>done</i>"),
        grouping="all",
        intent="Find docs",
        status="success",
        label="docs",
        value_preview="3 results",
        value="Result body",
        value_type="markdown",
        request_call='search(q="shiny")',
        show_request=True,
        full_screen=True,
        expanded=True,
        custom_display=False,
        footer=HTML("<span>footer</span>"),
        open_style="framed",
    )
    return request, result


def test_tool_result_display_open_style_is_validated() -> None:
    display = ToolResultDisplay(open_style="framed")

    assert display.open_style == "framed"

    with pytest.raises(ValidationError, match="open_style"):
        ToolResultDisplay(open_style=cast(Any, "panel"))


def test_tool_wire_protocol_fixture_matches_python_serialization() -> None:
    fixture_path = (
        Path(__file__).parents[1] / "fixtures" / "tool-wire-protocol.json"
    )
    fixture = json.loads(fixture_path.read_text())
    request, result = _protocol_components()

    assert _render(request) == fixture["request"]
    assert _render(result) == fixture["result"]


def test_tool_wire_protocol_fixture_matches_structured_blocks() -> None:
    """The structured-block wire contract (kata#c15v): both languages emit
    these exact block payloads; the markup above is the legacy tagify path."""
    from shinychat._chat_normalize_chatlas import (
        tool_request_block,
        tool_result_block,
    )

    fixture_path = (
        Path(__file__).parents[1] / "fixtures" / "tool-wire-protocol.json"
    )
    fixture = json.loads(fixture_path.read_text())
    request, result = _protocol_components()

    request_block, _ = tool_request_block(request)
    result_block, _ = tool_result_block(result)

    assert request_block == fixture["blocks"]["request"]
    assert result_block == fixture["blocks"]["result"]


def test_minimal_tool_result_open_style_is_not_serialized() -> None:
    request = ContentToolRequest(
        id="wire-default",
        name="search",
        arguments={"q": "shiny"},
    )
    result = ContentToolResult(
        value="Result body",
        request=request,
        extra={"display": ToolResultDisplay()},
    )

    assert "open-style=" not in _render(tool_result_contents(result))
