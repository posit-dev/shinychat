from __future__ import annotations

import importlib

import pytest

EXAMPLES = (
    "shinychat.examples.page_chat.artifact_control",
    "shinychat.examples.page_chat.navigation",
)


@pytest.mark.parametrize("module_name", EXAMPLES)
def test_page_chat_example_is_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    app_module = importlib.import_module(f"{module_name}.app")

    assert module.app is not None
    assert module.app is app_module.app
    assert "shiny-chat-page" in app_module.app_ui.get_html_string()
