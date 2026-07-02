from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session
from shiny.ui import HTML
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

# Regression app for client-authoritative history + out-of-band content: a
# message appended outside the normal request/response turn (e.g. a
# side-channel notice) must be part of the client's `${id}_messages`
# snapshot, so it round-trips through a history save/restore just like the
# "real" assistant reply.
#
# `Chat(client=...)` auto-registers its own `on_user_submit` handler (see
# `_setup_client` in `_chat.py`) that awaits `stream_async()` and appends the
# result via `append_message_stream()`. Adding a second, app-defined
# `on_user_submit` would fire independently and double-echo the reply, so the
# out-of-band message is appended as a side effect from inside
# `stream_async()` itself, which runs in the same on_user_submit invocation,
# before the streamed reply is appended.

OUT_OF_BAND_MARKER = "oob-marker-content"


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)
        self.shinychat_chat: Chat | None = None  # set once the Chat is constructed

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"echo: {user_input}"),
            ]
        )

        assert self.shinychat_chat is not None
        await self.shinychat_chat.append_message(
            HTML(f'<div id="{OUT_OF_BAND_MARKER}">out-of-band notice</div>')
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-oob-")

app_ui = chat_ui("chat")


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = EchoChatClient()
    chat = Chat(
        id="chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="test-user",
            title=None,
        ),
    )
    client.shinychat_chat = chat


app = App(app_ui, server)
