from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


@pytest.mark.parametrize("width", [1000, 390], ids=["desktop", "mobile"])
def test_incompatible_context_can_be_viewed_and_navigated_but_not_continued(
    page: Page,
    local_app: ShinyAppProc,
    width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc_input).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="Conversation history").click()
    page.get_by_role("button", name="Saved incompatible context").click()

    chat.expect_latest_message("original reply", timeout=30_000)
    bar = chat.loc.locator(".shiny-chat-readonly")
    status = bar.get_by_role("status")
    expect(status).to_contain_text(
        "This conversation can be viewed but not continued. Its saved model context couldn't be loaded."
    )
    expect(chat.loc_input).to_have_count(0)
    expect(chat.loc_input_button).to_have_count(0)
    expect(chat.loc.locator(".shiny-chat-edit-btn")).to_have_count(0)
    expect(chat.loc.get_by_role("button", name="Retry message")).to_have_count(
        0
    )
    expect(
        chat.loc.get_by_role("button", name="Regenerate message")
    ).to_have_count(0)
    expect(page.locator(".shiny-notification")).to_have_count(0)

    original = chat.loc.locator(".shiny-chat-user-message").first
    original.hover()
    original.get_by_role("button", name="Next version").click()
    chat.expect_latest_message("alternative reply", timeout=30_000)
    expect(status).to_be_visible()
    expect(chat.loc.locator(".shiny-chat-edit-btn")).to_have_count(0)
    alternative = chat.loc.locator(".shiny-chat-user-message").first
    alternative.hover()
    alternative.get_by_role("button", name="Previous version").click()
    chat.expect_latest_message("original reply", timeout=30_000)
    expect(page.locator(".shiny-notification")).to_have_count(0)

    # Reload must preserve the selected path and classify it read-only again.
    page.reload()
    chat.expect_latest_message("original reply", timeout=30_000)
    expect(status).to_be_visible()
    assert status.evaluate("el => el.scrollWidth <= el.clientWidth")

    new_chat = bar.get_by_role("button", name="New chat")
    new_chat.focus()
    new_chat.press("Enter")
    expect(status).to_have_count(0)
    expect(chat.loc_input).to_be_visible(timeout=30_000)
    expect(chat.loc_input).to_be_focused()
    chat.set_user_input("fresh question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: fresh question", timeout=30_000)
