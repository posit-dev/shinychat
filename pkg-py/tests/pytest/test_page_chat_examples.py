from __future__ import annotations

import importlib
import inspect

import pytest

EXAMPLES = (
    "shinychat.examples.page_chat.drawer_control",
    "shinychat.examples.page_chat.navigation",
)


@pytest.mark.parametrize("module_name", EXAMPLES)
def test_page_chat_example_is_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    app_module = importlib.import_module(f"{module_name}.app")

    assert module.app is not None
    assert module.app is app_module.app
    html = app_module.app_ui.get_html_string()
    assert "shiny-chat-page" in html
    if module_name.endswith(".navigation"):
        assert '<shiny-chat-history for="chat">' in html
        assert 'id="show_settings"' in html
        assert 'class="bi bi-gear-fill"' in html
        assert 'class="bi bi-info-circle-fill"' in html
        assert 'data-page-target="Notebook"' in html
        assert 'data-page-target="Settings"' not in html
        assert 'id="model"' in html
        assert 'id="reasoning"' in html
        assert "AI can be wrong. Check your work." in html
        assert "HistoryOptions" in inspect.getsource(app_module)
        assert "ui.show_offcanvas" in inspect.getsource(app_module)
