from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_auto_dev_memory_survives_plain_reload(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("reload dev memory")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: reload dev memory", timeout=30_000)

    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=10_000
    )
    before = page.evaluate("localStorage.getItem('shinychat-current:chat')")
    assert before
    page.keyboard.press("Escape")
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.expect_latest_message("echo: reload dev memory", timeout=30_000)
    after = page.evaluate("localStorage.getItem('shinychat-current:chat')")
    assert after == before
