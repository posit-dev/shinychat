from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import chatlas
import shinychat._history as history_module
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
)
from shinychat._history_types import new_conversation_record_v2
from shinychat.types import HistoryOptions

history_module._EXCHANGE_TREE_HISTORY_V2 = True

TARGET_ID = "startup-target"
TARGET_EXCHANGE_ID = "n_0001"
STORE = FileConversationStore(
    dir=Path(__file__).parent / "_history_initial_startup_barrier_store"
)
RESTORE_MODE = "browser"

app_ui = ui.page_fillable(
    ui.output_text("startup_exchange"),
    chat_ui("chat"),
)


def _target_record() -> Any:
    record = new_conversation_record_v2(
        title="startup target",
        id=TARGET_ID,
        client_info={},
    )
    record.open_exchange(
        TARGET_EXCHANGE_ID,
        StoredMessage(
            role="user",
            segments=[
                StoredSegment(
                    content="restored input",
                    content_type="markdown",
                )
            ],
        ),
    )
    return record


def server(input: Inputs, output: Outputs, session: Session) -> None:
    startup_exchange_value = reactive.Value("")

    @reactive.effect(priority=20_000)
    async def _seed_target() -> None:
        await STORE.put(
            ConversationPartition(chat_id="chat", scope="test-user"),
            _target_record(),
        )

    provider = MagicMock()
    provider.name = "test"
    provider.model = "test"
    chat = Chat(
        "chat",
        client=chatlas.Chat(provider),
        messages=["constructor message"],
        history=HistoryOptions(
            store=STORE,
            scope="test-user",
            restore_mode=RESTORE_MODE,
        ),
    )

    @reactive.effect
    async def _startup_append() -> None:
        await chat.append_message("startup append")
        controller = chat.history._controller
        assert controller is not None
        recorder = controller._exchange_recorder
        assert recorder is not None
        record = recorder.record
        assert record is not None
        active_id = record.active_leaf
        active = record.nodes[active_id] if active_id is not None else None
        startup_exchange_value.set(
            json.dumps(
                {
                    "active_id": active_id,
                    "parent_id": active.parent_id if active is not None else None,
                    "messages": [
                        message.as_stored_message().content
                        for message in active.messages
                    ]
                    if active is not None
                    else [],
                }
            )
        )

    @render.text
    def startup_exchange() -> str:
        return startup_exchange_value()


app = App(app_ui, server)
