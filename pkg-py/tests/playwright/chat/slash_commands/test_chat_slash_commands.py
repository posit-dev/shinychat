from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_slash_command_palette_opens(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/")

    palette = page.locator(".shiny-chat-slash-palette")
    expect(palette).to_be_visible()
    expect(palette.locator(".shiny-chat-slash-palette-item")).to_have_count(4)


def test_slash_command_fires_handler(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    # Wait for the server-registered commands to reach the client before
    # selecting one (the editor advertises the listbox once they arrive).
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    # Type /greet and select it, then add args and submit
    ctrl.loc_input.click()
    ctrl.loc_input.type("/greet")
    page.keyboard.press("Enter")  # select the command from palette
    page.keyboard.type("world")
    page.keyboard.press("Enter")  # submit

    ctrl.expect_latest_message("Hello! You said: world", timeout=10_000)


def test_slash_command_does_not_fire_on_user_submit(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    # Wait for the server-registered commands to reach the client before
    # selecting one (the editor advertises the listbox once they arrive).
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/greet")
    page.keyboard.press("Enter")  # select command
    page.keyboard.type("test")
    page.keyboard.press("Enter")  # submit

    ctrl.expect_latest_message("Hello! You said: test", timeout=10_000)
    # Verify no "Echo:" message was added (on_user_submit didn't fire)
    messages = ctrl.loc_messages.locator("> *").all_text_contents()
    assert not any("Echo:" in m for m in messages)


def test_regular_message_bypasses_slash_commands(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)

    ctrl.set_user_input("hello there")
    ctrl.send_user_input()

    ctrl.expect_latest_message("Echo: hello there", timeout=10_000)


def test_slash_palette_keyboard_navigation(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/")

    palette = page.locator(".shiny-chat-slash-palette")
    expect(palette).to_be_visible()

    first_item = palette.locator(".shiny-chat-slash-palette-item").first
    expect(first_item).to_have_class("shiny-chat-slash-palette-item highlighted")

    page.keyboard.press("ArrowDown")
    second_item = palette.locator(".shiny-chat-slash-palette-item").nth(1)
    expect(second_item).to_have_class("shiny-chat-slash-palette-item highlighted")

    page.keyboard.press("Escape")
    expect(palette).not_to_be_visible()


def test_unrecognized_slash_sent_as_regular_input(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)

    ctrl.set_user_input("/unknown hello")
    ctrl.send_user_input()

    # Should fall through to on_user_submit as regular input
    ctrl.expect_latest_message("Echo: /unknown hello", timeout=10_000)


def test_slash_palette_filter(page: Page, local_app: ShinyAppProc):
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/gr")

    palette = page.locator(".shiny-chat-slash-palette")
    expect(palette).to_be_visible()
    expect(palette.locator(".shiny-chat-slash-palette-item")).to_have_count(1)
    expect(palette.locator(".shiny-chat-slash-palette-name")).to_have_text("/greet")


def test_client_side_slash_command_echo(page: Page, local_app: ShinyAppProc):
    """Client-side /ping: JS listener sets echo=true, so user message appears; no server round-trip."""
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/ping")
    page.keyboard.press("Enter")  # select from palette
    page.keyboard.press("Enter")  # submit

    # The JS listener set echo=true, so /ping should appear as a user message
    ctrl.expect_latest_message("/ping", timeout=10_000)
    # No assistant/loading message should be added (no server handler)
    messages = ctrl.loc_messages.locator("> *").all_text_contents()
    assert not any("Hello!" in m or "Echo:" in m for m in messages)


def test_side_effect_slash_command_no_echo(page: Page, local_app: ShinyAppProc):
    """/note has echo=False: handler runs (shows notification) but no user message is stored."""
    page.goto(local_app.url)
    ctrl = ChatController(page, "chat")
    expect(ctrl.loc).to_be_visible(timeout=30_000)
    expect(ctrl.loc_input).to_have_attribute("aria-haspopup", "listbox")

    ctrl.loc_input.click()
    ctrl.loc_input.type("/note")
    page.keyboard.press("Enter")  # select from palette
    page.keyboard.press("Enter")  # submit

    # Server handler ran: "noted" notification should appear
    notification = page.locator(".shiny-notification")
    expect(notification).to_be_visible(timeout=10_000)
    expect(notification).to_contain_text("noted")

    # echo=False: /note must NOT appear as a user message in the transcript
    messages = ctrl.loc_messages.locator("> *").all_text_contents()
    assert not any("/note" in m for m in messages)
