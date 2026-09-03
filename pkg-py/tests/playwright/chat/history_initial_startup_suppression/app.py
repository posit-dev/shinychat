from __future__ import annotations

import json
import os
import tempfile
from typing import Any, AsyncGenerator
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
RESTORE_MODE = "browser"
_store_dirs: dict[int, str] = {}

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


def _store_dir() -> str:
    pid = os.getpid()
    if pid not in _store_dirs:
        _store_dirs[pid] = tempfile.mkdtemp(
            prefix="shinychat-history-initial-startup-"
        )
    return _store_dirs[pid]


class EchoStreamChatClient(chatlas.Chat):
    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        user_input = str(args[0]) if args else ""

        async def stream() -> AsyncGenerator[str, None]:
            yield f"echo: {user_input}"

        return stream()


def server(input: Inputs, output: Outputs, session: Session) -> None:
    startup_exchange_value = reactive.Value("")
    store = FileConversationStore(dir=_store_dir())

    @reactive.effect(priority=20_000)
    async def _seed_target() -> None:
        await store.put(
            ConversationPartition(chat_id="chat", scope="test-user"),
            _target_record(),
        )

    provider = MagicMock()
    provider.name = "test"
    provider.model = "test"
    chat = Chat(
        "chat",
        client=EchoStreamChatClient(provider),
        messages=["constructor message"],
        history=HistoryOptions(
            store=store,
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
        active_id = record.active_leaf if record is not None else None
        active = (
            record.nodes[active_id]
            if record is not None and active_id is not None
            else None
        )
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
