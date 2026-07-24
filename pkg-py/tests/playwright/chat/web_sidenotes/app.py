from shiny.express import render, ui
from shinychat.express import Chat

ui.page_opts(title="Web Sidenotes Test")

chat = Chat(id="chat")
chat.ui()


async def fake_stream():
    # The public <shiny-sidenote> convention: any markdown content (chatlas
    # web citations or otherwise) can carry these tags directly, with no
    # further processing needed.
    yield "Hub motors are cheaper"
    yield (
        '<shiny-sidenote label="eBicycles" url="https://ebicycles.example/hub-vs-mid-drive">'
        "[Hub Motor vs. Mid-Drive Motor Differences Explained]"
        "(https://ebicycles.example/hub-vs-mid-drive)"
        "</shiny-sidenote>"
    )
    yield ", and ideal for flatter terrain. "
    # A second, distinct source cited in the same sentence — both collapse
    # into one pill: the first source's label as the face, "+1" overflow.
    yield (
        '<shiny-sidenote label="WIRED" url="https://wired.example/ebike-motors">'
        "[How Electric Bike Motors Work](https://wired.example/ebike-motors)"
        "</shiny-sidenote>"
    )
    # Blank line starts a new paragraph, so this sidenote lands in a
    # separate block/group from the two above.
    yield "\n\nBattery quality matters more than raw power"
    # A label-less sidenote with a rich block body authored inline.
    yield (
        "<shiny-sidenote>\n\n"
        "**Methodology**\n\n"
        "- 40 commuter e-bike models\n"
        "- released in 2024\n\n"
        "</shiny-sidenote>"
    )
    yield "."


@chat.on_user_submit
async def _():
    await chat.append_message_stream(fake_stream())


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
