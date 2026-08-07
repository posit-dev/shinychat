from __future__ import annotations

from playwright.sync_api import Page, expect
from shinychat.playwright import ChatController


def wait_for_history_save(page: Page, expected_count: int) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    drawer = page.locator(".shiny-chat-history-drawer")
    expect(drawer).to_be_visible()
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        expected_count, timeout=10_000
    )
    page.keyboard.press("Escape")
    drawer.wait_for(state="hidden")


def test_r_history_restores_and_continues_after_reload(
    page: Page, r_app_url: str
) -> None:
    page.goto(r_app_url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("first")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first", timeout=30_000)
    wait_for_history_save(page, expected_count=1)

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: first", timeout=30_000)

    chat.set_user_input("second")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second", timeout=30_000)
    wait_for_history_save(page, expected_count=1)

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: second", timeout=30_000)
    messages = chat.loc_messages.locator("> *")
    expect(messages).to_have_text(
        ["first", "echo: first", "second", "echo: second"],
        use_inner_text=True,
    )
