"""Canonical serializer fixture for the cross-language tool wire contract."""

from __future__ import annotations

import json
from pathlib import Path

from htmltools import HTML, TagList
from shinychat._chat_normalize_chatlas import (
    ToolRequestComponent,
    ToolResultComponent,
)


def _render(component: ToolRequestComponent | ToolResultComponent) -> str:
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
    )
    return request, result


def test_tool_wire_protocol_fixture_matches_python_serialization() -> None:
    fixture_path = (
        Path(__file__).parents[1] / "fixtures" / "tool-wire-protocol.json"
    )
    fixture = json.loads(fixture_path.read_text())
    request, result = _protocol_components()

    assert _render(request) == fixture["request"]
    assert _render(result) == fixture["result"]
