"""Registers the ``shinychat.userInput`` Shiny input handler.

The browser sends the user's submission as one composite value
(``{text, attachments}``) tagged ``:shinychat.userInput``. Shiny routes any
type-tagged input through a registered handler (and errors if none exists), so
this module must be imported for shinychat to work. The handler normalizes the
composite into a ``UserInput``-compatible dict so ``Chat`` can read it without
further coercion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shiny.input_handler import input_handlers

from ._attachments import Attachment
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
        raise TypeError(f"Expected str or dict from shinychat.userInput, got {type(value)!r}")
    attachments = [
        Attachment.model_validate(a) for a in (value.get("attachments") or [])
    ]
    return UserInputValue(text=str(value.get("text", "")), attachments=attachments)
