from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

from tests.playwright.utils.deploy_utils import skip_on_webkit


@skip_on_webkit
def test_validate_chat_append_user_message(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "foo-chat")

    # Verify starting state
    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    chat.set_user_input("A user message")
    chat.send_user_input()
    chat.expect_latest_message("You said: A user message", timeout=30 * 1000)
