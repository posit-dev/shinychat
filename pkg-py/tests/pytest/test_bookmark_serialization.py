"""
Regression test for https://github.com/posit-dev/shinychat/issues/188

Bookmarking failed with PydanticSerializationError when a tool result
contained a ToolResultDisplay with HTMLDependency objects, because the
field serializer produced non-JSON-serializable output.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from chatlas import ContentToolResult, Turn
from htmltools import HTMLDependency, tags
from shinychat._chatlas_serialization import serialize_chatlas_turn
from shinychat.types import ToolResultDisplay


@pytest.mark.parametrize("as_dict", [False, True])
def test_turn_serialization_with_htmldep_in_tool_result(as_dict: bool):
    """Turn containing ToolResultDisplay with HTMLDependency round-trips through JSON."""
    typed_display = ToolResultDisplay(
        html=tags.div(
            "Widget output",
            HTMLDependency("my-dep", "1.0", source={"subdir": "."}),
        ),
        title="My Widget",
    )
    display: Any = typed_display
    if as_dict:
        display = {
            "html": typed_display.html,
            "title": typed_display.title,
        }
    result = ContentToolResult(value="done", extra={"display": display})
    turn = Turn(role="user", contents=[result])

    dumped = serialize_chatlas_turn(turn)

    # Must be JSON-serializable
    json_str = json.dumps(dumped)

    # Verify the serialized dependencies are JSON dicts (not live HTMLDependency objects)
    display_data = dumped["contents"][0]["extra"]["display"]
    deps = display_data["html"]["dependencies"]
    assert len(deps) == 1
    assert deps[0]["name"] == "my-dep"
    assert deps[0]["version"] == "1.0"

    # Must round-trip back to a valid Turn
    restored = Turn.model_validate(json.loads(json_str))
    assert restored.role == "user"
    assert len(restored.contents) == 1
    assert isinstance(restored.contents[0], ContentToolResult)
