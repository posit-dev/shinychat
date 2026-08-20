from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_navigation_example_saves_conversations(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    shell = page.locator("shiny-chat-page")
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    expect(shell).to_be_visible()
    expect(chat.loc).to_be_visible()

    if sidebar.is_hidden():
        shell.locator(".shiny-chat-page-sidebar-toggle").click()
    expect(sidebar).to_be_visible()

    chat.set_user_input("Remember this exchange")
    chat.send_user_input()
    chat.expect_latest_message(
        "The assistant replied to your message: Remember this exchange"
    )
    expect(
        sidebar.locator(
            ".shiny-chat-page-sidebar-panel:not([hidden]) "
            ".shiny-chat-history-item"
        )
    ).to_have_count(1)
