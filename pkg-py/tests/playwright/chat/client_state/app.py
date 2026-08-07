from __future__ import annotations

import asyncio
import json
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
from shinychat.types import (
    Attachment,
    ChatMessageDict,
    FileConversationStore,
    HistoryOptions,
)

CSS_DIR = Path(__file__).parent / "_test_assets"

server_state_dep = HTMLDependency(
    name="server-state-card",
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
        self.shinychat_chat: Chat | None = None

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        user_input = str(args[0]) if args else ""
        self._turns.extend(
            [
                Turn(role="user", contents=user_input),
                AssistantTurn(contents=f"echo: {user_input}"),
            ]
        )

        chat = self.shinychat_chat
        if chat is None:
            raise RuntimeError("Chat is not initialized")
        await chat.append_message(
            {
                "content": TagList(
                    server_state_dep,
                    tags.div(
                        {"class": "server-state-card"},
                        f"server state for: {user_input}",
                    ),
                ),
                "role": "assistant",
                "attachments": [
                    Attachment.from_data(
                        b"server attachment",
                        "text/plain",
                        name="server-note.txt",
                    )
                ],
            }
        )

        async def generate() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return generate()


def serialize_messages(messages: tuple[ChatMessageDict, ...]) -> str:
    payload: list[dict[str, object]] = []
    for message in messages:
        serialized: dict[str, object] = dict(message)
        if "attachments" in message:
            serialized["attachments"] = [
                attachment.model_dump() for attachment in message["attachments"]
            ]
        payload.append(serialized)
    return json.dumps(payload)


def serialize_record(chat: Chat) -> str:
    controller = chat.history._controller
    if controller is None or controller.record is None:
        return "null"
    return json.dumps(controller.record.model_dump(mode="json"))


store_dir = tempfile.mkdtemp(prefix="shinychat-client-state-")

app_ui = ui.page_fluid(
    chat_ui("chat", messages=["static"], allow_attachments=True),
    ui.input_action_button("append_complete", "Append complete"),
    ui.input_action_button("append_stream", "Append stream"),
    ui.input_action_button("clear_messages", "Clear messages"),
    ui.output_text_verbatim("count"),
    ui.output_text_verbatim("submits"),
    ui.output_text_verbatim("messages"),
    ui.output_text_verbatim("bookmark"),
    ui.output_text_verbatim("record"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    client = EchoChatClient()
    chat = Chat(
        "chat",
        client=client,
        history=HistoryOptions(
            store=FileConversationStore(dir=store_dir),
            scope="test-user",
            title=None,
        ),
    )
    client.shinychat_chat = chat
    seen = reactive.value(-1)
    submit_count = reactive.value(0)
    save_count = reactive.value(0)
    restore_count = reactive.value(0)

    @chat.on_user_submit
    async def on_user_submit(_: str) -> None:
        seen.set(len(chat.messages()))
        submit_count.set(submit_count() + 1)

    @chat.history.on_save
    def on_history_save(_: dict[str, object]) -> None:
        save_count.set(save_count() + 1)

    @chat.history.on_restore
    def on_history_restore(_: dict[str, object]) -> None:
        restore_count.set(restore_count() + 1)

    @reactive.effect
    @reactive.event(input.append_complete)
    async def append_complete() -> None:
        await chat.append_message("complete server append")

    @reactive.effect
    @reactive.event(input.append_stream)
    async def append_stream() -> None:
        async def generate() -> AsyncGenerator[str, None]:
            yield "streamed response"
            await asyncio.sleep(3)
            yield " complete"

        await chat.append_message_stream(generate())

    @reactive.effect
    @reactive.event(input.clear_messages)
    async def clear_messages() -> None:
        await chat.clear_messages()

    @render.text
    def count() -> str:
        return str(seen())

    @render.text
    def submits() -> str:
        return str(submit_count())

    @render.text
    def messages() -> str:
        return serialize_messages(chat.messages())

    @render.text
    def bookmark() -> str:
        chat.messages()
        return json.dumps(chat._messages_for_bookmark())

    @render.text
    def record() -> str:
        save_count()
        restore_count()
        return serialize_record(chat)


app = App(app_ui, server)
