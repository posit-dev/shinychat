"""Non-streaming tool flow: structured blocks through append_message.

Verifies that ``ContentToolRequest`` and ``ContentToolResult`` injected via
the non-streaming ``chat.append_message(...)`` action produce the same tool
group row and card as the streaming path.  The structured blocks must flow
through the ``message`` action so the title and result value are visible.
"""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_non_streaming_tool_renders_group_and_card(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A non-streaming tool request+result pair renders the tool group row
    and the drill-down card with the title and result value visible."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    page.locator("#add_tool").click()

    # A tool loop should appear.
    loop = page.locator(".shiny-chat-tool-loop")
    expect(loop).to_be_visible(timeout=10_000)

    # The tool group row should be visible with the result title.
    group = loop.locator(".shiny-chat-tool-group")
    expect(group).to_be_visible(timeout=10_000)
    # The group row title (the condensed activity row) shows the title.
    group_title = group.locator(".shiny-chat-tool-group__title")
    expect(group_title).to_be_visible(timeout=10_000)
    expect(group_title.get_by_text("Looked up data")).to_be_visible()

    # The card should be visible (display.open=True means expanded by
    # default) with the result value.
    card = loop.locator(".shiny-tool-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card.get_by_text("Non-streaming result body")).to_be_visible()
