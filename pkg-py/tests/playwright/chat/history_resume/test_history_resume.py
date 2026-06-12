from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_history_resume_last(page: Page, local_app: ShinyAppProc) -> None:
    """
    resume="last" reopens the most recent conversation on session start.

    Flow:
    1. Load page → send "hello resume" → expect "echo: hello resume".
    2. Reload the page (new Shiny session, same store dir).
    3. After reload the transcript contains "echo: hello resume" WITHOUT
       sending anything new — the conversation was auto-reopened.
    4. The drawer shows exactly 1 conversation with the active highlight.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message to create the first (and only) saved conversation.
    chat.set_user_input("hello resume")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello resume", timeout=30_000)

    # Reload — a new Shiny session starts against the same store dir.
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)

    # The conversation must be restored without any user input.
    chat.expect_latest_message("echo: hello resume", timeout=30_000)

    # Open the drawer: exactly 1 conversation, and it carries the active highlight.
    open_drawer(page)
    items = page.locator(".shiny-chat-history-item")
    expect(items).to_have_count(1, timeout=10_000)
    expect(items.first).to_have_class(
        "shiny-chat-history-item active", timeout=5_000
    )
