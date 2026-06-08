import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_bookmark_restores_echoed_slash_command_but_not_side_effects(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    End-to-end: an echoed slash command (and its handler's reply) is bookmarked
    and restored as static transcript entries, while a side-effect-only command
    (echo=False) leaves nothing to restore.
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    # Wait for server-registered commands to reach the client.
    expect(chat.loc_input).to_have_attribute("aria-haspopup", "listbox")

    # Side-effect-only command: runs (shows a notification) but stores nothing.
    chat.loc_input.click()
    chat.loc_input.type("/note")
    page.keyboard.press("Enter")  # select from palette
    page.keyboard.press("Enter")  # submit
    notification = page.locator(".shiny-notification")
    expect(notification).to_be_visible(timeout=10_000)
    expect(notification).to_contain_text("noted")

    # Echoed command: stores the `/greet world` user message and an assistant
    # reply. Being assistant-terminated, this triggers bookmark_on="response".
    chat.loc_input.click()
    chat.loc_input.type("/greet")
    page.keyboard.press("Enter")  # select from palette
    chat.loc_input.type("world")
    page.keyboard.press("Enter")  # submit
    chat.expect_latest_message("Hello! You said: world", timeout=10_000)

    # Wait for the bookmark URL to appear in the query string.
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=10_000)
    bookmark_url = page.url

    # Navigate to the bookmark URL (simulates a page reload / new session).
    page.goto(bookmark_url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    messages_container = chat.loc_messages
    # Only the echoed exchange is restored: the /note side effect is gone.
    expect(messages_container.locator("> *")).to_have_count(2, timeout=10_000)

    user_messages = messages_container.locator("> .shiny-chat-user-message")
    expect(user_messages).to_have_count(1)
    expect(user_messages.nth(0)).to_have_text("/greet world", use_inner_text=True)

    assistant_messages = messages_container.locator("> .shiny-chat-message")
    expect(assistant_messages).to_have_count(1)
    expect(assistant_messages.nth(0)).to_have_text(
        "Hello! You said: world", use_inner_text=True
    )

    # The side-effect-only command is absent from the restored transcript and
    # its notification is not replayed.
    all_text = messages_container.locator("> *").all_text_contents()
    assert not any("/note" in m or "noted" in m for m in all_text)

    # Message state confirms exactly the echoed exchange round-tripped.
    message_state = controller.OutputCode(page, "message_state")
    message_state_expected = tuple(
        [
            {"content": "/greet world", "role": "user"},
            {"content": "Hello! You said: world", "role": "assistant"},
        ]
    )
    message_state.expect_value(str(message_state_expected))
