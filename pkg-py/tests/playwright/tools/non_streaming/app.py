"""Non-streaming tool flow: structured blocks via append_message."""

from chatlas.types import ContentToolRequest, ContentToolResult
from shiny import reactive
from shiny.express import input, ui
from shinychat.express import Chat
from shinychat.types import ToolResultDisplay

ui.page_opts(fillable=True, title="Non-Streaming Tool Flow Test")

chat = Chat(id="chat")
chat.ui(messages=["Click the button to add a non-streaming tool result."])

ui.input_action_button("add_tool", "Add tool result (non-streaming)")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    request = ContentToolRequest(
        id="non-stream-1",
        name="lookup_tool",
        arguments={},
    )
    await chat.append_message(request)
    await chat.append_message(
        ContentToolResult(
            value="Non-streaming result body",
            request=request,
            extra={
                "display": ToolResultDisplay(
                    title="Looked up data",
                    open=True,
                )
            },
        )
    )
