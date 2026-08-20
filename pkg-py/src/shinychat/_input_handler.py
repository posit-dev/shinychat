"""Registers the ``shinychat.userInput`` and ``shinychat.messages`` Shiny input
handlers.

The browser sends the user's submission as one composite value
(``{text, attachments}``) tagged ``:shinychat.userInput``. Shiny routes any
type-tagged input through a registered handler (and errors if none exists), so
this module must be imported for shinychat to work. The handler normalizes the
composite into a ``UserInput``-compatible dict so ``Chat`` can read it without
further coercion.

The client also co-sends a full UI message snapshot tagged
``:shinychat.messages`` alongside the user input, so the ``shinychat.messages``
handler deserializes that snapshot into ``StoredMessage`` objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shiny.input_handler import input_handlers

from ._attachments import (
    Attachment,
    validate_attachments,
)
from ._chat_types import StoredMessage, StoredSegment
from ._typing_extensions import TypedDict

if TYPE_CHECKING:
    from shiny.module import ResolvedId
    from shiny.session import Session


class UserInputValue(TypedDict):
    text: str
    attachments: list[Attachment]


@input_handlers.add("shinychat.userInput")
def _(value: Any, _name: "ResolvedId", _session: "Session") -> UserInputValue:
    if isinstance(value, str):
        return UserInputValue(text=value, attachments=[])
    if not isinstance(value, dict):
        raise TypeError(
            f"Expected str or dict from shinychat.userInput, got {type(value)!r}"
        )
    attachments = [
        Attachment.model_validate(a) for a in (value.get("attachments") or [])
    ]
    validate_attachments(attachments)
    return UserInputValue(
        text=str(value.get("text", "")), attachments=attachments
    )


def messages_input_value(value: Any) -> list[StoredMessage]:
    # Shiny's websocket JSON decoding converts every JSON array to a Python
    # tuple (see shiny._utils.lists_to_tuples), so a JSON array arrives here
    # as a tuple, not a list.
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"Expected list or tuple from shinychat.messages, got {type(value)!r}"
        )
    messages: list[StoredMessage] = []
    for m in value:
        # This snapshot is the authoritative record for persistence, so a
        # malformed message is a client/protocol bug we surface loudly rather
        # than silently drop (which would be invisible data loss on save). The
        # R handler (chat_history_types.R) takes the same posture.
        html_deps = m.get("htmlDeps")
        segments = [
            StoredSegment(
                content=s["content"],
                content_type=s["content_type"],
                html_deps=html_deps if i == 0 else None,
            )
            for i, s in enumerate(m.get("segments", []))
        ]
        attachments = [
            Attachment.model_validate(a) for a in (m.get("attachments") or [])
        ]
        validate_attachments(attachments)
        messages.append(
            StoredMessage(
                role=m["role"], segments=segments, attachments=attachments
            )
        )
    return messages


@input_handlers.add("shinychat.messages")
def _(
    value: Any, _name: "ResolvedId", _session: "Session"
) -> list[StoredMessage]:
    return messages_input_value(value)
