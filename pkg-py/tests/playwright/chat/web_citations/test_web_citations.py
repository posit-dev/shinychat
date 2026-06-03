from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_web_citations(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    message_state = controller.OutputCode(page, "message_state")

    # Wait for app to load
    message_state.expect_value("()", timeout=30 * 1000)

    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    expect(chat.loc_input_button).to_be_disabled()

    chat.set_user_input("tell me about ggplot2")
    chat.send_user_input()

    # Wait for the stream to finish — Sources footer only appears after all chunks land
    expect(page.locator(".shiny-chat-sources")).to_be_visible(timeout=30 * 1000)

    # Web search activity line
    expect(page.locator(".shiny-web-search")).to_contain_text(
        "ggplot2 1.0.0 release date"
    )

    # Web fetch activity line
    expect(page.locator(".shiny-web-fetch")).to_contain_text(
        "ggplot2.tidyverse.org/news"
    )

    # Sources footer: 3 citations, 2 unique URLs → exactly 2 list items
    expect(page.locator(".shiny-chat-sources li")).to_have_count(2)
