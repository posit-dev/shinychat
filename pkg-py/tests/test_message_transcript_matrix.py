from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import ContentSegment, StoredMessage

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


def send_for(
    operation: dict[str, Any], transport: list[str]
) -> Callable[[], Awaitable[bool]]:
    async def send() -> bool:
        transport.append(cast(str, operation["operation"]))
        outcome = cast(dict[str, Any], operation["send"])
        if outcome["result"] == "error":
            raise RuntimeError(cast(str, outcome["message"]))
        return True

    return send


def sent_action(
    operation: dict[str, Any], transport: list[str]
) -> Callable[[], Awaitable[None]]:
    async def send() -> None:
        transport.append(cast(str, operation["operation"]))

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
    if entry.status is not None:
        wire_spec["status"] = entry.status
    if entry.error is not None:
        wire_spec["error"] = entry.error
    return wire_spec


def segments_for(operation: dict[str, Any]) -> list[ContentSegment]:
    return [
        ContentSegment.model_validate(segment)
        for segment in cast(list[dict[str, Any]], operation["source_segments"])
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("case", MATRIX, ids=lambda case: case["name"])
async def test_message_transcript_matrix(case: dict[str, Any]) -> None:
    transcript = ChatTranscript()
    exchanges: dict[str, str] = {}
    transport: list[str] = []

    async def apply_all() -> None:
        for operation in cast(list[dict[str, Any]], case["operations"]):
            kind = operation["operation"]
            try:
                if kind == "complete-message":
                    await transcript.append(
                        entry_for(operation),
                        send=send_for(operation, transport),
                    )
                elif kind == "accepted-input":
                    exchanges[cast(str, operation["exchange"])] = (
                        transcript.record_accepted_input(
                            entry_for(operation).message
                        )
                    )
                elif kind == "stream-start":
                    await transcript.start_stream(
                        stream_id=cast(str, operation["stream_id"]),
                        entry=entry_for(operation),
                        owner_task=None,
                        send=send_for(operation, transport),
                    )
                elif kind == "stream-chunk":
                    await transcript.transition_stream(
                        stream_id=cast(str, operation["stream_id"]),
                        source_segments=segments_for(operation),
                        message=entry_for(operation).message,
                        operation=cast(
                            Any, operation.get("transition", "append")
                        ),
                        send=send_for(operation, transport),
                    )
                elif kind == "stream-end":
                    await transcript.end_stream(
                        stream_id=cast(str, operation["stream_id"]),
                        source_segments=segments_for(operation),
                        message=entry_for(operation).message,
                        operation=cast(
                            Any, operation.get("transition", "append")
                        ),
                        status=cast(Any, operation.get("status")),
                        error=cast(str | None, operation.get("error_message")),
                        send=send_for(operation, transport),
                    )
                elif kind == "stream-abort":
                    transcript.abort_stream(
                        cast(str, operation["stream_id"]),
                        status=cast(Any, operation["status"]),
                        error=cast(str | None, operation.get("error_message")),
                    )
                elif kind == "clear":
                    await transcript.clear(
                        send=sent_action(operation, transport)
                    )
                elif kind == "defensive-read":
                    projection = transcript.read()
                    projection[cast(int, operation["entry"])].message.segments[
                        0
                    ].content = cast(str, operation["replacement"])
                else:
                    raise AssertionError(
                        f"Unknown transcript operation: {kind}"
                    )
            except RuntimeError as error:
                expected_error = operation.get("error", case.get("error"))
                if expected_error is None:
                    raise
                assert str(error) == expected_error
                if "error" not in operation:
                    return

    await apply_all()

    committed = transcript.read()
    assert [fixture_wire_spec(entry) for entry in committed] == case["expected"]
    assert transport == case["expected_transport"]
    for index, exchange in cast(
        dict[str, str], case.get("expected_exchanges", {})
    ).items():
        assert committed[int(index)].exchange_id == exchanges[exchange]
