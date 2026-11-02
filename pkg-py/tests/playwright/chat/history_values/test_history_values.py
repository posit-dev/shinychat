from __future__ import annotations

import json

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _restore_log(page: Page) -> list[dict[str, str]]:
    return json.loads(page.locator("#restore_log").inner_text())


def test_branch_values_follow_checkpoints_and_position_restores(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("all")
    # A fresh page has no conversation to restore.
    expect(page.locator("#restore_count")).to_have_text("0")

    # Completing the west response captures west on its exchange. Ordinary
    # accepted input and completion do not restore.
    chat.set_user_input("west")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("west")
    expect(page.locator("#restore_count")).to_have_text("0")

    # Editing the first message creates an east branch. on_restore receives the
    # retained parent's values before the replacement provider call starts.
    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    original.get_by_role("textbox", name="Chat message").fill("east")
    original.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    # The replacement saw the parent's restored values, not west or east.
    expect(page.locator("#provider_before_filter")).to_have_text("all")
    assert _restore_log(page) == [{"filter": "all"}]

    navigation = page.locator(".shiny-chat-sibling-nav")
    expect(navigation.locator("span")).to_have_text("2 / 2")

    # Browsing back to west restores west. Leaving east does not capture the
    # outgoing east state, so east's saved value stays intact.
    navigation.locator("button").first.click()
    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("west")
    expect(page.locator("#current_filter")).to_have_text("west")
    expect(navigation.locator("span")).to_have_text("1 / 2")
    assert _restore_log(page) == [{"filter": "all"}, {"filter": "west"}]

    # A follow-up from west captures north on its new exchange only. Completion
    # does not restore.
    chat.set_user_input("north")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected north", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("north")
    assert len(_restore_log(page)) == 2

    # Browsing to the east sibling restores east. The west-branch follow-up
    # must not have overwritten east with its live north state.
    navigation.locator("button").last.click()
    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    assert _restore_log(page)[-1] == {"filter": "east"}
    expect(navigation.locator("span")).to_have_text("2 / 2")

    # Reloading restores the selected position through on_restore as well.
    page.reload()
    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    expect(page.locator("#current_filter")).to_have_text("east")
    expect(page.locator("#restore_count")).to_have_text("1")
    assert _restore_log(page)[-1] == {"filter": "east"}
