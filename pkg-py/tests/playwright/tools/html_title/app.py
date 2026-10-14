from chatlas.types import ContentToolRequest, ContentToolResult
from shiny import reactive
from shiny.express import input, ui
from shinychat.express import Chat
from shinychat.types import ToolResultDisplay

ui.page_opts(fillable=True, title="HTML Title Test")

chat = Chat(id="chat")
chat.ui(messages=["Click the button to add a tool result with an HTML title."])

ui.input_action_button("add_tool", "Add tool result")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    request = ContentToolRequest(
        id="test-html-title", name="test_tool", arguments={}
    )
    await chat.append_message_stream(
        [
            request,
            ContentToolResult(
                value="Tool result content here",
                request=request,
                extra={
                    "display": ToolResultDisplay(
                        title="Map of <i>Paris</i>",
                        open=True,
                    )
                },
            ),
        ]
    )
