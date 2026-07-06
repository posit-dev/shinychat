from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_history_rename_delete_search(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Rename, search, and delete operations on a saved conversation.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message to create a saved conversation.
    chat.set_user_input("about penguins")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: about penguins", timeout=30_000)

    # --- Rename ---
    open_drawer(page)
    # Open the per-row actions menu.
    page.locator(".shiny-chat-history-itemmenu button").first.click()
    page.locator(".shiny-chat-history-menu").get_by_role(
        "button", name="Rename"
    ).click()
    # The item switches to an inline input.
    field = page.locator(".shiny-chat-history-item input")
    expect(field).to_be_visible()
    field.fill("Penguin study")
    field.press("Enter")
    expect(page.locator(".shiny-chat-history-item")).to_contain_text(
        "Penguin study", timeout=5_000
    )

    # --- Search ---
    page.locator(".shiny-chat-history-search").fill("zebra")
    expect(page.locator(".shiny-chat-history-empty")).to_be_visible()
    page.locator(".shiny-chat-history-search").fill("penguin")
    expect(page.locator(".shiny-chat-history-item")).to_have_count(1)
    page.locator(".shiny-chat-history-search").fill("")

    # --- Delete (inline confirm) ---
    page.locator(".shiny-chat-history-itemmenu button").first.click()
    page.locator(".shiny-chat-history-menu").get_by_role(
        "button", name="Delete", exact=True
    ).click()
    page.locator(".shiny-chat-history-confirm").get_by_role(
        "button", name="Confirm delete"
    ).click()
    expect(page.locator(".shiny-chat-history-empty")).to_be_visible(
        timeout=5_000
    )
