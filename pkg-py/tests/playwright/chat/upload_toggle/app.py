from shiny.express import ui
from shinychat._attachments import Attachment
from shinychat.express import Chat

ui.page_opts(title="Upload toggle")

# Two chats: one with attachments explicitly enabled, one explicitly disabled.
chat_on = Chat(id="chat_on")
chat_on.ui(allow_attachments=True)

chat_off = Chat(id="chat_off")
chat_off.ui(allow_attachments=False)


@chat_on.on_user_submit
async def _(user_input: str, attachments: list[Attachment]) -> None:
    await chat_on.append_message(f"on: {len(attachments)} image(s)")


@chat_off.on_user_submit
async def _(user_input: str) -> None:
    await chat_off.append_message("off")
