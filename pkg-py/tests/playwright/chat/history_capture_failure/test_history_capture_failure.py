from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_capture_failure_notification_and_new_chat_recovery(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc_input).to_be_visible(timeout=30_000)
    chat.set_user_input("initial")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: initial", timeout=30_000)
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 1"
    )
    page.get_by_role("button", name="Retain unsupported model turn").click()
    expect(page.locator("#poison_status")).to_have_text(
        "Unsupported turn retained"
    )
    chat.set_user_input("not sent")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    notification = page.locator(".shiny-notification-error")
    expect(notification).to_be_visible(timeout=30_000)
    expect(notification).to_contain_text("Message not sent", timeout=30_000)
    expect(chat.loc.locator(".shiny-chat-user-message").last).to_contain_text("not sent")
    expect(notification).to_contain_text("saved checkpoint is unchanged")
    expect(notification).to_contain_text("New chat")
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 1"
    )
    page.get_by_role("button", name="Conversation history").click()
    page.get_by_role("button", name="New conversation", exact=True).click()
    expect(chat.loc_input).to_be_visible(timeout=30_000)
    chat.set_user_input("recovered")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: recovered", timeout=30_000)
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 2"
    )
    expect(chat.loc).not_to_contain_text("not sent")
