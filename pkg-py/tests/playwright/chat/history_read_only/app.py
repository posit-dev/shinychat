from __future__ import annotations

import tempfile
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, ui
from shinychat import Chat, chat_ui
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_store import ConversationPartition
from shinychat._history_types import (
    CapturedMessage,
    ErrorEntry,
    StateEntry,
    new_conversation_record_v2,
)
from shinychat.types import FileConversationStore, HistoryOptions


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

        async def response() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return response()


store = FileConversationStore(tempfile.mkdtemp(prefix="shinychat-read-only-"))


async def seed_conversation() -> None:
    partition = ConversationPartition(chat_id="chat", scope="test")
    if await store.get(partition, "saved_incompatible") is not None:
        return
    record = new_conversation_record_v2(
        id="saved_incompatible",
        title="Saved incompatible context",
        client_info={},
    )
    root_id = record.root_id
    record.nodes[root_id].state["shinychat:turns"] = StateEntry(
        kind="chatlas", version=2, mode="snapshot", data=[]
    )
    record.open_exchange(
        "original",
        StoredMessage(
            role="user",
            segments=[
                StoredSegment(
                    content="original question", content_type="markdown"
                )
            ],
        ),
    )
    record.append_message(
        "original",
        CapturedMessage.from_stored_message(
            StoredMessage(
                role="assistant",
                segments=[
                    StoredSegment(
                        content="original reply", content_type="markdown"
                    )
                ],
            ),
            icon=None,
        ),
    )
    record.nodes["original"].status = "error"
    record.nodes["original"].error = ErrorEntry(message="saved failure")
    record.set_active_leaf(root_id)
    record.open_exchange(
        "alternative",
        StoredMessage(
            role="user",
            segments=[
                StoredSegment(
                    content="alternative question", content_type="markdown"
                )
            ],
        ),
    )
    record.append_message(
        "alternative",
        CapturedMessage.from_stored_message(
            StoredMessage(
                role="assistant",
                segments=[
                    StoredSegment(
                        content="alternative reply", content_type="markdown"
                    )
                ],
            ),
            icon=None,
        ),
    )
    record.nodes["alternative"].status = "ok"
    record.set_active_leaf("original")
    await store.put(partition, record)


app_ui = ui.page_fillable(chat_ui("chat"))


def server(input: Inputs, output: Outputs, session: Session) -> None:
    @reactive.effect(priority=20_000)
    async def _seed_target() -> None:
        await seed_conversation()

    _chat = Chat(
        "chat",
        client=EchoChatClient(),
        history=HistoryOptions(store=store, scope="test", title=None),
    )


app = App(app_ui, server)
