from pathlib import Path

from shiny import reactive
from shiny.express import input, ui
from shinychat import Attachment
from shinychat.express import Chat

ui.page_opts(fillable=True)

with ui.layout_columns(fill=False):
    ui.input_action_button("stage", "Stage attachment only")
    ui.input_action_button("stage_and_submit", "Stage and submit")
    ui.input_action_button("append", "Append second attachment")
    ui.input_action_button("set_replace", "Set-replace attachment")
    ui.input_action_button("append_and_submit", "Append and submit")

chat = Chat("chat")
chat.ui(allow_attachments=True)

FIXTURE = Path(__file__).parent / "sample.png"
FIXTURE2 = Path(__file__).parent / "sample.txt"


@reactive.effect
@reactive.event(input.stage)
def do_stage():
    att = Attachment.from_path(str(FIXTURE))
    chat.update_user_input(attachments=[att])


@reactive.effect
@reactive.event(input.stage_and_submit)
def do_stage_and_submit():
    att = Attachment.from_path(str(FIXTURE))
    chat.update_user_input(
        value="Check this image:",
        attachments=[att],
        submit=True,
    )


@reactive.effect
@reactive.event(input.append)
def do_append():
    att = Attachment.from_path(str(FIXTURE2))
    chat.update_user_input(attachments=[att])


@reactive.effect
@reactive.event(input.set_replace)
def do_set_replace():
    att = Attachment.from_path(str(FIXTURE2))
    chat.update_user_input(attachments=[att], attachment_mode="set")


@reactive.effect
@reactive.event(input.append_and_submit)
def do_append_and_submit():
    att = Attachment.from_path(str(FIXTURE2))
    chat.update_user_input(
        value="Append submit:",
        attachments=[att],
        submit=True,
    )


@chat.on_user_submit
async def on_submit(user_input: str, attachments: list[Attachment]) -> None:
    await chat.append_message(f"Got {len(attachments)} attachment(s).")
