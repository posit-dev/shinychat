from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def test_filter_follows_edit_siblings_and_position_specific_reload(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("all")

    chat.set_user_input("west")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("west")

    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    original.get_by_role("textbox", name="Chat message").fill("east")
    original.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    expect(page.locator("#navigation_log")).to_contain_text('"reason": "edit"')
    edit_events = json.loads(page.locator("#navigation_log").inner_text())
    assert len(edit_events) == 1
    edit = edit_events[0]
    assert edit["values"] == {"filter": "all"}
    assert edit["previous_values"] == {"filter": "west"}
    assert edit["exchange_id"] != edit["previous_exchange_id"]
    # The navigation hook ran before the replacement provider consumed input.
    expect(page.locator("#provider_before_filter")).to_have_text("all")
    expect(page.locator("#restore_count")).to_have_text("0")

    navigation = page.locator(".shiny-chat-sibling-nav")
    expect(navigation.locator("span")).to_have_text("2 / 2")
    navigation.locator("button").first.click()

    chat.expect_latest_message("Selected west", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("west")
    expect(page.locator("#current_filter")).to_have_text("west")
    expect(page.locator("#navigation_log")).to_contain_text(
        '"previous_values": {"filter": "east"}'
    )
    west_events = json.loads(page.locator("#navigation_log").inner_text())
    assert len(west_events) == 2
    west = west_events[-1]
    assert west["reason"] == "navigate"
    assert west["values"] == {"filter": "west"}
    assert west["previous_values"] == {"filter": "east"}
    assert west["exchange_id"] == edit["previous_exchange_id"]
    assert west["previous_exchange_id"] != west["exchange_id"]
    expect(navigation.locator("span")).to_have_text("1 / 2")
    expect(page.locator("#restore_count")).to_have_text("0")

    navigation.locator("button").last.click()
    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    # This target value is unique to the rightward navigation event.
    expect(page.locator("#navigation_log")).to_contain_text(
        '"values": {"filter": "east"}'
    )
    east_events = json.loads(page.locator("#navigation_log").inner_text())
    assert len(east_events) == 3
    east = east_events[-1]
    assert east["reason"] == "navigate"
    assert east["values"] == {"filter": "east"}
    assert east["previous_values"] == {"filter": "west"}
    assert east["exchange_id"] == west["previous_exchange_id"]
    assert east["previous_exchange_id"] == west["exchange_id"]
    expect(navigation.locator("span")).to_have_text("2 / 2")
    expect(page.locator("#restore_count")).to_have_text("0")

    # Observe the existing history publication point before a new session loads
    # the selected leaf. Reload calls on_restore, not on_navigate.
    page.locator(".shiny-chat-history-trigger").click()
    expect(
        page.locator(".shiny-chat-history-item", has_text="west")
    ).to_have_count(1)
    page.keyboard.press("Escape")
    page.reload()
    chat.expect_latest_message("Selected east", timeout=30_000)
    expect(page.locator("#region_filter")).to_have_value("east")
    expect(page.locator("#current_filter")).to_have_text("east")
    expect(page.locator("#restore_count")).to_have_text("1")
    expect(page.locator("#navigation_log")).to_have_text("[]")
