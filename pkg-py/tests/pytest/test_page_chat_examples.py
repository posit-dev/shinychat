from __future__ import annotations

import importlib

import pytest

EXAMPLES = (
    "shinychat.examples.artifact_controls",
    "shinychat.examples.navigation",
)


@pytest.mark.parametrize("module_name", EXAMPLES)
def test_page_chat_example_is_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)

    assert module.app is not None
    assert "shiny-chat-page" in module.app_ui.get_html_string()
