from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def test_image_input_forwards_to_handler(
    page: Page, chat: ChatController
) -> None:
    # `chat` fixture already navigated to the app and confirmed visibility.

    # Attach the fixture image via the hidden file input.
    page.set_input_files("input[type=file]", str(HERE / "one_px.png"))

    # A thumbnail should appear in the input area.
    expect(page.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)

    chat.set_user_input("what is this?")
    chat.send_user_input(method="enter")

    # Server handler received exactly one image.
    chat.expect_latest_message("Got 1 image(s).")
    controller.OutputCode(page, "received").expect_value("n_images=1")

    # The user message bubble rendered the attached image.
    expect(page.locator(".shiny-chat-message-image")).to_have_count(1)
