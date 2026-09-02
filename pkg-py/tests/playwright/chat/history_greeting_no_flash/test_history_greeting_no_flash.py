from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_greeting_does_not_flash_on_restored_conversation(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Reloading a page that restores a previous conversation must not show
    the app's greeting again — it belongs to brand-new conversations only.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_greeting("Welcome", timeout=30_000)

    chat.set_user_input("hello")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello", timeout=30_000)

    # Ensure the active conversation ID has been written to localStorage before
    # reloading.  The ID lands once the history_update action reaches the client,
    # which happens after send_history_update().  The drawer shows the item at
    # that point, so opening it is a reliable sync point.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=10_000
    )
    page.keyboard.press("Escape")
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Transcript must be restored ...
    chat.expect_latest_message("echo: hello", timeout=30_000)
    # ... and the greeting must never reappear.
    expect(chat.loc_greeting).to_have_count(0, timeout=5_000)

    # Starting a new chat from a session that began by restoring a
    # conversation must still resolve the app's greeting — it was never
    # requested/resolved for *this* session, so there's nothing cached
    # client-side to fall back on.
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()
    page.locator(".shiny-chat-history-new").click()
    expect(page.locator(".shiny-chat-history-drawer")).not_to_be_visible()

    chat.expect_greeting("Welcome", timeout=30_000)
