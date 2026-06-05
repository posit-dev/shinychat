import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _assert_all_three(page: Page) -> None:
    content = page.locator(".shiny-chat-message-content")
    # Thinking panel: the header button is always visible (even when the panel
    # is collapsed after streaming ends). Its label text confirms it rendered.
    thinking_header = content.locator("button.shinychat-thinking-header").first
    expect(thinking_header).to_be_visible(timeout=10_000)
    # The label inside the header confirms the thinking panel identity
    expect(
        thinking_header.locator("span.shinychat-thinking-label")
    ).to_be_visible(timeout=5_000)
    # markdown segment rendered as <strong>
    expect(content.locator("strong", has_text="hello")).to_be_visible(timeout=10_000)
    # html segment with its CSS dep
    card = page.locator(".custom-styled-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)


def test_mixed_thinking_survives_bookmark(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    _assert_all_three(page)

    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    bookmark_url = page.url
    page.goto(bookmark_url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    _assert_all_three(page)
