from pathlib import Path

from shiny.express import ui
from shinychat.express import Chat
from shinychat.types import Attachment, ChatMessage

HERE = Path(__file__).parent

ui.page_opts(title="Append Assistant Attachment")

chat = Chat(id="chat")
chat.ui()


@chat.on_user_submit
async def handle_user_input(user_input: str) -> None:
    # Server-authored attachment via the public API: an assistant message that
    # carries an Attachment (no user upload involved).
    await chat.append_message(
        ChatMessage(
            "Here is the chart you asked for.",
            role="assistant",
            attachments=[Attachment.from_path(HERE / "one_px.png")],
        )
    )
