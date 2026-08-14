from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chatlas import Turn


def serialize_chatlas_turn(turn: Turn[Any]) -> dict[str, Any]:
    """Serialize a chatlas turn after normalizing supported rich displays."""
    from chatlas import ContentToolResult

    from ._chat_normalize_chatlas import ToolResultDisplay

    normalized = turn
    for index, content in enumerate(turn.contents):
        if not isinstance(content, ContentToolResult):
            continue
        extra = content.extra
        if not isinstance(extra, dict) or not isinstance(
            extra.get("display"), dict
        ):
            continue

        if normalized is turn:
            normalized = turn.model_copy(deep=True)
        normalized_content = normalized.contents[index]
        assert isinstance(normalized_content, ContentToolResult)
        normalized_content.extra = dict(normalized_content.extra)
        display = normalized_content.extra["display"]
        normalized_content.extra["display"] = {
            **display,
            **ToolResultDisplay(**display).model_dump(mode="json"),
        }

    return normalized.model_dump(mode="json")
