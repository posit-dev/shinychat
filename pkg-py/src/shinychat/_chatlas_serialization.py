from __future__ import annotations

from typing import Any


def serialize_chatlas_turn(turn: Any) -> dict[str, Any]:
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
        normalized_content.extra = dict(normalized_content.extra)
        normalized_content.extra["display"] = ToolResultDisplay(
            **normalized_content.extra["display"]
        )

    return normalized.model_dump(mode="json")
