from chatlas.types import (
    ContentCitation,
    ContentText,
    ContentToolRequestSearch,
    ContentToolResponseFetch,
    ContentToolResponseSearch,
    Source,
)
from shiny.express import render, ui
from shinychat.express import Chat

ui.page_opts(title="Web Citations Test")

chat = Chat(id="chat")
chat.ui()


async def fake_stream():
    yield ContentToolRequestSearch(query="e-bike motor types")
    yield ContentToolResponseSearch(
        sources=[
            Source(
                url="https://ebicycles.example/hub-vs-mid-drive",
                title="Hub Motor vs. Mid-Drive Motor Differences Explained",
                domain="ebicycles.example",
            ),
        ]
    )
    yield ContentToolResponseFetch(
        url="https://ebicycles.example/hub-vs-mid-drive", status="success"
    )
    yield ContentText(text="Hub motors are cheaper and simpler")
    yield ContentCitation(
        url="https://ebicycles.example/hub-vs-mid-drive",
        title="Hub Motor vs. Mid-Drive Motor Differences Explained",
    )
    yield ContentText(text=", and ideal for flatter terrain. ")
    # A second, distinct source cited in the same sentence — both collapse
    # into one pill: the first source's label as the face, "+1" overflow.
    yield ContentCitation(
        url="https://wired.example/ebike-motors",
        title="How Electric Bike Motors Work",
    )
    # Blank line starts a new paragraph, so this aside lands in a
    # separate block/group from the two citations above.
    yield ContentText(text="\n\nBattery quality matters more than raw power")
    # A developer/LLM-authored generic aside with no url/label at all —
    # the public <shiny-aside> convention, not sourced from chatlas.
    yield (
        "<shiny-aside>Measured across 40 commuter e-bike models "
        "released in 2024.</shiny-aside>"
    )
    yield ContentText(text=".")
    yield ContentText(text=" Range depends on battery")
    yield ContentCitation(
        url="https://ebicycles.example/hub-vs-mid-drive",
        title="Hub Motor vs. Mid-Drive Motor Differences Explained",
    )
    yield ContentText(text=" and again on the same source")
    yield ContentCitation(
        url="https://ebicycles.example/hub-vs-mid-drive",
        title="Hub Motor vs. Mid-Drive Motor Differences Explained",
    )
    yield ContentText(text=".")


@chat.on_user_submit
async def _():
    await chat.append_message_stream(fake_stream())


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
