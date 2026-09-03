from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_greeting_clears_when_switching_to_old_conversation(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Starting a fresh conversation shows the greeting; switching to a
    previously-saved conversation via the history drawer must hide it.

    Selectors and flow mirror
    `pkg-py/tests/playwright/chat/history/test_history.py::test_history_full_flow`.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_greeting("Welcome", timeout=30_000)

    chat.set_user_input("first conversation")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first conversation", timeout=30_000)

    open_drawer(page)
    items = page.locator(".shiny-chat-history-item")
    expect(items).to_have_count(1, timeout=10_000)

    # New chat: clears the transcript (and, per this fix, the greeting
    # should reappear here as a normal fresh-conversation greeting).
    page.locator(".shiny-chat-history-new").click()
    expect(page.locator(".shiny-chat-history-drawer")).not_to_be_visible()

    chat.set_user_input("second conversation")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second conversation", timeout=30_000)

    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=10_000
    )

    # Switch back to the first conversation via the drawer.
    page.locator(
        ".shiny-chat-history-item", has_text="first conversation"
    ).click()

    chat.expect_latest_message("echo: first conversation", timeout=30_000)
    expect(chat.loc_greeting).to_have_count(0, timeout=5_000)
