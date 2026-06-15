from shiny import reactive
from shiny.express import render, ui
from shinychat._attachments import Attachment
from shinychat.express import Chat

ui.page_opts(title="Image Input")

chat = Chat(id="chat")
chat.ui(allow_attachments=True)

n_images = reactive.value(-1)


@chat.on_user_submit
async def handle_user_input(
    user_input: str, attachments: list[Attachment]
) -> None:
    n_images.set(len(attachments))
    await chat.append_message(f"Got {len(attachments)} image(s).")


"Images received:"


@render.code
def received() -> str:
    return f"n_images={n_images.get()}"
