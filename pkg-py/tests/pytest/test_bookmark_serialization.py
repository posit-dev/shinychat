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
from chatlas import ChatOpenAI, ContentToolResult, Turn
from htmltools import HTMLDependency, TagList, tags
from pydantic_core import PydanticSerializationError
from shinychat._chat_bookmark import get_chatlas_state
from shinychat.types import ToolResultDisplay


async def serialize_bookmark_turn(turn: Turn[Any]) -> dict[str, Any]:
    client = ChatOpenAI(api_key="fake")
    client.set_turns([turn])
    state = await get_chatlas_state(client)()
    assert isinstance(state, dict)
    turns = state["turns"]
    assert isinstance(turns, list)
    dumped = turns[0]
    assert isinstance(dumped, dict)
    return dumped


@pytest.mark.anyio
@pytest.mark.parametrize("as_dict", [False, True])
async def test_turn_serialization_with_htmldep_in_tool_result(as_dict: bool):
    """Turn containing ToolResultDisplay with HTMLDependency round-trips through JSON."""
    typed_display = ToolResultDisplay(
        html=tags.div(
            "Widget output",
            HTMLDependency(
                "my-dep",
                "1.0",
                source={"subdir": "."},
                script={"src": "widget.js"},
                stylesheet={"href": "widget.css"},
                all_files=True,
            ),
        ),
        title="My Widget",
    )
    display: Any = typed_display
    if as_dict:
        display = {
            "html": typed_display.html,
            "title": typed_display.title,
            "application_metadata": {"widget_id": "my-widget"},
        }
    result = ContentToolResult(value="done", extra={"display": display})
    turn = Turn(role="user", contents=[result])

    dumped = await serialize_bookmark_turn(turn)

    assert turn.contents[0] is result
    assert result.extra["display"] is display

    # Must be JSON-serializable
    json_str = json.dumps(dumped)

    # Verify the serialized dependencies are JSON dicts (not live HTMLDependency objects)
    display_data = dumped["contents"][0]["extra"]["display"]
    assert set(display_data) >= {"html", "title"}
    if as_dict:
        assert "show_request" not in display_data
        assert "open" not in display_data
        assert display_data["application_metadata"] == {
            "widget_id": "my-widget"
        }
    dependencies = display_data["html"]["dependencies"]
    assert len(dependencies) == 1
    assert dependencies[0] == {
        "name": "my-dep",
        "version": "1.0",
        "source": {"subdir": "."},
        "script": [{"src": "widget.js"}],
        "stylesheet": [{"href": "widget.css", "rel": "stylesheet"}],
        "meta": [],
        "all_files": True,
        "head": None,
    }

    # Must round-trip back to a valid Turn
    restored = Turn.model_validate(json.loads(json_str))
    assert restored.role == "user"
    assert len(restored.contents) == 1
    assert isinstance(restored.contents[0], ContentToolResult)
    restored_display = ToolResultDisplay(**restored.contents[0].extra["display"])
    restored_dependency = TagList(restored_display.html).render()["dependencies"][
        0
    ]

    assert restored_dependency.source == {"subdir": "."}
    assert restored_dependency.script == [{"src": "widget.js"}]
    assert restored_dependency.stylesheet == [
        {"href": "widget.css", "rel": "stylesheet"}
    ]
    assert restored_dependency.all_files is True


def test_tool_result_display_restores_legacy_dependency_payload():
    legacy_display = {
        "html": {
            "html": '<div class="widget">Widget output</div>',
            "dependencies": [
                {
                    "name": "my-dep",
                    "version": "1.0",
                    "script": [{"src": "lib/my-dep-1.0/widget.js"}],
                    "stylesheet": [
                        {
                            "href": "lib/my-dep-1.0/widget.css",
                            "rel": "stylesheet",
                        }
                    ],
                    "meta": [],
                    "head": None,
                }
            ],
        }
    }

    display = ToolResultDisplay(**legacy_display)
    rendered = TagList(display.html).render()
    dependency = rendered["dependencies"][0]

    assert rendered["html"] == '<div class="widget">Widget output</div>'
    assert dependency.name == "my-dep"
    assert str(dependency.version) == "1.0"
    assert dependency.source is None
    assert dependency.script == [{"src": "lib/my-dep-1.0/widget.js"}]
    assert dependency.stylesheet == [
        {
            "href": "lib/my-dep-1.0/widget.css",
            "rel": "stylesheet",
        }
    ]

    new_value = display.model_dump(mode="json")
    new_dependency = new_value["html"]["dependencies"][0]

    assert "source" in new_dependency
    assert new_dependency["source"] is None
    assert new_dependency["all_files"] is False


@pytest.mark.anyio
async def test_turn_serialization_handles_htmltools_outside_tool_display():
    turn = Turn(
        role="user",
        contents=[
            ContentToolResult(
                value="done",
                extra={"application_metadata": tags.span("metadata")},
            )
        ],
    )

    dumped = await serialize_bookmark_turn(turn)

    assert dumped["contents"][0]["extra"]["application_metadata"] == {
        "html": "<span>metadata</span>",
        "dependencies": [],
    }


@pytest.mark.anyio
async def test_turn_serialization_rejects_unknown_objects():
    turn = Turn(
        role="user",
        contents=[
            ContentToolResult(
                value="done",
                extra={"application_metadata": object()},
            )
        ],
    )

    with pytest.raises(PydanticSerializationError, match="unknown type"):
        await serialize_bookmark_turn(turn)
