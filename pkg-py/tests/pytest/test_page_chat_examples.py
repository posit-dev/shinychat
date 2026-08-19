from __future__ import annotations

import runpy
from pathlib import Path

import pytest

EXAMPLES = (
    "artifact-controls/app.py",
    "navigation/app.py",
)
EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples" / "page-chat"


@pytest.mark.parametrize("relative_path", EXAMPLES)
def test_page_chat_example_constructs(relative_path: str) -> None:
    namespace = runpy.run_path(str(EXAMPLES_DIR / relative_path))

    app_ui = namespace["app_ui"]
    assert "app" in namespace
    assert "shiny-chat-page" in app_ui.get_html_string()
