from chatlas.types import ContentToolRequest, ContentToolResult
from faicons import icon_svg
from shiny import reactive
from shiny.express import input, ui
from shiny.ui import value_box
from shinychat import message_content_chunk
from shinychat.express import Chat
from shinychat.types import ChatMessage

ui.page_opts(fillable=True, title="Custom Tool Output Test")


class CustomToolResult(ContentToolResult):
    """Stand-in for an author's own `ContentToolResult` subclass that renders
    fully custom UI (a `value_box`) instead of shinychat's tool card."""


@message_content_chunk.register
def _(message: CustomToolResult):
    content = value_box(
        "Custom Output",
        "42",
        showcase=icon_svg("star"),
        id="custom_tool_output",
    )
    return ChatMessage(content=content)


async def _tool_call_stream():
    request = ContentToolRequest(
        id="custom-call-1", name="custom_tool", arguments={}
    )
    yield request
    yield CustomToolResult(value="done", request=request)


chat = Chat(id="chat")
chat.ui(
    messages=["Click the button to run a tool call with fully custom output."]
)

ui.input_action_button("add_tool", "Run tool call")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    await chat.append_message_stream(_tool_call_stream())
