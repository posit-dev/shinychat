from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from htmltools import HTMLDependency
from shinychat._chat_transcript import ChatTranscript, StreamCandidate
from shinychat._chat_types import (
    ChatMessage,
    Role,
    SerializedDep,
    StoredMessage,
    StoredSegment,
)


def load_matrix() -> list[dict[str, Any]]:
    matrix_path = (
        Path(__file__).parents[2]
        / "tests/shared/message-transcript-matrix.json"
    )
    return cast(list[dict[str, Any]], json.loads(matrix_path.read_text()))


def make_dependencies(
    dependencies: list[dict[str, Any]],
) -> list[HTMLDependency]:
    return [
        HTMLDependency(
            name=cast(str, dependency["name"]),
            version=cast(str, dependency["version"]),
            source={"subdir": "."},
        )
        for dependency in dependencies
    ]


def serialize_html_deps(
    dependencies: list[HTMLDependency] | None,
) -> list[SerializedDep] | None:
    if not dependencies:
        return None
    return [
        {"name": dependency.name, "version": str(dependency.version)}
        for dependency in dependencies
    ]


def fixture_message(value: dict[str, Any]) -> StoredMessage:
    return StoredMessage.model_validate(value)


def send_for(operation: dict[str, Any]) -> Callable[[], Awaitable[None]]:
    async def send() -> None:
        error = operation.get("send_error")
        if error is not None:
            raise RuntimeError(cast(str, error))

    return send


def candidate_to_stored(candidate: StreamCandidate) -> StoredMessage:
    return StoredMessage(
        role=candidate.role,
        segments=[
            StoredSegment(
                content=segment.content,
                content_type=segment.content_type,
                html_deps=serialize_html_deps(segment.html_deps),
            )
            for segment in candidate.segments
        ],
        attachments=list(candidate.attachments),
    )


def canonical_messages(transcript: ChatTranscript) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for message in transcript.read():
        dumped = message.model_dump(exclude_none=True)
        if not dumped.get("attachments"):
            dumped.pop("attachments", None)

        html_deps: list[dict[str, Any]] = []
        for segment in dumped["segments"]:
            html_deps.extend(segment.pop("html_deps", []) or [])
        if html_deps:
            dumped["htmlDeps"] = html_deps
        canonical.append(dumped)
    return canonical


async def apply_operation(
    transcript: ChatTranscript, operation: dict[str, Any]
) -> None:
    operation_type = cast(str, operation["type"])
    send = send_for(operation)

    if operation_type == "message":
        await transcript.append(fixture_message(operation), send=send)
        return

    if operation_type == "stream_start":
        await transcript.start(
            ChatMessage(content="", role=cast(Role, operation["role"])),
            stream_id=cast(str, operation["stream_id"]),
            send=send,
        )
        return

    if operation_type == "stream_chunk":
        message = ChatMessage(
            content=cast(str, operation["content"]),
            role="assistant",
            content_type=cast(
                Literal["markdown", "html", "text", "thinking"],
                operation["content_type"],
            ),
        )
        message.html_deps = make_dependencies(
            cast(list[dict[str, Any]], operation.get("html_deps", []))
        )

        async def chunk_send(
            candidate: StreamCandidate,
        ) -> StoredMessage | None:
            await send()
            return candidate_to_stored(candidate)

        await transcript.chunk(
            message,
            stream_id=cast(str, operation["stream_id"]),
            operation=cast(
                Literal["append", "replace"], operation["operation"]
            ),
            send=chunk_send,
        )
        return

    if operation_type == "stream_end":

        async def settle_send(candidate: StreamCandidate) -> StoredMessage:
            await send()
            return candidate_to_stored(candidate)

        await transcript.settle(
            stream_id=cast(str, operation["stream_id"]), send=settle_send
        )
        return

    if operation_type == "stream_abort":
        transcript.abort(cast(str, operation["stream_id"]))
        return

    if operation_type == "clear":
        await transcript.clear(send=send)
        return

    if operation_type == "replay":
        messages = [
            fixture_message(message)
            for message in cast(list[dict[str, Any]], operation["messages"])
        ]
        await transcript.replace(messages, send=send)
        return

    raise AssertionError(f"Unknown matrix operation: {operation_type}")


@pytest.mark.anyio
@pytest.mark.parametrize("case", load_matrix(), ids=lambda case: case["name"])
async def test_message_transcript_matrix(case: dict[str, Any]) -> None:
    transcript = ChatTranscript()

    async def apply_all() -> None:
        for operation in cast(list[dict[str, Any]], case["operations"]):
            await apply_operation(transcript, operation)

    if "error" in case:
        with pytest.raises(
            RuntimeError, match=re.escape(cast(str, case["error"]))
        ):
            await apply_all()
    else:
        await apply_all()

    assert canonical_messages(transcript) == case["expected"]
    if any(
        operation["type"] == "clear"
        for operation in cast(list[dict[str, Any]], case["operations"])
    ):
        assert transcript.active_stream_id is None
        assert transcript.active_segments == ()
