from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _loc_greeting(chat: ChatController):
    return chat.loc.locator(".shiny-chat-greeting")


def test_app_loads_and_chat_is_visible(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)


def test_greeting_is_displayed(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    greeting = _loc_greeting(chat)
    expect(greeting).to_be_visible(timeout=10_000)
    expect(greeting).to_contain_text("Welcome to the test!", timeout=10_000)


def test_send_message_gets_response(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    user_message = "Hello from the test"
    chat.set_user_input(user_message)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"You said: {user_message}", timeout=30_000)


def test_messages_reflect_conversation(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    message_state = controller.OutputCode(page, "message_state")

    user_message = "Tell me something"
    chat.set_user_input(user_message)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"You said: {user_message}", timeout=30_000)

    message_state.expect.to_contain_text(user_message, timeout=10_000)
    message_state.expect.to_contain_text(f"You said: {user_message}", timeout=10_000)
