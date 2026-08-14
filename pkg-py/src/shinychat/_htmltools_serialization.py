"""Temporary JSON adapter for htmltools values.

Keep shinychat serialization behind this module until htmltools exposes a
source-preserving rendered-HTML codec; migration should then be confined to
this boundary.
"""

from __future__ import annotations

from typing import Any

from htmltools import TagList, is_tag_child
from pydantic_core import PydanticSerializationError
from typing_extensions import TypedDict


class SerializedHTML(TypedDict):
    html: str
    dependencies: list[dict[str, Any]]


def serialize_htmltools(value: object) -> SerializedHTML:
    """Convert an htmltools node to shinychat's current JSON wire format."""
    if not is_tag_child(value):
        raise PydanticSerializationError(
            f"Unable to serialize unknown type: {type(value)}"
        )

    rendered = TagList(value).render()
    return {
        "html": rendered["html"],
        "dependencies": [
            dependency.as_dict() for dependency in rendered["dependencies"]
        ],
    }
