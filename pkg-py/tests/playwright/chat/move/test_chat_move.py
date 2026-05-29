from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_chat_survives_dom_move(page: Page, local_app: ShinyAppProc) -> None:
    """Regression test for #121: moving the chat to another DOM container
    must preserve the rendered conversation (greeting + streamed replies)."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    initial_message = "Hello! How can I help you today?"
    chat.expect_latest_message(initial_message, timeout=30 * 1000)

    # Send a message so the conversation includes a dynamically appended reply
    # that lives only in client-side state (not in the server-rendered HTML).
    user_message = "I need help with something"
    chat.set_user_input(user_message)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"You said: {user_message}")

    # The chat starts under #left.
    expect(page.locator("#left #chat")).to_have_count(1)

    # Move it to #right.
    page.locator("#move").click()
    expect(page.locator("#right #chat")).to_have_count(1)
    expect(page.locator("#left #chat")).to_have_count(0)

    # The full conversation must survive the move.
    expect(chat.loc).to_contain_text(initial_message)
    chat.expect_latest_message(f"You said: {user_message}")

    # And the chat must remain functional after the move.
    follow_up = "thanks"
    chat.set_user_input(follow_up)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"You said: {follow_up}")
