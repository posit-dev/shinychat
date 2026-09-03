from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_browser_no_target_suppresses_unresolved_constructor_and_startup_append(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    messages = page.locator(".shiny-chat-message, .shiny-chat-user-message")
    expect(messages).to_have_count(0, timeout=30_000)
    controller.OutputText(page, "startup_exchange").expect_value(
        re.compile(r'"active_id": null, "parent_id": null, "messages": \[\]'),
        timeout=30_000,
    )
    chat = ChatController(page, "chat")
    chat.set_user_input("extended task response")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: extended task response", timeout=30_000)


@pytest.mark.parametrize("local_app", ["app_url.py"], indirect=True)
def test_url_target_restores_display_without_unresolved_startup_append(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(f"{local_app.url}?shinychat_conversation_id=startup-target")

    messages = page.locator(".shiny-chat-message, .shiny-chat-user-message")
    expect(messages).to_have_count(1, timeout=30_000)
    expect(messages.nth(0)).to_contain_text("restored input")
    expect(page.get_by_text("constructor message", exact=True)).to_have_count(0)
    expect(page.get_by_text("startup append", exact=True)).to_have_count(0)
    controller.OutputText(page, "startup_exchange").expect_value(
        re.compile(r'"active_id": null, "parent_id": null, "messages": \[\]'),
        timeout=30_000,
    )
