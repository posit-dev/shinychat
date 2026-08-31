"""Bookmark restore with structured tool and web-search blocks.

Verifies that structured content blocks (tool request/result, web search)
survive a bookmark round-trip: after navigating to the bookmark URL, the
tool group/card renders with the title visible, the web activity renders
with the search query visible, and the text content is present.
"""

import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_bookmark_restore_renders_tool_and_web_blocks(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    End-to-end bookmark test with structured blocks:
    1. Click button to inject tool request+result and web search burst.
    2. Send a user message (triggers auto-bookmark on response).
    3. Capture the bookmark URL.
    4. Navigate to the bookmark URL.
    5. Assert the tool group/card, web activity, and text content are restored.
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Click button to inject tool + web blocks
    page.locator("#add_blocks").click()

    # Wait for the tool loop to appear
    tool_loop = page.locator(".shiny-chat-tool-loop")
    expect(tool_loop).to_be_visible(timeout=10_000)

    # Wait for the web activity to appear
    web_activity = page.locator(".shiny-web-activity")
    expect(web_activity).to_be_visible(timeout=10_000)

    # Verify tool group and card are visible before bookmark
    group = tool_loop.locator(".shiny-chat-tool-group")
    expect(group).to_be_visible(timeout=10_000)
    group_title = group.locator(".shiny-chat-tool-group__title")
    expect(group_title).to_be_visible(timeout=10_000)
    expect(group_title.get_by_text("Looked up data")).to_be_visible()

    card = tool_loop.locator(".shiny-tool-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card.get_by_text("Restored tool result body")).to_be_visible()

    # Verify web activity shows the search query (expand the activity first)
    web_activity.locator(".shiny-web-activity__header").click()
    expect(web_activity.locator(".shiny-web-activity__timeline")).to_be_visible(
        timeout=10_000
    )
    expect(web_activity).to_contain_text("best e-bike motors")

    # Verify text content from the web search burst
    expect(
        chat.loc.get_by_text("Hub motors are ideal for flat terrain.")
    ).to_be_visible()

    # The block injection already triggered an auto-bookmark
    # (bookmark_on="response" fires on any assistant message). Capture that
    # first bookmark URL so we can tell it apart from the next one.
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    first_bookmark_url = page.url

    # Send a user message to trigger a second auto-bookmark
    chat.set_user_input("tell me more")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: tell me more", timeout=10_000)

    # Wait for the URL to change to a NEW state id, not just any state id --
    # otherwise this can race and grab the first bookmark's (stale) URL.
    page.wait_for_function(
        "url => window.location.href !== url",
        arg=first_bookmark_url,
        timeout=10_000,
    )
    bookmark_url = page.url

    # Navigate to the bookmark URL (simulates a page reload / new session)
    page.goto(bookmark_url)

    # Wait for restored chat to be visible
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Assert the tool group/card renders in the restored transcript
    restored_tool_loop = page.locator(".shiny-chat-tool-loop")
    expect(restored_tool_loop).to_be_visible(timeout=10_000)
    restored_group = restored_tool_loop.locator(".shiny-chat-tool-group")
    expect(restored_group).to_be_visible(timeout=10_000)
    restored_group_title = restored_group.locator(
        ".shiny-chat-tool-group__title"
    )
    expect(restored_group_title).to_be_visible(timeout=10_000)
    expect(restored_group_title.get_by_text("Looked up data")).to_be_visible()

    restored_card = restored_tool_loop.locator(".shiny-tool-card")
    expect(restored_card).to_be_visible(timeout=10_000)
    expect(
        restored_card.get_by_text("Restored tool result body")
    ).to_be_visible()

    # Assert the web activity renders with the search query visible
    restored_web_activity = page.locator(".shiny-web-activity")
    expect(restored_web_activity).to_be_visible(timeout=10_000)
    restored_web_activity.locator(".shiny-web-activity__header").click()
    expect(
        restored_web_activity.locator(".shiny-web-activity__timeline")
    ).to_be_visible(timeout=10_000)
    expect(restored_web_activity).to_contain_text("best e-bike motors")

    # Assert the text content is present
    expect(
        chat.loc.get_by_text("Hub motors are ideal for flat terrain.")
    ).to_be_visible()

    # Assert the user/assistant text messages are also restored
    expect(chat.loc.get_by_text("tell me more", exact=True)).to_be_visible()
    expect(chat.loc.get_by_text("You said: tell me more")).to_be_visible()
