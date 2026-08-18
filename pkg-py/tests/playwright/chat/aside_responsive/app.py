from shiny.express import ui
from shinychat.express import Chat

ui.page_opts(title="Aside Test")

chat = Chat(id="chat")
chat.ui()

LONG_LABEL = "source" * 40
LONG_BODY = " ".join(["A detailed source explanation."] * 100)


async def fake_stream():
    yield "Claim"
    yield (
        f'<shiny-aside label="{LONG_LABEL}" url="https://example.com/source">'
        f"{LONG_BODY}</shiny-aside>."
    )


@chat.on_user_submit
async def _():
    await chat.append_message_stream(fake_stream())
