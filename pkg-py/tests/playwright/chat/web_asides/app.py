from shiny.express import render, ui
from shinychat.express import Chat

ui.page_opts(title="Web Asides Test")

chat = Chat(id="chat")
with ui.div(
    {
        "data-bs-theme": "dark",
        "style": (
            "--bs-body-bg: rgb(18, 18, 18);"
            "--bs-body-color: rgb(238, 238, 238);"
            "--bs-emphasis-color-rgb: 238, 238, 238;"
        ),
    }
):
    chat.ui()

LONG_ASIDE_LABEL = "source" * 40
LONG_ASIDE_BODY = " ".join(["A detailed source explanation."] * 100)


async def fake_stream():
    # The public <shiny-aside> convention: any markdown content (chatlas
    # web citations or otherwise) can carry these tags directly, with no
    # further processing needed.
    yield "Hub motors are cheaper"
    yield (
        '<shiny-aside label="eBicycles" url="https://ebicycles.example/hub-vs-mid-drive">'
        "[Hub Motor vs. Mid-Drive Motor Differences Explained]"
        "(https://ebicycles.example/hub-vs-mid-drive)"
        "</shiny-aside>"
    )
    yield ", and ideal for flatter terrain. "
    # A second, distinct source cited in the same sentence — both collapse
    # into one pill: the first source's label as the face, "+1" overflow.
    yield (
        '<shiny-aside label="WIRED" url="https://wired.example/ebike-motors">'
        "[How Electric Bike Motors Work](https://wired.example/ebike-motors)"
        "</shiny-aside>"
    )
    # Blank line starts a new paragraph, so this aside lands in a
    # separate block/group from the two above.
    yield "\n\nBattery quality matters more than raw power"
    # A label-less aside with a rich block body authored inline.
    yield (
        "<shiny-aside>\n\n"
        "**Methodology**\n\n"
        "- 40 commuter e-bike models\n"
        "- released in 2024\n\n"
        "</shiny-aside>"
    )
    yield "."
    yield "\n\nLong source details"
    yield (
        f'<shiny-aside label="{LONG_ASIDE_LABEL}" url="https://example.com/long">'
        f"{LONG_ASIDE_BODY}"
        "</shiny-aside>"
    )
    yield "\n\n- A list claim with a rich citation  \n"
    yield (
        '<shiny-aside label="List source" url="https://example.com/list-source">'
        "\n\n"
        "**List methodology**\n\n"
        "- Evidence one\n"
        "- Evidence two\n\n"
        "</shiny-aside>"
    )
    yield "\n\nNumbered source one"
    yield (
        '<shiny-aside display="compact" label="Policy A">'
        "Policy A evidence."
        "</shiny-aside>"
    )
    yield " and numbered source two"
    yield (
        '<shiny-aside display="compact" label="Policy B">'
        "Policy B evidence."
        "</shiny-aside>"
    )
    yield "."
    yield (
        "\n\n"
        '<shiny-aside label="Final source" url="https://example.com/final-source">'
        "\n\n"
        "**Final methodology**\n\n"
        "> Final supporting evidence.\n\n"
        "</shiny-aside>"
    )


@chat.on_user_submit
async def _():
    await chat.append_message_stream(fake_stream())


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
