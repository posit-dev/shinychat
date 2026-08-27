from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import StoredMessage

MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "shared"
    / "message-transcript-matrix.json"
)
MATRIX = cast(list[dict[str, Any]], json.loads(MATRIX_PATH.read_text()))


def entry_for(operation: dict[str, Any]) -> TranscriptEntry:
    wire_spec = cast(dict[str, Any], operation["wire_spec"])
    return TranscriptEntry(
        message=StoredMessage.model_validate(wire_spec["message"]),
        icon=cast(str | None, wire_spec.get("icon")),
    )


def send_for(operation: dict[str, Any]) -> Callable[[], Awaitable[bool]]:
    async def send() -> bool:
        outcome = cast(dict[str, Any], operation["send"])
        if outcome["result"] == "error":
            raise RuntimeError(cast(str, outcome["message"]))
        return True

    return send


def fixture_wire_spec(entry: TranscriptEntry) -> dict[str, Any]:
    message = entry.message
    message_spec: dict[str, Any] = {
        "role": message.role,
        "segments": [
            {
                **{
                    "content": segment.content,
                    "content_type": segment.content_type,
                },
                **(
                    {"html_deps": segment.html_deps}
                    if segment.html_deps is not None
                    else {}
                ),
            }
            for segment in message.segments
        ],
    }
    if message.attachments:
        message_spec["attachments"] = [
            {
                "mime": attachment.mime,
                "data_url": attachment.data_url,
                "name": attachment.name,
                "size": attachment.size,
            }
            for attachment in message.attachments
        ]

    wire_spec: dict[str, Any] = {"message": message_spec}
    if entry.icon is not None:
        wire_spec["icon"] = entry.icon
    return wire_spec


@pytest.mark.anyio
@pytest.mark.parametrize("case", MATRIX, ids=lambda case: case["name"])
async def test_message_transcript_matrix(case: dict[str, Any]) -> None:
    transcript = ChatTranscript()

    async def apply_all() -> None:
        for operation in cast(list[dict[str, Any]], case["operations"]):
            assert operation["operation"] == "complete-message"
            await transcript.append(
                entry_for(operation), send=send_for(operation)
            )

    if "error" in case:
        with pytest.raises(
            RuntimeError, match=re.escape(cast(str, case["error"]))
        ):
            await apply_all()
    else:
        await apply_all()

    assert [fixture_wire_spec(entry) for entry in transcript.read()] == case[
        "expected"
    ]
