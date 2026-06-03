from chatlas.types import (
    Citation,
    ContentCitation,
    ContentToolRequestFetch,
    ContentToolRequestSearch,
    ContentToolResponseFetch,
    ContentToolResponseSearch,
    Source,
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
                Source(url="https://a.com", title="Alpha", domain="a.com"),
                Source(url="https://b.com"),
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
    html = _html(ContentToolResponseFetch(url="https://example.com", status="success"))
    assert "shiny-web-fetch" in html
    assert "https://example.com" in html
    assert "success" in html


def test_citation_renders_citation_element():
    html = _html(
        ContentCitation(
            citation=Citation(url="https://a.com", title="A", cited_text="some text")
        )
    )
    assert "shiny-citation" in html
    assert "https://a.com" in html
    assert "A" in html
    assert "some text" in html


def test_tool_display_none_suppresses(monkeypatch):
    monkeypatch.setenv("SHINYCHAT_TOOL_DISPLAY", "none")
    assert _html(ContentToolRequestSearch(query="x")).strip() == ""
    assert (
        _html(ContentToolResponseSearch(sources=[Source(url="https://a.com")])).strip()
        == ""
    )
    assert (
        _html(ContentToolResponseFetch(url="https://a.com", status="success")).strip()
        == ""
    )
    assert _html(ContentCitation(citation=Citation(url="https://a.com"))).strip() == ""
