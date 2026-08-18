from shiny import App, Inputs, Outputs, Session, ui
from shinychat import chat_sidebar, page_chat

app_ui = page_chat(
    "Assistant",
    sidebar=chat_sidebar(
        ui.div("Sidebar content", style="width: 1200px"),
        width="fit-content",
        open="open",
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    pass


app = App(app_ui, server)
