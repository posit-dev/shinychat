"""Non-streaming tool flow: structured blocks through append_message."""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_non_streaming_tool_renders_group_and_card(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    page.locator("#add_tool").click()

    loop = page.locator(".shiny-chat-tool-loop")
    expect(loop).to_be_visible(timeout=10_000)

    group = loop.locator(".shiny-chat-tool-group")
    expect(group).to_be_visible(timeout=10_000)
    group_title = group.locator(".shiny-chat-tool-group__title")
    expect(group_title).to_be_visible(timeout=10_000)
    expect(group_title.get_by_text("Looked up data")).to_be_visible()

    card = loop.locator(".shiny-tool-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card.get_by_text("Non-streaming result body")).to_be_visible()
