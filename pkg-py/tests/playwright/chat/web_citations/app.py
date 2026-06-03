from chatlas.types import (
    Citation,
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
    # All web activity arrives as one consecutive burst (search, its results, a
    # fetch) before the prose answer, so it groups into a single timeline block.
    yield ContentToolRequestSearch(query="ggplot2 1.0.0 release date")
    yield ContentToolResponseSearch(
        sources=[
            Source(url="https://cran.r-project.org/web/packages/ggplot2", title="ggplot2 on CRAN", domain="cran.r-project.org"),
            Source(url="https://ggplot2.tidyverse.org/news", title="ggplot2 changelog", domain="ggplot2.tidyverse.org"),
        ]
    )
    yield ContentToolResponseFetch(url="https://ggplot2.tidyverse.org/news", status="success")
    yield ContentText(text="ggplot2 1.0.0 was released on 2015-03-09. It is a popular R package.")
    yield ContentCitation(citation=Citation(url="https://cran.r-project.org", title="CRAN", cited_text="released on 2015-03-09"))
    yield ContentCitation(citation=Citation(url="https://ggplot2.tidyverse.org", title="ggplot2", cited_text="popular R package"))
    # duplicate URL to prove dedupe
    yield ContentCitation(citation=Citation(url="https://cran.r-project.org", title="CRAN"))


@chat.on_user_submit
async def _():
    await chat.append_message_stream(fake_stream())


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
