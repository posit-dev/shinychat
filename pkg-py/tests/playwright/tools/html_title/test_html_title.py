from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_tool_title_renders_html(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Click button to add a tool result with HTML in the title
    page.click("#add_tool")

    # A single tool call rests as a condensed Tier-1 row; its title carries the
    # tool title. The <i> tag in the title should render as an actual italic
    # element, not as escaped text like "&lt;i&gt;Paris&lt;/i&gt;".
    title = chat.loc.locator(".shiny-chat-tool-group__title")
    expect(title).to_be_visible(timeout=10_000)

    italic = title.locator("i")
    expect(italic).to_be_visible()
    expect(italic).to_have_text("Paris")
