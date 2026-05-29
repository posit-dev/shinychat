from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_no_error_without_bookmark_store(
    page: Page, local_app: ShinyAppProc
) -> None:
    """enable_bookmarking() should not raise when no bookmark store is configured."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # App loaded without crashing — the main assertion
    # Verify chat works normally
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: hello", timeout=30_000)
