from __future__ import annotations

from typing import Any, cast

import pytest
from shiny import Inputs, Session
from shiny._deprecated import ShinyDeprecationWarning
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat, chat_ui


class _MockSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "mock-session"
    input: Any

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId(""))

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        pass


test_session = cast(Session, _MockSession())


def test_chat_messages_requires_history_false():
    with session_context(test_session):
        with pytest.raises(ValueError, match="requires `history=False`"):
            Chat(id="chat", messages=["Hello"])


def test_chat_messages_with_history_false_warns():
    with session_context(test_session):
        with pytest.warns(
            ShinyDeprecationWarning,
            match=r"`Chat\(messages=\.\.\.\)` is deprecated",
        ):
            Chat(id="chat", messages=["Hello"], history=False)


def test_chat_ui_messages_warns():
    with pytest.warns(ShinyDeprecationWarning):
        chat_ui("chat", messages=["Hello"])
