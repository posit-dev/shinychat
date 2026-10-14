"""Bookmark restore with structured tool and web-search blocks."""

import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_bookmark_restore_renders_tool_and_web_blocks(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    page.locator("#add_blocks").click()

    tool_loop = page.locator(".shiny-chat-tool-loop")
    expect(tool_loop).to_be_visible(timeout=10_000)

    web_activity = page.locator(".shiny-web-activity")
    expect(web_activity).to_be_visible(timeout=10_000)

    group = tool_loop.locator(".shiny-chat-tool-group")
    expect(group).to_be_visible(timeout=10_000)
    group_title = group.locator(".shiny-chat-tool-group__title")
    expect(group_title).to_be_visible(timeout=10_000)
    expect(group_title.get_by_text("Looked up data")).to_be_visible()

    card = tool_loop.locator(".shiny-tool-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card.get_by_text("Restored tool result body")).to_be_visible()

    web_activity.locator(".shiny-web-activity__header").click()
    expect(web_activity.locator(".shiny-web-activity__timeline")).to_be_visible(
        timeout=10_000
    )
    expect(web_activity).to_contain_text("best e-bike motors")

    expect(
        chat.loc.get_by_text("Hub motors are ideal for flat terrain.")
    ).to_be_visible()

    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    first_bookmark_url = page.url

    chat.set_user_input("tell me more")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: tell me more", timeout=10_000)

    page.wait_for_function(
        "url => window.location.href !== url",
        arg=first_bookmark_url,
        timeout=10_000,
    )
    bookmark_url = page.url

    page.goto(bookmark_url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

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

    restored_web_activity = page.locator(".shiny-web-activity")
    expect(restored_web_activity).to_be_visible(timeout=10_000)
    restored_web_activity.locator(".shiny-web-activity__header").click()
    expect(
        restored_web_activity.locator(".shiny-web-activity__timeline")
    ).to_be_visible(timeout=10_000)
    expect(restored_web_activity).to_contain_text("best e-bike motors")

    expect(
        chat.loc.get_by_text("Hub motors are ideal for flat terrain.")
    ).to_be_visible()

    expect(chat.loc.get_by_text("tell me more", exact=True)).to_be_visible()
    expect(chat.loc.get_by_text("You said: tell me more")).to_be_visible()
