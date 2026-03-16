from htmltools import Tag

from shiny import reactive
from shiny.express import input, ui
from shinychat.express import Chat

ui.page_opts(fillable=True, title="Fullscreen Tool Test")

chat = Chat(id="chat")
chat.ui(messages=["Click the button to add a tool result card."])

ui.input_action_button("add_tool", "Add tool result")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    tool_tag = Tag(
        "shiny-tool-result",
        data_shinychat_react=True,
        request_id="test-123",
        tool_name="test_tool",
        tool_title="Test Tool",
        value="Tool result content here",
        value_type="text",
        status="success",
        expanded="",
        full_screen="",
    )
    await chat.append_message(tool_tag)
