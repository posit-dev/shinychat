from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_identical_resubmission_refires_on_user_submit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Regression test for the B1 dedup nonce: submitting the exact same text
    twice must fire `on_user_submit` twice. Client-side history dedup (which
    keys purely on message content) must not suppress the second identical
    submission server-side — each submit carries a fresh nonce that makes the
    two submissions distinguishable end-to-end."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    for _ in range(2):
        chat.set_user_input("same")
        chat.send_user_input(method="enter")
        page.wait_for_timeout(500)

    expect(page.locator("#submits")).to_have_text("2", timeout=10 * 1000)
