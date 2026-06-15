from shiny import reactive
from shiny.express import render, ui
from shinychat._attachments import Attachment
from shinychat.express import Chat

ui.page_opts(title="Attachment Input")

chat = Chat(id="chat")
chat.ui(allow_attachments=["application/pdf"])

n_attachments = reactive.value(-1)
first_type = reactive.value("")
first_name = reactive.value("")


@chat.on_user_submit
async def handle_user_input(
    user_input: str, attachments: list[Attachment]
) -> None:
    n_attachments.set(len(attachments))
    if attachments:
        first_type.set(attachments[0].mime)
        first_name.set(attachments[0].name)
    await chat.append_message(f"Got {len(attachments)} attachment(s).")


"Attachments received:"


@render.code
def received() -> str:
    return (
        f"n={n_attachments.get()} "
        f"type={first_type.get()} "
        f"name={first_name.get()}"
    )
