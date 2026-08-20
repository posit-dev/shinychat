import asyncio
from collections.abc import AsyncIterator

from shiny.express import ui
from shinychat.express import Chat

ui.page_opts(title="Numbered labeled asides", fillable=True)

chat = Chat(id="chat")
chat.ui(placeholder="Submit any message to render the smoke cases")


@chat.on_user_submit
async def _(user_input: str) -> None:
    await chat.append_message_stream(smoke_response())


async def smoke_response() -> AsyncIterator[str]:
    chunks = (
        "## Compact aside smoke cases\n\n",
        "### Sequence, label, and icon\n\n",
        "An anonymous aside consumes the first message-wide number",
        "<shiny-aside>",
        "**Anonymous evidence:** this should render as plain marker `1`.",
        "</shiny-aside>",
        ". Open the `[2]` marker below: its popover header shows the "
        "**Single source** label and icon, while the marker stays compact",
        '<shiny-aside display="compact" label="Single source" '
        'icon="https://icons.duckduckgo.com/ip3/posit.co.ico">',
        "**Expected face:** `[2]`\n\nThis source has its own popover.",
        "</shiny-aside>",
        ".\n\n",
        "### Same-block clusters\n\n",
        "Two adjacent claims share one compact marker",
        '<shiny-aside display="compact" label="Revenue policy">',
        "**Source 3:** recognition occurs when custody transfers.",
        "</shiny-aside>",
        " and customer records are retained for 30 days",
        '<shiny-aside display="compact" label="Retention policy">',
        "**Source 4:** deletion runs after the retention window.",
        "</shiny-aside>",
        ". The shared marker opens a two-page popover.\n\n",
        "A three-source cluster exercises a wider face",
        '<shiny-aside display="compact" label="Operations report">',
        "**Source 5:** operations evidence.",
        "</shiny-aside>",
        ", a second source",
        '<shiny-aside display="compact" label="Finance report">',
        "**Source 6:** finance evidence.",
        "</shiny-aside>",
        ", and a third source",
        '<shiny-aside display="compact" label="Security report">',
        "**Source 7:** security evidence.",
        "</shiny-aside>",
        ". The shared marker opens a three-page popover.\n\n",
        "### Block boundaries\n\n",
        "The first paragraph has one source",
        '<shiny-aside display="compact" label="Paragraph one">',
        "**Source 8:** first paragraph evidence.",
        "</shiny-aside>",
        ".\n\n",
        "The next paragraph has another",
        '<shiny-aside display="compact" label="Paragraph two">',
        "**Source 9:** second paragraph evidence.",
        "</shiny-aside>",
        ". These remain separate markers.\n\n",
        "### Lists and wrapping\n\n",
        "- A list item can contain two numbered sources",
        '<shiny-aside display="compact" label="List source A">',
        "**Source 10:** first list-item source.",
        "</shiny-aside>",
        " and",
        '<shiny-aside display="compact" label="List source B">',
        "**Source 11:** second list-item source.",
        "</shiny-aside>",
        ". They share one marker.\n",
        "- A long sentence near the wrapping boundary keeps the superscript surface ",
        "tight while the prose flows naturally around it",
        '<shiny-aside display="compact" label="A deliberately long source label that wraps in the popover">',
        "**Source 12**\n\n"
        "- Rich Markdown remains intact.\n"
        "- The popover label may wrap.\n"
        "- The marker stays compact.",
        "</shiny-aside>",
        ".\n\n",
        "### Mixed and fallback markers\n\n",
        "An ordinary labeled aside keeps its standard pill",
        '<shiny-aside label="Control standard" url="https://example.com/controls">',
        "[Control framework](https://example.com/controls)",
        "</shiny-aside>",
        " while a numbered source in the same paragraph stays independent",
        '<shiny-aside display="compact" label="Compact mixed source">',
        "**Source 13:** numbered evidence beside an ordinary labeled aside.",
        "</shiny-aside>",
        ".\n\n",
        "Unsupported marker values keep the ordinary labeled treatment",
        '<shiny-aside display="numbered" label="Fallback source">',
        "The `numbered` display is intentionally unsupported.",
        "</shiny-aside>",
        " and do not consume a number.\n\n",
        "### Streaming boundaries\n\n",
        "This opening tag is split across stream chunks",
        "<shiny-",
        'aside display="compact" label="Split stream source">',
        "**Source 14:** the tag and body arrive incrementally.",
        "</shiny-",
        "aside>",
        ". The settled result should not flash a partial marker.\n\n",
        "Repeated labels still retain separate evidence pages",
        '<shiny-aside display="compact" label="Repeated source">',
        "**Source 15:** first repeated-label page.",
        "</shiny-aside>",
        " and",
        '<shiny-aside display="compact" label="Repeated source">',
        "**Source 16:** second repeated-label page.",
        "</shiny-aside>",
        ". The shared marker retains two separate evidence pages.\n\n",
        "### Grounded spans\n\n",
        "A **formatted grounded claim** remains linked to its source",
        '<shiny-aside display="compact" label="Grounded formatting" '
        'grounded-span="formatted grounded claim">',
        "**Source 17:** the grounded match crosses inline formatting.",
        "</shiny-aside>",
        ". Opening the marker highlights the formatted claim.\n\n",
        "The primary grounded claim has supporting evidence",
        '<shiny-aside display="compact" label="Grounded primary" '
        'grounded-span="primary grounded claim">',
        "**Source 18:** evidence for the primary claim.",
        "</shiny-aside>",
        " while the secondary grounded claim has different evidence",
        '<shiny-aside display="compact" label="Grounded secondary" '
        'grounded-span="secondary grounded claim">',
        "**Source 19:** evidence for the secondary claim.",
        "</shiny-aside>",
        ". Paging the shared marker moves the highlight between claims.",
    )

    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.04)
