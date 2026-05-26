from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_chat_module_renders(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chatmod-chat")
    expect(chat.loc).to_be_visible(timeout=30_000)


def test_chat_module_cancel_enabled(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chatmod-chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(chat.loc).to_have_attribute("enable-cancel", "")


def test_chat_module_submit_and_receive_response(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chatmod-chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("hello")
    chat.send_user_input()
    chat.expect_latest_message("Echo: hello ", timeout=30_000)


def test_chat_module_status_starts_idle(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chatmod-chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    status = page.locator("#status_out")
    expect(status).to_have_text("idle", timeout=10_000)


def test_chat_module_multiple_messages(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chatmod-chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("first")
    chat.send_user_input()
    chat.expect_latest_message("Echo: first ", timeout=30_000)

    chat.set_user_input("second")
    chat.send_user_input()
    chat.expect_latest_message("Echo: second ", timeout=30_000)
