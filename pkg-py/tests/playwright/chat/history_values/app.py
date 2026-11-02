"""A region filter follows conversation checkpoints and position restores."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import chatlas
from chatlas import Turn
from chatlas._turn import AssistantTurn
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui
from shinychat.types import (
    FileConversationStore,
    HistoryOptions,
)


class FilterChatClient(chatlas.Chat):
    def __init__(
        self,
        get_filter: Callable[[], str],
        set_filter: Callable[[str], None],
        before_filter: reactive.Value[str],
    ) -> None:
        provider = MagicMock()
        provider.name = "filter-echo"
        provider.model = "filter-echo"
        super().__init__(provider, system_prompt="Track the selected region.")
        self.get_filter = get_filter
        self.set_filter = set_filter
        self.before_filter = before_filter

    async def stream_async(
        self, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        region = str(args[0])
        self.before_filter.set(self.get_filter())
        # Like a tool that updates both app state and its visible control.
        self.set_filter(region)
        answer = f"Selected {region}"
        self._turns.extend(
            [
                Turn(role="user", contents=region),
                AssistantTurn(contents=answer),
            ]
        )

        async def response() -> AsyncGenerator[str, None]:
            yield answer

        return response()


store = FileConversationStore(
    dir=tempfile.mkdtemp(prefix="shinychat-history-values-")
)

app_ui = ui.page_fillable(
    ui.input_text("region_filter", "Region filter", value="all"),
    ui.output_text("current_filter"),
    ui.output_text("provider_before_filter"),
    ui.output_text("restore_log"),
    ui.output_text("restore_count"),
    chat_ui("chat"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    selected_filter = reactive.Value("all")
    before_filter = reactive.Value("")
    restores: reactive.Value[list[dict[str, Any]]] = reactive.Value([])

    def sync_filter(region: str) -> None:
        # Server state changes immediately; the input update travels to the
        # browser asynchronously, so the provider need not wait for its echo.
        selected_filter.set(region)
        ui.update_text("region_filter", value=region)

    client = FilterChatClient(selected_filter.get, sync_filter, before_filter)
    chat = Chat(
        "chat",
        client=client,
        history=HistoryOptions(
            store=store, scope="test-user", restore_mode="browser", title=None
        ),
    )

    @reactive.effect
    @reactive.event(input.region_filter)
    def accept_filter_input() -> None:
        selected_filter.set(input.region_filter())

    @chat.history.on_save
    def save_filter(values: dict[str, Any]) -> None:
        values["filter"] = selected_filter.get()

    @chat.history.on_restore
    def restore_filter(values: dict[str, Any]) -> None:
        sync_filter(str(values.get("filter", "all")))
        restores.set(restores.get() + [dict(values)])

    @render.text
    def current_filter() -> str:
        return selected_filter.get()

    @render.text
    def provider_before_filter() -> str:
        return before_filter.get()

    @render.text
    def restore_log() -> str:
        return json.dumps(restores.get())

    @render.text
    def restore_count() -> str:
        return str(len(restores.get()))


app = App(app_ui, server)
