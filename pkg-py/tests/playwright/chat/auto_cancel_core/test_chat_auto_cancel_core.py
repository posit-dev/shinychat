from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_auto_chat_cancel_uses_stream_controller(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "mod-chat")
    cancel_requested = controller.OutputCode(page, "cancel_requested")

    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("cancel this response")
    chat.send_user_input(method="enter")

    cancel_button = chat.loc_input_container.locator(".shiny-chat-btn-cancel")
    expect(cancel_button).to_be_visible(timeout=30_000)
    cancel_button.click()

    cancel_requested.expect_value("True", timeout=30_000)
