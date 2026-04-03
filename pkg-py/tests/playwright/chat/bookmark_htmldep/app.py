import chatlas
from htmltools import HTMLDependency, tags
from shiny import App, ui
from shinychat.types import ToolResultDisplay


def get_widget():
    """Get a widget. Always call this tool when the user asks for a widget."""
    return chatlas.ContentToolResult(
        value="Widget loaded successfully.",
        extra={
            "display": ToolResultDisplay(
                html=tags.div(
                    "Widget output",
                    HTMLDependency("my-dep", "1.0", source={"subdir": "."}),
                ),
                title="My Widget",
            )
        },
    )


chat_client = chatlas.ChatAuto(
    system_prompt="When the user says anything, call the get_widget tool. Do not ask for confirmation.",
)
chat_client.register_tool(get_widget)


def app_ui(request):
    return ui.page_fillable(
        ui.chat_ui("chat"),
    )


def server(input, output, session):
    chat = ui.Chat("chat")

    @chat.on_user_submit
    async def _():
        stream = await chat_client.stream_async(
            chat.user_input() or "", echo="none", content="all"
        )
        await chat.append_message_stream(stream)

    chat.enable_bookmarking(chat_client)


app = App(app_ui, server, bookmark_store="server")
