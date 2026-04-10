import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_bookmark_restore_preserves_user_messages(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    End-to-end bookmark test: send messages, bookmark, navigate to bookmark
    URL, and verify both user and assistant messages are restored.
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send first message and wait for response
    chat.set_user_input("Hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: Hello", timeout=10_000)

    # Send second message and wait for response
    chat.set_user_input("World")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: World", timeout=10_000)

    # Wait for the bookmark URL to appear in the query string
    # (enable_bookmarking with bookmark_on="response" updates the URL after each response)
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    bookmark_url = page.url

    # Navigate to the bookmark URL (simulates a page reload / new session)
    page.goto(bookmark_url)

    # Wait for restored chat to be visible
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    messages_container = chat.loc_messages

    # There should be 4 messages total (2 user + 2 assistant)
    expect(messages_container.locator("> *")).to_have_count(4, timeout=10_000)

    # Verify user messages have content
    user_messages = messages_container.locator("> .shiny-chat-user-message")
    expect(user_messages).to_have_count(2)
    expect(user_messages.nth(0)).to_have_text("Hello", use_inner_text=True)
    expect(user_messages.nth(1)).to_have_text("World", use_inner_text=True)

    # Verify assistant messages have content
    assistant_messages = messages_container.locator("> .shiny-chat-message")
    expect(assistant_messages).to_have_count(2)
    expect(assistant_messages.nth(0)).to_have_text(
        "You said: Hello", use_inner_text=True
    )
    expect(assistant_messages.nth(1)).to_have_text(
        "You said: World", use_inner_text=True
    )

    # Verify the message state includes all messages
    message_state = controller.OutputCode(page, "message_state")
    message_state_expected = tuple(
        [
            {"content": "Hello", "role": "user", "content_type": "markdown"},
            {"content": "You said: Hello", "role": "assistant", "content_type": "markdown"},
            {"content": "World", "role": "user", "content_type": "markdown"},
            {"content": "You said: World", "role": "assistant", "content_type": "markdown"},
        ]
    )
    message_state.expect_value(str(message_state_expected))
