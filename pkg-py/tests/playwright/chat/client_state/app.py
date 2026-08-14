from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shinychat import Chat, chat_ui

# Regression test app for client-authoritative UI state: `.messages()` must
# read the client-reported snapshot, which is co-sent synchronously with the
# user's submission. So inside `on_user_submit`, `.messages()` should already
# include the just-submitted user turn.

app_ui = ui.page_fluid(
    chat_ui("chat"),
    ui.output_text_verbatim("count"),
    ui.output_text_verbatim("submits"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    chat = Chat("chat")
    seen = reactive.value(-1)
    submit_count = reactive.value(0)

    @chat.on_user_submit
    async def _(user_input: str):
        seen.set(len(chat.messages()))
        submit_count.set(submit_count() + 1)
        await chat.append_message(f"echo: {user_input}")

    @render.text
    def count():
        return str(seen())

    @render.text
    def submits():
        return str(submit_count())


app = App(app_ui, server)
