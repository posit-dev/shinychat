from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from htmltools import Tag, TagList
from shiny.express._run import run_express

_ADAPTER_SOURCE = """
from htmltools import Tag, tags
from shiny.express import ui


def _shared_core_page(
    chat_root,
    *,
    title,
    window_title,
    lang,
    theme,
):
    return tags.div(
        chat_root,
        id="shared-core-page",
        **{
            "data-page-title": title,
            "data-window-title": window_title,
            "data-lang": lang,
            "data-theme": "none" if theme is None else "provided",
        },
    )


def _page_fn(*items, **page_options):
    chat_roots = [
        item
        for item in items
        if isinstance(item, Tag)
        and item.attrs.get("data-shinychat-page-root") == "true"
    ]
    if len(chat_roots) != 1 or len(items) != 1:
        raise RuntimeError(
            "shinychat.express.page_chat() owns the page layout; "
            "remove unrelated top-level UI."
        )

    return _shared_core_page(chat_roots[0], **page_options)


def page_chat(
    title,
    *,
    window_title=None,
    lang=None,
    theme=None,
):
    ui.page_opts(
        title=title,
        window_title=window_title,
        lang=lang,
        theme=theme,
        page_fn=_page_fn,
    )
    return tags.div(
        "chat root",
        **{"data-shinychat-page-root": "true"},
    )
"""


def _run_page_chat_source(tmp_path: Path, top_level_ui: str) -> Tag | TagList:
    app = tmp_path / "app.py"
    app.write_text(
        textwrap.dedent(_ADAPTER_SOURCE) + "\n" + textwrap.dedent(top_level_ui),
        encoding="utf-8",
    )
    return run_express(app)


def test_express_page_fn_delegates_one_chat_root_and_page_options(
    tmp_path: Path,
) -> None:
    page = _run_page_chat_source(
        tmp_path,
        """
        page_chat(
            "Assistant",
            window_title="Chat window",
            lang="fr",
            theme="custom-theme.css",
        )
        """,
    )

    html = page.get_html_string()
    assert 'id="shared-core-page"' in html
    assert 'data-page-title="Assistant"' in html
    assert 'data-window-title="Chat window"' in html
    assert 'data-lang="fr"' in html
    assert 'data-theme="provided"' in html
    assert html.count('data-shinychat-page-root="true"') == 1


@pytest.mark.parametrize(
    "top_level_ui",
    [
        """
        page_chat("Assistant")
        ui.p("Unrelated top-level UI")
        """,
        """
        page_chat("Assistant")
        page_chat("Another chat")
        """,
    ],
)
def test_express_page_fn_rejects_unrelated_or_multiple_top_level_ui(
    tmp_path: Path,
    top_level_ui: str,
) -> None:
    with pytest.raises(
        RuntimeError,
        match=(
            r"shinychat\.express\.page_chat\(\) owns the page layout; "
            r"remove unrelated top-level UI"
        ),
    ):
        _run_page_chat_source(tmp_path, top_level_ui)
