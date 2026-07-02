from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_messages_includes_just_submitted_turn(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Regression test for client-authoritative UI state: `.messages()` must
    read the client-reported snapshot, which is co-sent synchronously with the
    user's submission, so it already includes the just-submitted user turn
    inside `on_user_submit`."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    chat.set_user_input("hello")
    chat.send_user_input(method="enter")

    # On first submit the snapshot carries exactly the 1 user turn.
    expect(page.locator("#count")).to_have_text("1", timeout=10 * 1000)
