from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def start_transition(page: Page, operation: str) -> None:
    open_drawer(page)
    if operation == "new":
        page.locator(".shiny-chat-history-new").click()
        return

    page.locator(".shiny-chat-history-itemmenu button").first.click()
    page.locator(".shiny-chat-history-menu").get_by_role(
        "button", name="Delete", exact=True
    ).click()
    page.locator(".shiny-chat-history-confirm").get_by_role(
        "button", name="Confirm delete"
    ).click()


@pytest.mark.parametrize("operation", ["new", "delete"])
def test_active_history_transition_preserves_draft_until_explicit_resubmit(
    page: Page, local_app: ShinyAppProc, operation: str
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("seed")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: seed", timeout=30_000)
    controller.OutputText(page, "submissions").expect_value("1")

    start_transition(page, operation)
    chat.set_user_input("draft")
    page.set_input_files("input[type=file]", str(HERE / "draft.txt"))

    expect(chat.loc_input).to_have_text("draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    expect(chat.loc.locator(".shiny-chat-messages-content")).not_to_contain_text(
        "draft"
    )
    controller.OutputText(page, "submissions").expect_value("1")

    expect(chat.loc_input).to_have_text("draft", timeout=10_000)
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    expect(page.get_by_role("button", name="Send message")).to_have_attribute(
        "data-state", "ready", timeout=10_000
    )

    page.keyboard.press("Escape")
    page.get_by_role("button", name="Remove draft.txt").click()
    chat.loc_input.click()
    page.keyboard.press("End")
    page.keyboard.insert_text(" ")
    page.keyboard.press("Backspace")
    expect(page.get_by_role("button", name="Send message")).to_be_enabled()
    page.get_by_role("button", name="Send message").click()
    controller.OutputText(page, "submissions").expect_value("2", timeout=30_000)
