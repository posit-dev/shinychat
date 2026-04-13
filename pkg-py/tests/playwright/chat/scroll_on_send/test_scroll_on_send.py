"""
Test that when the user sends a message, the chat scrolls to the bottom
so the new user message (and subsequent loading dots / response) are visible.
"""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_scroll_to_bottom_on_send(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Wait for all initial messages to render
    chat.expect_latest_message("Message 19: padding to fill the chat area.", timeout=30_000)

    messages_el = chat.loc_scroll_container

    # The chat should be scrollable with 20 messages in 400px
    is_scrollable = messages_el.evaluate(
        "el => el.scrollHeight > el.clientHeight"
    )
    assert is_scrollable, "Chat should be scrollable with 20 messages"

    # Send a user message
    chat.set_user_input("Hello from the test")
    chat.send_user_input(method="enter")

    # Wait for the user message to appear in the DOM
    user_msg = messages_el.locator(".shiny-chat-user-message").filter(has_text="Hello from the test")
    expect(user_msg).to_be_visible(timeout=5_000)

    # Wait until the scroll settles within 20px of the bottom.
    # This replaces a fixed sleep and is robust to smooth-scroll timing.
    messages_handle = messages_el.element_handle()
    page.wait_for_function(
        """el => {
            const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
            return distance <= 20;
        }""",
        arg=messages_handle,
        timeout=5000,
    )
