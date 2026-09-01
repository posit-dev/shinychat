from __future__ import annotations

import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def test_v2_restore_replays_turns_and_continues_provider_context(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("first question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(_message_count(page)).to_have_count(2, timeout=10_000)

    # The history drawer is the production synchronization point for the
    # browser's active conversation ID before the new session restores it.
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=10_000
    )
    page.keyboard.press("Escape")

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(_message_count(page)).to_have_count(2, timeout=10_000)

    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"first question"'), timeout=10_000
    )
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"echo: first question"'), timeout=10_000
    )
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"turn_count": 2'), timeout=10_000
    )
    controller.OutputText(page, "recorder").expect_value(
        re.compile(r'"node_count": 2'), timeout=10_000
    )

    chat.set_user_input("second question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second question", timeout=30_000)
    expect(_message_count(page)).to_have_count(4, timeout=10_000)
    controller.OutputText(page, "provider_context").expect_value(
        "[first question] | [echo: first question] | second question",
        timeout=10_000,
    )
    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"turn_count": 4'), timeout=10_000
    )
    controller.OutputText(page, "recorder").expect_value(
        re.compile(r'"node_count": 3'), timeout=10_000
    )
