"""Non-streaming tool flow: structured blocks via append_message.

This app injects a ``ContentToolRequest`` and ``ContentToolResult`` pair
through the non-streaming ``chat.append_message(...)`` action (NOT
``append_message_stream``).  The structured blocks must flow through the
``message`` action the same way they flow through streaming chunks, so the
tool group row and card render with the title and result value visible.
"""

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
    # Non-streaming append_message: each call sends one complete message.
    # The request creates a tool_request block; the result creates a
    # tool_result block.  The client pairs them by request_id.
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
