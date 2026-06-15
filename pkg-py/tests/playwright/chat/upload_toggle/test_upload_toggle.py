from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_enable_upload_toggles_attach_ui(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    on = ChatController(page, "chat_on")
    off = ChatController(page, "chat_off")
    expect(on.loc).to_be_visible(timeout=30_000)
    expect(off.loc).to_be_visible(timeout=30_000)

    # Enabled chat shows the attach button; disabled chat does not.
    expect(
        page.locator("#chat_on button[aria-label='Attach file']")
    ).to_have_count(1)
    expect(
        page.locator("#chat_off button[aria-label='Attach file']")
    ).to_have_count(0)

    # Enabled chat exposes a file input; disabled chat does not.
    expect(page.locator("#chat_on input[type=file]")).to_have_count(1)
    expect(page.locator("#chat_off input[type=file]")).to_have_count(0)
