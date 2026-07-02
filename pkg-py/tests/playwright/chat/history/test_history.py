from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_history_full_flow(page: Page, local_app: ShinyAppProc) -> None:
    """
    Full conversation-history flow:
    1. Send a message in a first conversation (with bridged app state).
    2. Verify it appears in the drawer.
    3. Open a second conversation via "+ New".
    4. Send a message; verify drawer shows two conversations.
    5. Switch back to the first conversation; verify transcript AND app state are restored.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # First conversation: mutate bridged app state, then send a message.
    controller.OutputText(page, "filter_state").expect_value("filter: none")
    controller.InputActionButton(page, "set_filter").click()
    controller.OutputText(page, "filter_state").expect_value(
        re.compile(r"filter: penguins"), timeout=5_000
    )

    chat.set_user_input("first question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first question", timeout=30_000)

    # The drawer should list one conversation with the fallback title.
    open_drawer(page)
    items = page.locator(".shiny-chat-history-item")
    expect(items).to_have_count(1, timeout=10_000)
    expect(items.first).to_contain_text("first question")

    # New chat: clears transcript but does NOT touch bridged app state.
    page.locator(".shiny-chat-history-new").click()
    expect(page.locator(".shiny-chat-history-drawer")).not_to_be_visible()

    # Send a message in the second conversation.
    chat.set_user_input("second question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second question", timeout=30_000)

    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=10_000
    )

    # Switch back to the first conversation: transcript and app state must restore.
    page.locator(".shiny-chat-history-item", has_text="first question").click()
    chat.expect_latest_message("echo: first question", timeout=30_000)
    controller.OutputText(page, "filter_state").expect_value(
        re.compile(r"filter: penguins"), timeout=5_000
    )
