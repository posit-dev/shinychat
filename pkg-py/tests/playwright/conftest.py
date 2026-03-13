import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


@pytest.fixture
def chat(page: Page, local_app: ShinyAppProc) -> ChatController:
    """Navigate to the app and return a visible ChatController."""
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    return ctrl
