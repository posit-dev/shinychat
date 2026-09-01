"""Temporary JSON adapter for htmltools values.

Keep shinychat serialization behind this module until htmltools exposes a
source-preserving rendered-HTML codec; migration should then be confined to
this boundary.
"""

from __future__ import annotations

from typing import Any, Optional

from htmltools import RenderedHTML, TagList, is_tag_child
from pydantic_core import PydanticSerializationError
from typing_extensions import TypedDict


class SerializedHTML(TypedDict):
    html: str
    dependencies: list[dict[str, Any]]


def render_htmltools(value: object) -> RenderedHTML:
    """Validate, tagify, and render an htmltools node."""
    if not is_tag_child(value):
        raise PydanticSerializationError(
            f"Unable to serialize unknown type: {type(value)}"
        )

    return TagList(value).tagify().render()


def serialize_htmltools(value: object | None) -> Optional[SerializedHTML]:
    """Convert an htmltools node to shinychat's current JSON wire format.

    ``None`` passes through unchanged so callers can forward optional fields
    (e.g. pydantic ``field_serializer`` hooks) without a separate guard.
    """
    if value is None:
        return None
    rendered = render_htmltools(value)
    return {
        "html": rendered["html"],
        "dependencies": [
            dependency.as_dict() for dependency in rendered["dependencies"]
        ],
    }
