"""
Test that HTMLDependency objects are restored during bookmark restore
for messages delivered via append_message_stream().

This is the streaming counterpart to test_bookmark_html_deps. It verifies
that deps sent during streaming chunks are accumulated on the stored message
so they can be serialized into the bookmark state and re-sent on restore.
"""

import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_html_deps_restored_after_bookmark_stream(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    HTMLDependency CSS should be present after bookmark restore (streaming path).
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message to trigger the streamed styled response
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")

    # Wait for the styled card to appear
    card = page.locator(".custom-styled-card")
    expect(card).to_be_visible(timeout=10_000)

    # Verify the CSS dependency is loaded: the card should have a red border
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)

    # Wait for the bookmark URL
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    bookmark_url = page.url

    # Navigate to the bookmark URL (new session)
    page.goto(bookmark_url)

    # Wait for restored chat
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # The styled card should be present (HTML content is restored)
    card = page.locator(".custom-styled-card")
    expect(card).to_be_visible(timeout=10_000)

    # CRITICAL: Verify the CSS dependency was re-loaded.
    # Without accumulating deps during streaming, the stored message has
    # html_deps=None, so nothing is saved in the bookmark state.
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
