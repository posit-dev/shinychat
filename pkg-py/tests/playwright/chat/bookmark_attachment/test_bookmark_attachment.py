import re
from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def test_bookmark_restore_renders_user_attachment(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    A user message with an image attachment must still render its image after a
    bookmark round trip. On restore the server re-sends the message as a
    complete-message ``message`` action whose segments include an attachment
    segment, so this exercises the client mapping in ``messagePayloadToData``.
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Attach the fixture image and send it.
    page.set_input_files("input[type=file]", str(HERE / "one_px.png"))
    expect(page.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)
    chat.set_user_input("look at this")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Got 1 attachment(s).", timeout=10_000)

    # Sanity: the just-sent user bubble rendered the image (the INPUT_SENT path).
    expect(page.locator(".shiny-chat-message-image")).to_have_count(1)

    # Wait for the bookmark URL, then navigate to it (simulates a reload).
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    bookmark_url = page.url
    page.goto(bookmark_url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # The restored user message must re-render its attached image (the
    # message-action path, previously dropped).
    expect(page.locator(".shiny-chat-message-image")).to_have_count(
        1, timeout=10_000
    )
