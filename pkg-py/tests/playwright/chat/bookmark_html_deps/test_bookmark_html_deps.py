"""
Test that HTMLDependency objects are restored during bookmark restore.

This test verifies that when a chat message includes HTML content with
HTMLDependency objects (CSS/JS), those dependencies are re-sent to the
client when the message is restored from a bookmark.
"""

import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_html_deps_restored_after_bookmark(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    HTMLDependency CSS should be present after bookmark restore.

    Steps:
    1. Send a message that triggers HTML with an HTMLDependency (custom CSS)
    2. Verify the CSS is loaded (red border visible)
    3. Bookmark
    4. Navigate to the bookmark URL
    5. Verify the CSS is still loaded (red border visible)
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message to trigger the styled response
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")

    # Wait for the styled card to appear
    card = page.locator(".custom-styled-card")
    expect(card).to_be_visible(timeout=10_000)

    # Verify the CSS dependency is loaded: the card should have a red border
    border_color = card.evaluate(
        "el => getComputedStyle(el).borderColor"
    )
    assert "rgb(255, 0, 0)" in border_color, (
        f"Expected red border on first render, got: {border_color}"
    )

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

    # CRITICAL: Verify the CSS dependency was re-loaded
    # Without the fix, the CSS is NOT loaded on restore, so the border will be absent
    border_color = card.evaluate(
        "el => getComputedStyle(el).borderColor"
    )
    assert "rgb(255, 0, 0)" in border_color, (
        f"Expected red border after bookmark restore, got: {border_color}. "
        "HTMLDependency was not re-sent during bookmark restore."
    )
