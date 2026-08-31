from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_validate_chat_transform_assistant(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    message_state = controller.OutputCode(page, "message_state")

    # Wait for app to load
    message_state.expect_value("()", timeout=30 * 1000)

    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    expect(chat.loc_input_button).to_be_disabled()

    user_msg = "hello"
    chat.set_user_input(user_msg)
    chat.send_user_input()
    code = chat.loc_latest_message.locator("code")
    expect(code).to_have_text("hello", timeout=30 * 1000)

    user_msg2 = "return HTML"
    chat.set_user_input(user_msg2)
    chat.send_user_input()
    # The transform's HTML() result travels as a trusted html-typed payload
    # (structured html_block on the wire) and must render as LIVE HTML: a
    # real <b> element, not literal/escaped markup. If it were rendered as
    # plain text, the visible text would contain the literal "<b>" tags.
    bold = chat.loc_latest_message.locator("b")
    expect(bold).to_have_text("Transformed response")
    expect(chat.loc_latest_message).to_have_text(
        "Transformed response: return HTML"
    )
    expect(chat.loc_latest_message).not_to_contain_text("<b>")

    # Trusted HTML no longer carries <shiny-chat-raw-html> island wrapper
    # tags: the client reports the rendered html segment's raw content.
    message_state_expected = tuple(
        [
            {"content": "hello", "role": "user"},
            {"content": "Transformed response: `hello`", "role": "assistant"},
            {"content": "return HTML", "role": "user"},
            {
                "content": "<b>Transformed response</b>: return HTML",
                "role": "assistant",
            },
        ]
    )
    message_state.expect_value(str(message_state_expected))
