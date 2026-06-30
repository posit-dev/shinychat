from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_edit_creates_branch_and_regenerates(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Edit a user message: verify new response appears and sibling nav shows 2 / 2."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send two messages
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    chat.set_user_input("world")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: world", timeout=10_000)

    # Locate the second user message and hover to reveal the edit button
    user_messages = page.locator(".shiny-chat-user-message")
    second_user = user_messages.nth(1)
    second_user.hover()

    # Click the edit button
    edit_btn = second_user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()

    # Fill the textarea and submit
    textarea = second_user.locator("textarea")
    expect(textarea).to_be_visible(timeout=5_000)
    textarea.fill("universe")
    second_user.locator(".shiny-chat-edit-submit").click()

    # New response should appear
    chat.expect_latest_message("Echo: universe", timeout=15_000)

    # Sibling navigation should show "2 / 2" on the edited user message
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)


def test_sibling_navigation_switches_branch(
    page: Page, local_app: ShinyAppProc
) -> None:
    """After creating a branch via edit, clicking prev restores the original response."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send two messages
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    chat.set_user_input("world")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: world", timeout=10_000)

    # Edit the second user message to create a branch
    user_messages = page.locator(".shiny-chat-user-message")
    second_user = user_messages.nth(1)
    second_user.hover()

    edit_btn = second_user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()

    textarea = second_user.locator("textarea")
    expect(textarea).to_be_visible(timeout=5_000)
    textarea.fill("universe")
    second_user.locator(".shiny-chat-edit-submit").click()

    chat.expect_latest_message("Echo: universe", timeout=15_000)

    # Sibling nav should be visible on the current (second) branch
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)

    # Navigate to the previous sibling (original "world" branch)
    prev_btn = sibling_nav.locator("button").first
    prev_btn.click()

    # Should now show the original response and the nav should read "1 / 2"
    chat.expect_latest_message("Echo: world", timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("1 / 2", timeout=5_000)
