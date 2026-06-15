from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_server_authored_assistant_attachment_renders(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    A server-authored assistant message carrying an ``Attachment`` (the public
    ``append_message(ChatMessage(role="assistant", attachments=[...]))`` API)
    must render its image. This exercises the complete-message ``message``
    action's attachment segments for the assistant role, which has no user
    upload / ``INPUT_SENT`` path behind it.
    """
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("show me the chart")
    chat.send_user_input(method="enter")
    chat.expect_latest_message(
        "Here is the chart you asked for.", timeout=10_000
    )

    # The assistant message rendered the attached image (assistant bubbles use
    # the `shiny-chat-message` class; user bubbles use `shiny-chat-user-message`).
    image = page.locator(".shiny-chat-message .shiny-chat-message-image")
    expect(image).to_have_count(1, timeout=10_000)
