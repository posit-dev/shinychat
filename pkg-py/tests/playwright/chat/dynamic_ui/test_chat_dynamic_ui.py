from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_validate_chat_basic(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    chat = ChatController(page, "chat")

    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    chat.expect_latest_message("A starting message", timeout=30 * 1000)
