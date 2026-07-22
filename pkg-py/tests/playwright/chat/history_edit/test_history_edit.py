from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


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

    # Fill the edit box and submit
    editor = second_user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("universe")
    second_user.locator(".shiny-chat-btn-send").click()

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

    editor = second_user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("universe")
    second_user.locator(".shiny-chat-btn-send").click()

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


def test_edit_button_reachable_via_keyboard_without_hover(
    page: Page, local_app: ShinyAppProc
) -> None:
    """The edit pencil button must be reachable and visibly revealed via
    real Tab-key navigation, with no mouse hover involved -- otherwise
    keyboard-only users have no way to discover or activate it."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    # Deliberately never call .hover() anywhere in this test -- drive focus
    # with real Tab keypresses so the browser's :focus-visible heuristic
    # (which a programmatic .focus() call would not satisfy) is exercised
    # the same way it would be for an actual keyboard user.
    first_user = page.locator(".shiny-chat-user-message").first
    edit_btn = first_user.locator(".shiny-chat-edit-btn")

    reached = False
    for _ in range(40):
        page.keyboard.press("Tab")
        if edit_btn.evaluate("el => el === document.activeElement"):
            reached = True
            break
    assert reached, "edit button was never reached via Tab key navigation"

    # Playwright's own visibility check ignores opacity, so also assert the
    # button is actually painted (not left at opacity: 0) once focused.
    # (to_have_css polls, which absorbs the button's opacity transition.)
    expect(edit_btn).to_have_css("opacity", "1")


def test_only_one_edit_box_open_at_a_time(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Opening edit on one user message closes any other open edit box."""
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

    user_messages = page.locator(".shiny-chat-user-message")
    first_user = user_messages.nth(0)
    second_user = user_messages.nth(1)

    # Open the edit box on the first message
    first_user.hover()
    first_edit_btn = first_user.locator(".shiny-chat-edit-btn")
    expect(first_edit_btn).to_be_visible(timeout=5_000)
    first_edit_btn.click()

    edit_boxes = page.locator(".shiny-chat-edit-box")
    expect(edit_boxes).to_have_count(1)
    first_editor = first_user.get_by_role("textbox", name="Chat message")
    expect(first_editor).to_be_visible(timeout=5_000)
    expect(first_editor).to_have_text("hello")

    # Without saving or cancelling, open the edit box on the second message
    second_user.hover()
    second_edit_btn = second_user.locator(".shiny-chat-edit-btn")
    expect(second_edit_btn).to_be_visible(timeout=5_000)
    second_edit_btn.click()

    # Exactly one edit box should remain, now on the second message
    expect(edit_boxes).to_have_count(1)
    second_editor = second_user.get_by_role("textbox", name="Chat message")
    expect(second_editor).to_be_visible(timeout=5_000)
    expect(second_editor).to_have_text("world")


def test_edit_add_and_remove_attachment_resends_with_final_set(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Editing a message's attachments (seed, remove, add) resends the final set."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send a message with one attached image via the main composer.
    page.set_input_files("input[type=file]", str(HERE / "one_px.png"))
    expect(page.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)
    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    # Open edit on that user message; its attachment should be pre-seeded.
    user_messages = page.locator(".shiny-chat-user-message")
    first_user = user_messages.nth(0)
    first_user.hover()
    edit_btn = first_user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()

    edit_box = first_user.locator(".shiny-chat-edit-box")
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)

    # Remove the pre-seeded attachment, then attach a new one via the edit
    # box's own attach button/hidden file input.
    edit_box.locator(".shiny-chat-input-thumbnail button").click()
    expect(edit_box.locator(".shiny-chat-input-thumbnail")).to_have_count(0)
    edit_box.locator("input[type=file]").set_input_files(str(HERE / "one_px.png"))
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)

    editor = first_user.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("hello again")
    first_user.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("Echo: hello again", timeout=15_000)

    # The resent user message still carries exactly one attached image.
    expect(first_user.locator(".shiny-chat-message-image")).to_have_count(1)
