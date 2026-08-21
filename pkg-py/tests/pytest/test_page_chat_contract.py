from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

import pytest
from htmltools import Tag, TagList
from shiny import ui
from shiny.express._run import run_express
from shinychat import chat_nav_panel
from shinychat import page_chat as core_page_chat
from shinychat.express import page_chat as express_page_chat

_APP_IMPORTS = """
from shiny.express import ui
from shinychat import chat_nav_panel
from shinychat.express import page_chat
"""

_OWNERSHIP_ERROR = (
    r"shinychat\.express\.page_chat\(\) owns the page layout; "
    r"remove unrelated top-level UI"
)


def _run_page_chat_source(tmp_path: Path, top_level_ui: str) -> Tag | TagList:
    app = tmp_path / "app.py"
    app.write_text(
        textwrap.dedent(_APP_IMPORTS) + "\n" + textwrap.dedent(top_level_ui),
        encoding="utf-8",
    )
    return run_express(app)


def test_express_page_chat_signature_matches_core() -> None:
    assert inspect.signature(express_page_chat) == inspect.signature(
        core_page_chat
    )


def test_express_page_chat_matches_core_markup(tmp_path: Path) -> None:
    express_page = _run_page_chat_source(
        tmp_path,
        """
        page_chat(
            "Assistant",
            sidebar=False,
            toolbar=ui.input_action_button("home_action", "Home"),
            toolbar_global=ui.input_action_button("global_action", "Global"),
            pages=[
                chat_nav_panel("No toolbar"),
                chat_nav_panel(
                    "Custom",
                    toolbar=ui.input_action_button("custom_action", "Custom"),
                ),
                chat_nav_panel("None"),
            ],
        )
        """,
    )

    assert (
        express_page.get_html_string()
        == core_page_chat(
            "Assistant",
            sidebar=False,
            toolbar=ui.input_action_button("home_action", "Home"),
            toolbar_global=ui.input_action_button("global_action", "Global"),
            pages=[
                chat_nav_panel("No toolbar"),
                chat_nav_panel(
                    "Custom",
                    toolbar=ui.input_action_button("custom_action", "Custom"),
                ),
                chat_nav_panel("None"),
            ],
        ).get_html_string()
    )


def test_express_page_chat_propagates_page_options(tmp_path: Path) -> None:
    theme = tmp_path / "custom-theme.css"
    theme.write_text("body { color: rgb(1, 2, 3); }", encoding="utf-8")

    page = _run_page_chat_source(
        tmp_path,
        f"""
        page_chat(
            "Assistant",
            window_title="Chat window",
            lang="fr",
            theme={str(theme)!r},
        )
        """,
    )

    html = page.get_html_string()
    assert "<title>Chat window</title>" in html
    assert '<html lang="fr">' in html
    assert html.count("<shiny-chat-container") == 1
    assert html.count("<shiny-chat-page") == 1
    assert any(
        dependency.head is not None
        and "custom-theme.css" in str(dependency.head)
        for dependency in page.get_dependencies()
    )


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
        """
        chat_root = page_chat("Assistant")
        """,
        """
        ui.div(page_chat("Assistant"))
        """,
    ],
)
def test_express_page_chat_rejects_invalid_top_level_composition(
    tmp_path: Path,
    top_level_ui: str,
) -> None:
    with pytest.raises(RuntimeError, match=_OWNERSHIP_ERROR):
        _run_page_chat_source(tmp_path, top_level_ui)
