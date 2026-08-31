from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import HistoryOptions


class EchoChatClient(chatlas.Chat):
    def __init__(self) -> None:
        provider = MagicMock()
        provider.name = "echo"
        provider.model = "echo"
        super().__init__(provider)

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

        async def _gen() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return _gen()


app_ui = ui.page_fillable(
    ui.output_text("submissions"),
    chat_ui("chat", allow_attachments=True),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    submission_count = reactive.value(0)
    chat = Chat(
        id="chat",
        client=EchoChatClient(),
        history=HistoryOptions(store="memory", scope="test-user", title=None),
    )
    controller = chat.history._controller
    assert controller is not None
    original_new = controller.new_chat
    original_delete = controller.delete

    async def wait_then_new() -> None:
        await asyncio.sleep(0.5)
        await original_new()

    async def wait_then_delete(conversation_id: str) -> None:
        await asyncio.sleep(0.5)
        await original_delete(conversation_id)

    controller.new_chat = wait_then_new  # type: ignore[method-assign]
    controller.delete = wait_then_delete  # type: ignore[method-assign]

    @chat.on_user_submit
    async def _(user_input: str) -> None:
        submission_count.set(submission_count.get() + 1)
        await chat.append_message(f"echo: {user_input}")

    @render.text
    def submissions() -> str:
        return str(submission_count.get())


app = App(app_ui, server)
