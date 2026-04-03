import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_bookmark_with_htmldep_in_tool_result(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Bookmarking should succeed when a tool result contains a ToolResultDisplay
    with HTMLDependency objects in its html/icon/footer fields.

    Regression test for https://github.com/posit-dev/shinychat/issues/188
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message to trigger the tool
    chat.set_user_input("Show me a widget")
    chat.send_user_input(method="enter")

    # Wait for an assistant message (the LLM response after tool execution)
    assistant_msgs = chat.loc_messages.locator("> .shiny-chat-message")
    expect(assistant_msgs.first).to_be_visible(timeout=60_000)

    # The bookmark_on="response" default should auto-bookmark after response.
    # If serialization of ToolResultDisplay (with HTMLDependency) fails,
    # the URL won't get a _state_id_ parameter.
    page.wait_for_url(re.compile(r"\?_state_id_="), timeout=30_000)
    bookmark_url = page.url

    # Navigate to the bookmark URL to verify restore also works
    page.goto(bookmark_url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Verify at least 1 user message was restored
    user_msgs = chat.loc_messages.locator("> .shiny-chat-user-message")
    expect(user_msgs.first).to_be_visible(timeout=30_000)
