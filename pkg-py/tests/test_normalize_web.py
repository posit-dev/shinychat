from chatlas.types import (
    ContentCitation,
    ContentToolRequestFetch,
    ContentToolRequestSearch,
    ContentToolResponseFetch,
    ContentToolResponseSearch,
    WebSource,
)
from htmltools import TagList
from shinychat._chat_normalize import message_content


def _html(content) -> str:
    return TagList(message_content(content).content).render()["html"]


def test_search_request_renders_web_search_element():
    html = _html(ContentToolRequestSearch(query="ggplot2 1.0.0 release date"))
    assert "shiny-web-search" in html
    assert "ggplot2 1.0.0 release date" in html
    assert "data-shinychat-react" in html


def test_search_response_renders_results_element_with_sources():
    html = _html(
        ContentToolResponseSearch(
            sources=[
                WebSource(url="https://a.com", title="Alpha"),
                WebSource(url="https://b.com"),
            ]
        )
    )
    assert "shiny-web-search-results" in html
    assert "data-shinychat-react" in html
    # sources are JSON-encoded onto the element (HTML-escaped in the attribute)
    assert "https://a.com" in html
    assert "Alpha" in html
    assert "https://b.com" in html


def test_fetch_request_renders_empty():
    html = _html(ContentToolRequestFetch(url="https://example.com"))
    assert "shiny-web-fetch" not in html


def test_fetch_response_renders_web_fetch_element_with_status():
    html = _html(
        ContentToolResponseFetch(url="https://example.com", status="success")
    )
    assert "shiny-web-fetch" in html
    assert "https://example.com" in html
    assert "success" in html


def test_citation_renders_aside_element_with_auto_derived_label():
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
    assert 'label="cran.r-project.org"' in msg.content
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


def test_tool_display_none_suppresses(monkeypatch):
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", "none")
    assert _html(ContentToolRequestSearch(query="x")).strip() == ""
    assert (
        _html(
            ContentToolResponseSearch(sources=[WebSource(url="https://a.com")])
        ).strip()
        == ""
    )
    assert (
        _html(
            ContentToolResponseFetch(url="https://a.com", status="success")
        ).strip()
        == ""
    )
    assert (
        message_content(
            ContentCitation(source=WebSource(url="https://a.com"))
        ).content
        == ""
    )
