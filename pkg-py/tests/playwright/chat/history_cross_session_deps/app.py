"""
Regression app: HTMLDependency objects carried by chat messages must survive
a cross-session history restore — i.e. reloading the page fresh (a brand new
session) and then restoring a saved conversation from the history drawer.

This exercises both message paths:
  * `append_message()` (non-streaming) via a direct side-effect call.
  * `append_message_stream()` (streaming) via the auto-wired `client=`
    handler's generator.

Each path carries a distinct HTMLDependency with a distinct marker
stylesheet, so the test can confirm both dependencies are individually
re-registered after restore.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from htmltools import HTMLDependency, TagList, tags
from shiny import App, Inputs, Outputs, Session
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

CSS_DIR = Path(__file__).parent / "_test_assets"

non_stream_dep = HTMLDependency(
    name="cross-session-nonstream-card",
    version="1.0.0",
    source={"subdir": str(CSS_DIR)},
    stylesheet=[{"href": "custom.css"}],
)


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

        # Non-streaming path: append a message carrying an HTMLDependency
        # directly, alongside (not as part of) the streamed reply below.
        assert self.shinychat_chat is not None
        await self.shinychat_chat.append_message(
            TagList(
                non_stream_dep,
                tags.div(
                    {"class": "cross-session-nonstream-card"},
                    f"non-stream dep for: {user_input}",
                ),
            )
        )

        async def _gen() -> AsyncGenerator[Any, None]:
            # Streaming path: the auto-wired `client=` handler appends this
            # generator's output via `append_message_stream()`.
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-deps-")

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
