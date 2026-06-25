from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_history_restore_callbacks_on_reload(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    on_restore callbacks must fire on page-load restore, not only on in-session
    conversation switches.

    Flow:
    1. Set filter to "penguins", send a message → on_save captures the filter.
    2. Reload the page.
    3. Transcript is restored AND filter_state shows "penguins" (on_restore fired).
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    controller.OutputText(page, "filter_state").expect_value("filter: none")
    controller.InputActionButton(page, "set_filter").click()
    controller.OutputText(page, "filter_state").expect_value(
        re.compile(r"filter: penguins"), timeout=5_000
    )

    chat.set_user_input("reload test")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: reload test", timeout=30_000)

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

    # Transcript must be restored.
    chat.expect_latest_message("echo: reload test", timeout=30_000)

    # App state must be restored via on_restore callback.
    controller.OutputText(page, "filter_state").expect_value(
        re.compile(r"filter: penguins"), timeout=5_000
    )
