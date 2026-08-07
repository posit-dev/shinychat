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


def test_edit_button_revealed_via_long_press_on_touch(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A ~500ms touch hold on a user message reveals the edit button (no
    hover, no keyboard focus involved); a quick tap does not reveal it;
    tapping elsewhere afterward hides it again."""
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    first_user = page.locator(".shiny-chat-user-message").first
    edit_btn = first_user.locator(".shiny-chat-edit-btn")
    box = first_user.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    touch_point = {
        "pointerType": "touch",
        "clientX": x,
        "clientY": y,
        "bubbles": True,
    }

    # A quick tap, well under the hold threshold, must not reveal the button.
    first_user.dispatch_event("pointerdown", touch_point)
    first_user.dispatch_event("pointerup", touch_point)
    page.wait_for_timeout(600)
    expect(edit_btn).to_have_css("opacity", "0")

    # A ~500ms hold reveals it.
    first_user.dispatch_event("pointerdown", touch_point)
    page.wait_for_timeout(600)
    expect(edit_btn).to_have_css("opacity", "1")
    first_user.dispatch_event("pointerup", touch_point)

    # It's clickable while revealed, and opens the normal edit box.
    edit_btn.click()
    editor = first_user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    first_user.locator(".shiny-chat-edit-cancel-outside").click()

    # Long-press again, then tap elsewhere -- the reveal should clear.
    first_user.dispatch_event("pointerdown", touch_point)
    page.wait_for_timeout(600)
    expect(edit_btn).to_have_css("opacity", "1")
    first_user.dispatch_event("pointerup", touch_point)
    page.locator("body").dispatch_event(
        "pointerdown",
        {"pointerType": "touch", "clientX": 5, "clientY": 5, "bubbles": True},
    )
    expect(edit_btn).to_have_css("opacity", "0")


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


def test_editing_a_scrolled_out_message_autoscrolls_to_new_response(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Editing a message that's scrolled out of view (an early message in a
    long conversation) must still auto-scroll down to the newly generated
    response -- the same way an ordinary (non-edit) send already does."""
    page.set_viewport_size({"width": 800, "height": 400})
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Send enough messages that the small viewport overflows.
    for i in range(6):
        chat.set_user_input(f"message {i}")
        chat.send_user_input(method="enter")
        chat.expect_latest_message(f"Echo: message {i}", timeout=10_000)

    # Edit an early message. Playwright scrolls it into view to click the
    # edit button, which leaves the container scrolled away from the bottom
    # -- exactly how a real user would end up there.
    user_messages = page.locator(".shiny-chat-user-message")
    early_user = user_messages.nth(1)
    early_user.hover()
    edit_btn = early_user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()

    scroll_container = chat.loc_scroll_container
    at_bottom_before = scroll_container.evaluate(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 2"
    )
    assert not at_bottom_before, (
        "test setup failed: container should be scrolled away from the bottom"
    )

    editor = early_user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("edited message 1")
    early_user.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("Echo: edited message 1", timeout=15_000)

    # The newly generated response should have been auto-scrolled into view.
    expect(chat.loc_latest_message).to_be_in_viewport(timeout=5_000)

    # The scroll-to-bottom is a spring animation, not an instant jump -- wait
    # for it to actually arrive rather than sampling once after a fixed delay.
    page.wait_for_function(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 2",
        arg=scroll_container.element_handle(),
        timeout=10_000,
    )


def test_sibling_navigation_scrolled_away_autoscrolls_to_new_branch(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Switching to a sibling branch (created by editing) must auto-scroll
    down to reveal that branch's response, the same way editing itself
    already does -- navigation currently has no equivalent trigger."""
    page.set_viewport_size({"width": 800, "height": 400})
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Filler messages so the container overflows.
    for i in range(6):
        chat.set_user_input(f"filler {i}")
        chat.send_user_input(method="enter")
        chat.expect_latest_message(f"Echo: filler {i}", timeout=10_000)

    chat.set_user_input("hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Echo: hello", timeout=10_000)

    # Edit the last message to create a second branch/response.
    user_messages = page.locator(".shiny-chat-user-message")
    target_user = user_messages.last
    target_user.hover()
    edit_btn = target_user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    # Click via JS, bypassing Playwright's auto-scroll-into-view -- otherwise
    # each click would do the container's scrolling job for it, masking bugs
    # in the app's own auto-scroll logic.
    edit_btn.evaluate("el => el.click()")
    editor = target_user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("hello again")
    target_user.locator(".shiny-chat-btn-send").evaluate("el => el.click()")
    chat.expect_latest_message("Echo: hello again", timeout=15_000)

    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)

    scroll_container = chat.loc_scroll_container
    scroll_container.hover()
    for _ in range(10):
        page.mouse.wheel(0, -1000)
        page.wait_for_timeout(50)
    at_bottom_before = scroll_container.evaluate(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 2"
    )
    assert not at_bottom_before, (
        "test setup failed: container should be scrolled away from the bottom"
    )

    prev_btn = sibling_nav.locator("button").first
    prev_btn.evaluate("el => el.click()")

    chat.expect_latest_message("Echo: hello", timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("1 / 2", timeout=5_000)

    # The scroll-to-bottom is a spring animation, not an instant jump -- wait
    # for it to actually arrive rather than sampling once after a fixed delay.
    page.wait_for_function(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 2",
        arg=scroll_container.element_handle(),
        timeout=10_000,
    )


def test_sibling_metadata_refresh_does_not_override_manual_scroll(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Passive sibling metadata updates must not re-engage bottom scrolling."""
    page.set_viewport_size({"width": 800, "height": 400})
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    for i in range(6):
        chat.set_user_input(f"filler {i}")
        chat.send_user_input(method="enter")
        chat.expect_latest_message(f"Echo: filler {i}", timeout=10_000)

    scroll_container = chat.loc_scroll_container
    scroll_container.hover()
    for _ in range(10):
        page.mouse.wheel(0, -1000)
        page.wait_for_timeout(50)

    at_bottom_before = scroll_container.evaluate(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight < 2"
    )
    assert not at_bottom_before

    page.evaluate(
        """() => Shiny.setInputValue(
            "test_passive_sibling_update",
            Date.now(),
            {priority: "event"}
        )"""
    )
    expect(page.locator(".shiny-chat-sibling-nav")).to_be_visible(timeout=5_000)

    distance_from_bottom = scroll_container.evaluate(
        "el => el.scrollHeight - el.scrollTop - el.clientHeight"
    )
    assert distance_from_bottom >= 2, (
        "passive sibling metadata refresh should not override manual scrolling"
    )
