from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from htmltools import HTMLDependency
from shiny import Inputs, Session, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._chat_types import ChatMessage, Role, StoredMessage


class MatrixSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "matrix-session"
    input: Any

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _decrement_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


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


def fixture_message(value: dict[str, Any]) -> StoredMessage:
    return StoredMessage.model_validate(value)


def fixture_chat_message(value: dict[str, Any]) -> ChatMessage:
    segments = cast(list[dict[str, Any]], value["segments"])
    assert len(segments) == 1, (
        "fixture_chat_message() only supports single-segment complete messages"
    )
    segment = segments[0]
    return ChatMessage(
        content=cast(str, segment["content"]),
        role=cast(Role, value["role"]),
        content_type=cast(
            Literal["markdown", "html", "text", "thinking"],
            segment["content_type"],
        ),
        attachments=value.get("attachments"),
    )


def canonical_messages(chat: Chat) -> list[dict[str, Any]]:
    with reactive.isolate():
        messages = chat._messages()

    canonical: list[dict[str, Any]] = []
    for message in messages:
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


async def apply_operation(chat: Chat, operation: dict[str, Any]) -> None:
    operation_type = cast(str, operation["type"])
    if operation_type == "message":
        await chat.append_message(fixture_chat_message(operation))
        return

    if operation_type == "stream_start":
        await chat._append_message_chunk(
            ChatMessage(
                content="",
                role=cast(Role, operation["role"]),
            ),
            chunk="start",
            stream_id=cast(str, operation["stream_id"]),
        )
        return

    if operation_type == "stream_chunk":
        if chat._current_stream_id is None:
            raise ValueError(
                "Cannot apply a stream chunk without an active stream"
            )
        dependencies = make_dependencies(
            cast(list[dict[str, Any]], operation.get("html_deps", []))
        )
        message = ChatMessage(
            content=cast(str, operation["content"]),
            role="assistant",
            content_type=cast(
                Literal["markdown", "html", "text", "thinking"],
                operation["content_type"],
            ),
        )
        message.html_deps = dependencies
        await chat._append_message_chunk(
            message,
            chunk=True,
            stream_id=cast(str, operation["stream_id"]),
            operation=cast(
                Literal["append", "replace"], operation["operation"]
            ),
        )
        return

    if operation_type == "stream_end":
        if chat._current_stream_id is None:
            raise ValueError("Cannot end a stream without an active stream")
        await chat._append_message_chunk(
            "",
            chunk="end",
            stream_id=cast(str, operation["stream_id"]),
        )
        return

    if operation_type == "stream_abort":
        await chat._abort_message_stream(cast(str, operation["stream_id"]))
        return

    if operation_type == "clear":
        await chat.clear_messages()
        return

    if operation_type == "replay":
        messages = [
            fixture_message(message)
            for message in cast(list[dict[str, Any]], operation["messages"])
        ]
        chat._replace_messages(messages)
        return

    raise AssertionError(f"Unknown matrix operation: {operation_type}")


@pytest.mark.anyio
@pytest.mark.parametrize("case", load_matrix(), ids=lambda case: case["name"])
async def test_message_transcript_matrix(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = cast(Session, MatrixSession())

    with session_context(session):
        chat = Chat("matrix", history=False)

        async def send_action(
            action: Any,
            html_deps: Any = None,
        ) -> None:
            return None

        def serialize_html_deps(
            dependencies: list[HTMLDependency] | None,
        ) -> list[dict[str, object]] | None:
            if not dependencies:
                return None
            return [
                {"name": dependency.name, "version": str(dependency.version)}
                for dependency in dependencies
            ]

        monkeypatch.setattr(chat, "_send_action", send_action)
        monkeypatch.setattr(chat, "_serialize_html_deps", serialize_html_deps)

        async def apply_all() -> None:
            for operation in cast(list[dict[str, Any]], case["operations"]):
                await apply_operation(chat, operation)

        if "error" in case:
            with pytest.raises(
                ValueError, match=re.escape(cast(str, case["error"]))
            ):
                await apply_all()
        else:
            await apply_all()
            assert canonical_messages(chat) == case["expected"]
            if any(
                operation["type"] == "clear"
                for operation in cast(list[dict[str, Any]], case["operations"])
            ):
                assert chat._current_stream_id is None
                assert chat._current_stream_segments == []
                assert chat._message_stream_segments_checkpoint == []
                assert chat._pending_messages == []
