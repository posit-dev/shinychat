from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_tool_title_renders_html(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Click button to add a tool result with HTML in the title
    page.click("#add_tool")

    # The <i> tag in the title should render as an actual italic element,
    # not as escaped text like "&lt;i&gt;Paris&lt;/i&gt;"
    title_name = chat.loc.locator(".tool-title-name")
    expect(title_name).to_be_visible(timeout=10_000)

    italic = title_name.locator("i")
    expect(italic).to_be_visible()
    expect(italic).to_have_text("Paris")
