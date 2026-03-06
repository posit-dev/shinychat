from shiny import reactive
from shiny.express import input, ui
from shiny.ui import HTML
from shinychat.express import Chat

ui.page_opts(fillable=True, title="Fullscreen Tool Test")

chat = Chat(id="chat")
chat.ui(messages=["Click the button to add a tool result card."])

ui.input_action_button("add_tool", "Add tool result")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    tool_html = HTML(
        '<shiny-tool-result '
        'request-id="test-123" '
        'tool-name="test_tool" '
        'tool-title="Test Tool" '
        'value="Tool result content here" '
        'value-type="text" '
        'status="success" '
        "expanded "
        "full-screen "
        ">"
        "</shiny-tool-result>"
    )
    await chat.append_message(tool_html)
