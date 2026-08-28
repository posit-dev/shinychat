from chatlas import Turn
from chatlas.types import (
    ContentCitation,
    ContentText,
    ContentToolRequestFetch,
    ContentToolRequestSearch,
    ContentToolResponseFetch,
    ContentToolResponseSearch,
    WebSource,
)
from shinychat._chat_normalize import message_content


def test_search_request_emits_web_search_block():
    msg = message_content(
        ContentToolRequestSearch(query="ggplot2 1.0.0 release date")
    )
    # The structured envelope rides `blocks`; nothing is tagified into the
    # content string.
    assert msg.content == ""
    assert msg.blocks == [
        {
            "type": "web_search",
            "version": 1,
            "query": "ggplot2 1.0.0 release date",
        }
    ]


def test_search_response_emits_results_block_with_sources():
    msg = message_content(
        ContentToolResponseSearch(
            sources=[
                WebSource(url="https://a.com", title="Alpha"),
                WebSource(url="https://b.com"),
            ]
        )
    )
    assert msg.content == ""
    assert msg.blocks == [
        {
            "type": "web_search_results",
            "version": 1,
            "sources": [
                {"url": "https://a.com", "title": "Alpha"},
                # `title` is omitted (not None) when chatlas didn't report one.
                {"url": "https://b.com"},
            ],
        }
    ]


def test_fetch_request_renders_empty():
    msg = message_content(ContentToolRequestFetch(url="https://example.com"))
    assert msg.content == ""
    assert msg.blocks == []


def test_fetch_response_emits_web_fetch_block_with_status():
    msg = message_content(
        ContentToolResponseFetch(url="https://example.com", status="success")
    )
    assert msg.content == ""
    assert msg.blocks == [
        {
            "type": "web_fetch",
            "version": 1,
            "url": "https://example.com",
            "status": "success",
        }
    ]


def test_fetch_response_omits_status_when_none():
    # chatlas allows a missing status; the key is then absent on the wire.
    msg = message_content(ContentToolResponseFetch(url="https://example.com"))
    assert msg.content == ""
    assert msg.blocks == [
        {"type": "web_fetch", "version": 1, "url": "https://example.com"}
    ]


def test_citation_renders_aside_element_without_server_derived_label():
    # Citations render as a markdown-typed string (not a Tag) so they merge
    # into the surrounding text segment instead of forcing their own block.
    msg = message_content(
        ContentCitation(
            source=WebSource(
                url="https://cran.r-project.org/web/packages/ggplot2",
                title="ggplot2 on CRAN",
            )
        )
    )
    assert msg.content_type == "markdown"
    assert "shiny-aside" in msg.content
    assert "data-citation" in msg.content
    assert "label=" not in msg.content
    assert "https://cran.r-project.org/web/packages/ggplot2" in msg.content
    assert "ggplot2 on CRAN" in msg.content


def test_citation_without_title_uses_url_as_link_text():
    msg = message_content(
        ContentCitation(source=WebSource(url="https://example.com/page"))
    )
    assert "shiny-aside" in msg.content
    assert "https://example.com/page" in msg.content
    # Never emit the unsafe `<url>` autolink form as HTML children.
    assert "<https://" not in msg.content


def test_citation_escapes_special_characters():
    msg = message_content(
        ContentCitation(
            source=WebSource(
                url="https://x.example/?a=1&b=2", title="A & B <ok>"
            )
        )
    )
    assert "A &amp; B &lt;ok&gt;" in msg.content
    assert "a=1&amp;b=2" in msg.content


def test_citation_preserves_grounded_span_and_cited_quote():
    msg = message_content(
        ContentCitation(
            source=WebSource(url="https://example.com", title="Example"),
            grounded_span='Supported answer "text"',
            cited_quote="Source evidence <verbatim>",
        )
    )
    assert 'grounded-span="Supported answer &quot;text&quot;"' in msg.content
    assert 'cited-quote="Source evidence &lt;verbatim&gt;"' in msg.content


def test_citation_omits_missing_grounding_metadata():
    msg = message_content(
        ContentCitation(
            source=WebSource(url="https://example.com", title="Example")
        )
    )
    assert "grounded-span=" not in msg.content
    assert "cited-quote=" not in msg.content


def test_citation_preserves_grounded_span_without_cited_quote():
    msg = message_content(
        ContentCitation(
            source=WebSource(url="https://example.com", title="Example"),
            grounded_span="Supported answer",
        )
    )
    assert 'grounded-span="Supported answer"' in msg.content
    assert "cited-quote=" not in msg.content


def test_citation_preserves_cited_quote_without_grounded_span():
    msg = message_content(
        ContentCitation(
            source=WebSource(url="https://example.com", title="Example"),
            cited_quote="Source evidence",
        )
    )
    assert 'cited-quote="Source evidence"' in msg.content
    assert "grounded-span=" not in msg.content


def test_citation_without_source_renders_nothing():
    msg = message_content(ContentCitation())
    assert msg.content == ""


def test_turn_search_with_citations_but_no_results_carries_cited_sources():
    # The structured re-expression of the markup path's
    # rehypeAttachCitedSources fallback: the turn's citations ride the
    # web_search block explicitly so the client can show them while no
    # provider results attach.
    msg = message_content(
        Turn(
            [
                ContentToolRequestSearch(query="ggplot2 release date"),
                ContentText(text="According to "),
                ContentCitation(
                    source=WebSource(url="https://a.com", title="Alpha")
                ),
                ContentCitation(source=WebSource(url="https://b.com")),
                # Duplicate URL merges; a later title fills a missing one.
                ContentCitation(
                    source=WebSource(url="https://b.com", title="Beta")
                ),
            ],
            role="assistant",
        )
    )
    search_blocks = [b for b in msg.blocks if b["type"] == "web_search"]
    assert search_blocks == [
        {
            "type": "web_search",
            "version": 1,
            "query": "ggplot2 release date",
            "cited_sources": [
                {"url": "https://a.com", "title": "Alpha"},
                {"url": "https://b.com", "title": "Beta"},
            ],
        }
    ]
    # The citation asides still render into the content string as before.
    assert msg.content.count("data-citation") == 3


def test_turn_search_with_results_does_not_carry_cited_sources():
    # Provider results win: cited sources are only a fallback when the turn
    # has no search results at all.
    msg = message_content(
        Turn(
            [
                ContentToolRequestSearch(query="ggplot2 release date"),
                ContentToolResponseSearch(
                    sources=[WebSource(url="https://results.com")]
                ),
                ContentCitation(source=WebSource(url="https://a.com")),
            ],
            role="assistant",
        )
    )
    search_blocks = [b for b in msg.blocks if b["type"] == "web_search"]
    assert search_blocks == [
        {
            "type": "web_search",
            "version": 1,
            "query": "ggplot2 release date",
        }
    ]


def test_turn_citations_without_search_stay_markup_only():
    msg = message_content(
        Turn(
            [
                ContentText(text="Hello "),
                ContentCitation(source=WebSource(url="https://a.com")),
            ],
            role="assistant",
        )
    )
    assert msg.blocks == []
    assert "data-citation" in msg.content


def test_tool_display_none_suppresses(monkeypatch):
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", "none")
    search = message_content(ContentToolRequestSearch(query="x"))
    assert search.content == "" and search.blocks == []
    results = message_content(
        ContentToolResponseSearch(sources=[WebSource(url="https://a.com")])
    )
    assert results.content == "" and results.blocks == []
    fetch = message_content(
        ContentToolResponseFetch(url="https://a.com", status="success")
    )
    assert fetch.content == "" and fetch.blocks == []
    assert (
        message_content(
            ContentCitation(source=WebSource(url="https://a.com"))
        ).content
        == ""
    )
