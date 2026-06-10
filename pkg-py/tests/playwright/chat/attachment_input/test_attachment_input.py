from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


@pytest.fixture
def chat(page: Page, local_app: ShinyAppProc) -> ChatController:
    """Navigate to the app and return a visible ChatController."""
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    return ctrl


def test_pdf_attachment_forwards_to_handler(
    page: Page, chat: ChatController
) -> None:
    # Attach the fixture PDF via the hidden file input.
    page.set_input_files("input[type=file]", str(HERE / "sample.pdf"))

    # A document chip (not an image thumbnail) should appear, showing the name.
    chip = page.locator(".shiny-chat-input-attachment-chip")
    expect(chip).to_have_count(1)
    expect(chip).to_contain_text("sample.pdf")

    chat.set_user_input("summarize this")
    chat.send_user_input(method="enter")

    # Server handler received exactly one PDF attachment with its filename.
    chat.expect_latest_message("Got 1 attachment(s).")
    controller.OutputCode(page, "received").expect_value(
        "n=1 type=application/pdf name=sample.pdf"
    )

    # The sent message bubble rendered the PDF as a chip, not an <img>.
    expect(page.locator(".shiny-chat-message-attachment-chip")).to_have_count(1)
    expect(page.locator(".shiny-chat-message-image")).to_have_count(0)
