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
from shinychat._chat_normalize import message_content, message_content_chunk


def test_search_request_emits_web_search_block():
    msg = message_content(
        ContentToolRequestSearch(query="ggplot2 1.0.0 release date")
    )
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
    msg = message_content(ContentToolResponseFetch(url="https://example.com"))
    assert msg.content == ""
    assert msg.blocks == [
        {"type": "web_fetch", "version": 1, "url": "https://example.com"}
    ]


def test_citation_renders_aside_element_without_server_derived_label():
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


def test_search_request_with_provider_id_emits_it():
    msg = message_content(
        ContentToolRequestSearch(
            query="ggplot2 release date",
            extra={"type": "server_tool_use", "id": "srvtoolu_123"},
        )
    )
    assert msg.blocks == [
        {
            "type": "web_search",
            "version": 1,
            "query": "ggplot2 release date",
            "id": "srvtoolu_123",
        }
    ]


def test_search_response_with_provider_id_emits_search_id():
    msg = message_content(
        ContentToolResponseSearch(
            sources=[WebSource(url="https://a.com")],
            extra={
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_123",
            },
        )
    )
    assert msg.blocks == [
        {
            "type": "web_search_results",
            "version": 1,
            "sources": [{"url": "https://a.com"}],
            "search_id": "srvtoolu_123",
        }
    ]


def test_citation_emits_citations_block_alongside_aside():
    msg = message_content(
        ContentCitation(
            source=WebSource(url="https://a.com", title="Alpha"),
        )
    )
    assert msg.blocks == [
        {
            "type": "web_search_citations",
            "version": 1,
            "sources": [{"url": "https://a.com", "title": "Alpha"}],
        }
    ]
    assert "data-citation" in msg.content


def test_citation_chunk_matches_complete_message():
    citation = ContentCitation(
        source=WebSource(url="https://a.com", title="Alpha"),
        grounded_span="answer text",
    )
    chunk = message_content_chunk(citation)
    complete = message_content(citation)
    assert chunk.blocks == complete.blocks
    assert chunk.content == complete.content


def test_turn_search_with_citations_emits_citation_blocks_in_order():
    msg = message_content(
        Turn(
            [
                ContentToolRequestSearch(query="ggplot2 release date"),
                ContentText(text="According to "),
                ContentCitation(
                    source=WebSource(url="https://a.com", title="Alpha")
                ),
                ContentCitation(source=WebSource(url="https://b.com")),
                ContentCitation(
                    source=WebSource(url="https://b.com", title="Beta")
                ),
            ],
            role="assistant",
        )
    )
    assert msg.blocks == [
        {
            "type": "web_search",
            "version": 1,
            "query": "ggplot2 release date",
        },
        {
            "type": "web_search_citations",
            "version": 1,
            "sources": [{"url": "https://a.com", "title": "Alpha"}],
        },
        {
            "type": "web_search_citations",
            "version": 1,
            "sources": [{"url": "https://b.com"}],
        },
        {
            "type": "web_search_citations",
            "version": 1,
            "sources": [{"url": "https://b.com", "title": "Beta"}],
        },
    ]
    assert msg.content.count("data-citation") == 3


def test_turn_search_with_results_still_emits_citation_blocks():
    # The client hides cited sources once provider results attach; the
    # server emits them unconditionally so stream and replay agree.
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
    assert [b["type"] for b in msg.blocks] == [
        "web_search",
        "web_search_results",
        "web_search_citations",
    ]


def test_citations_before_any_search_request_still_emit_blocks():
    # Pairing is the client's job; a citations block with no preceding
    # search is dropped there, never filtered here (the chunk path
    # couldn't know).
    msg = message_content(
        Turn(
            [
                ContentText(text="Intro "),
                ContentCitation(source=WebSource(url="https://orphan.com")),
                ContentToolRequestSearch(query="query"),
                ContentText(text="Answer"),
            ],
            role="assistant",
        )
    )
    assert [b["type"] for b in msg.blocks] == [
        "web_search_citations",
        "web_search",
    ]
    assert msg.content.count("data-citation") == 1


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


def test_overlapping_pending_searches_emit_blocks_without_pairing():
    # Results↔search pairing (by search_id, else earliest pending) is
    # single-sourced in the client; the server just emits blocks in order.
    msg = message_content(
        Turn(
            [
                ContentToolRequestSearch(query="query A"),
                ContentToolRequestSearch(query="query B"),
                ContentToolResponseSearch(
                    sources=[WebSource(url="https://results-a.com")]
                ),
                ContentText(text="Answer "),
                ContentCitation(
                    source=WebSource(url="https://b.com", title="Beta")
                ),
            ],
            role="assistant",
        )
    )
    assert [b["type"] for b in msg.blocks] == [
        "web_search",
        "web_search",
        "web_search_results",
        "web_search_citations",
    ]
