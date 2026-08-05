from __future__ import annotations

from htmltools import div
from shinychat._markdown_stream import output_markdown_stream


def test_non_string_content_is_always_labelled_html_regardless_of_content_type():
    tag = output_markdown_stream("stream", content=div("Hello"))
    assert tag.attrs["content-type"] == "html"

    # Even if the caller explicitly (and wrongly) asks for markdown.
    tag = output_markdown_stream(
        "stream", content=div("Hello"), content_type="markdown"
    )
    assert tag.attrs["content-type"] == "html"

    # A plain string keeps whatever the caller asked for.
    tag = output_markdown_stream("stream", content="Hello", content_type="text")
    assert tag.attrs["content-type"] == "text"
