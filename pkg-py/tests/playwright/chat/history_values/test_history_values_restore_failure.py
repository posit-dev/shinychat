from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

READ_ONLY_MESSAGE = (
    "This conversation can be viewed but not continued. "
    "Its saved application state couldn't be restored."
)


@pytest.mark.parametrize("local_app", ["app_restore_failure.py"], indirect=True)
def test_failed_on_restore_keeps_conversation_read_only_until_new_chat(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("broken")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected broken", timeout=30_000)
    # Live submission is not a restore, so the failure has not run yet.
    expect(page.locator("#restore_attempts")).to_have_text("0")

    # Reloading restores the saved "broken" position. Its on_restore fails.
    page.reload()
    chat.expect_latest_message("Selected broken", timeout=30_000)

    bar = chat.loc.locator(".shiny-chat-readonly")
    status = bar.get_by_role("status")
    expect(status).to_contain_text(READ_ONLY_MESSAGE)
    expect(chat.loc_input).to_be_hidden()
    expect(chat.loc_input_button).to_be_hidden()
    expect(chat.loc.locator(".shiny-chat-edit-btn")).to_have_count(0)
    expect(chat.loc.get_by_role("button", name="Retry message")).to_have_count(
        0
    )
    expect(
        chat.loc.get_by_role("button", name="Regenerate message")
    ).to_have_count(0)

    # The failing callback ran once, stopped dispatch, and applied nothing.
    expect(page.locator("#restore_attempts")).to_have_text("1")
    expect(page.locator("#second_restore_calls")).to_have_text("0")
    expect(page.locator("#restore_count")).to_have_text("0")
    expect(page.locator("#current_filter")).to_have_text("all")

    # New chat is the escape: it clears read-only and focuses the composer.
    new_chat = bar.get_by_role("button", name="New chat")
    new_chat.focus()
    new_chat.press("Enter")
    expect(status).to_have_count(0)
    expect(chat.loc_input).to_be_visible(timeout=30_000)
    expect(chat.loc_input).to_be_focused()
    chat.set_user_input("north")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected north", timeout=30_000)


@pytest.mark.parametrize("local_app", ["app_restore_failure.py"], indirect=True)
def test_ordinary_saved_position_restores_without_read_only(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("west")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected west", timeout=30_000)

    page.reload()
    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("west")
    expect(page.locator("#restore_count")).to_have_text("1")
    expect(page.locator("#restore_attempts")).to_have_text("1")
    expect(page.locator("#second_restore_calls")).to_have_text("1")
    expect(chat.loc.locator(".shiny-chat-readonly")).to_have_count(0)
    expect(chat.loc_input).to_be_visible(timeout=30_000)


@pytest.mark.parametrize("local_app", ["app_restore_failure.py"], indirect=True)
def test_failed_first_message_edit_keeps_not_sent_version_and_exits_pending_edit(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.set_user_input("west")
    expect(chat.loc_input_button).to_be_enabled()
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#provider_calls")).to_have_text("1")
    page.get_by_label("Fail starting checkpoint restore").check()

    user = chat.loc.locator(".shiny-chat-user-message").first
    user.hover()
    user.locator(".shiny-chat-edit-btn").click()
    editor = user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible()
    editor.fill("north")
    user.locator(".shiny-chat-btn-send").click()

    bar = chat.loc.locator(".shiny-chat-readonly")
    expect(bar.get_by_role("status")).to_contain_text("not sent")
    expect(editor).to_have_count(0)
    expect(chat.loc_input).to_be_hidden()
    expect(user).to_contain_text("north")
    expect(user.locator(".shiny-chat-retry-error")).to_have_text("Message not sent.")
    expect(user.get_by_role("button", name="Retry message")).to_be_enabled()
    expect(chat.loc_messages.locator(":scope > *")).to_have_count(1)
    expect(page.locator("#provider_calls")).to_have_text("1")
    expect(page.locator("#restore_attempts")).to_have_text("1")
    expect(page.locator("#second_restore_calls")).to_have_text("0")
    expect(page.locator("#current_filter")).to_have_text("west")

    new_chat = bar.get_by_role("button", name="New chat")
    new_chat.focus()
    new_chat.press("Enter")
    expect(bar).to_have_count(0)
    expect(chat.loc_input).to_be_visible()
    expect(chat.loc_input).to_be_focused()
    chat.set_user_input("north")
    expect(chat.loc_input_button).to_be_enabled()
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected north", timeout=30_000)
    expect(page.locator("#provider_calls")).to_have_text("2")
