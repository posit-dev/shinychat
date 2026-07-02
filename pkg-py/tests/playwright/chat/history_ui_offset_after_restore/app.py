"""
Regression app for stale `ui_offset` after restore (see `replay_ui` in
`_history.py`).

`replay_ui` used to set `self.ui_offset` from
`len(self.chat._messages_for_bookmark())`, which reads the client-reported
`${id}_messages` input. That input is only updated by the BROWSER,
asynchronously, so immediately after `replay_ui`'s synchronous restore loop
it still holds the PREVIOUS conversation's snapshot. That stale offset then
clips the next turn's UI out of `extend_record_linear`'s
`ui_messages[ui_offset:]` slice, so the new node is saved with no `node.ui`
and later restores fall back to lossy `turn_fallback_markdown` (losing rich
HTML).

Each assistant reply carries a distinctive rich-UI marker (a styled
`<div>` with an HTMLDependency-provided border color) keyed to the turn
number, so the test can assert that a turn's *rich* UI - not just its
plain-text fallback - survives a *second* restore after a conversation
switch.
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
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import FileConversationStore, HistoryOptions

CSS_DIR = Path(__file__).parent / "_test_assets"

marker_dep = HTMLDependency(
    name="ui-offset-marker-card",
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
        self.shinychat_chat: Chat | None = (
            None  # set once the Chat is constructed
        )

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

        # Rich-UI reply: a styled card carrying an HTMLDependency, distinct
        # per turn via `user_input`. This is what must survive a *second*
        # restore intact -- if `ui_offset` goes stale, this card is dropped
        # from `node.ui` and the restore falls back to plain echoed text.
        assert self.shinychat_chat is not None
        await self.shinychat_chat.append_message(
            TagList(
                marker_dep,
                tags.div(
                    {"class": "ui-offset-marker-card"},
                    f"rich reply for: {user_input}",
                ),
            )
        )

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


store_dir = tempfile.mkdtemp(prefix="shinychat-history-ui-offset-")

app_ui = ui.page_fluid(chat_ui("chat"), ui.output_text_verbatim("save_count"))


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

    saves = reactive.value(0)

    @chat.history.on_save
    def _(values: dict[str, object]) -> None:
        saves.set(saves() + 1)

    @render.text
    def save_count():
        return str(saves())


app = App(app_ui, server)
