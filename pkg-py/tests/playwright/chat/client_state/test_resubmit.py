from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_identical_resubmission_refires_on_user_submit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Identical submissions carry distinct event-priority sequence values."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    for _ in range(2):
        chat.set_user_input("same")
        chat.send_user_input(method="enter")
        chat.expect_latest_message("echo: same", timeout=10_000)

    expect(page.locator("#submits")).to_have_text("2", timeout=10 * 1000)
    expect(page.locator("pre#messages.shiny-text-output")).to_contain_text(
        '"content": "same"', timeout=10_000
    )
