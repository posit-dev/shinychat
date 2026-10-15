from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def start_conversation(page: Page, text: str) -> None:
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.set_user_input(text)
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"echo: {text}", timeout=30_000)


def expect_filter_state(page: Page, value: str) -> None:
    expect(page.locator("#filter_state")).to_have_text(
        f"filter: {value}", timeout=30_000
    )


def test_bookmark_mode_switch_restores_inputs(
    page: Page, local_app: ShinyAppProc
) -> None:
    """An in-session conversation switch restores the target's transcript
    and its saved input values in place (mechanism D5: a soft URL update,
    never a reload-per-switch). Auxiliary Shiny inputs come back through the
    conversation's captured `values` via @chat.history.on_restore."""
    page.goto(local_app.url)

    # Conversation A: set the input, then chat (the save captures the value
    # and mints a bookmark state id).
    controller.InputText(page, "filter_text").set("penguins")
    expect_filter_state(page, "penguins")
    start_conversation(page, "first question")
    page.wait_for_url(lambda url: "_state_id_=" in url, timeout=30_000)

    # New chat: fresh conversation in place. No reload happens, so the
    # client keeps its current auxiliary input value (raw inputs are only
    # synced through on_save/on_restore, never the conversation switch).
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()

    # Conversation B, with a different filter value.
    controller.InputText(page, "filter_text").set("second value")
    expect_filter_state(page, "second value")
    start_conversation(page, "second question")

    # Switch back to A: in-place restore brings back A's transcript and A's
    # captured input value, and the URL soft-points at A's bookmark state id
    # (replaceState — no navigation, no reload).
    open_drawer(page)
    conversation = page.locator(
        ".shiny-chat-history-item", has_text="first question"
    )
    select = conversation.locator(".shiny-chat-history-item-select")
    expect(select).to_be_enabled(timeout=30_000)
    select.click()
    controller.InputText(page, "filter_text").expect_value(
        "penguins", timeout=30_000
    )
    ChatController(page, "chat").expect_latest_message(
        "echo: first question", timeout=30_000
    )
    assert "_state_id_=" in page.url


def test_bookmark_mode_reload_returns_to_conversation(
    page: Page, local_app: ShinyAppProc
) -> None:
    """The bookmark URL tracks the active conversation, so a plain reload
    restores transcript AND inputs."""
    page.goto(local_app.url)

    controller.InputText(page, "filter_text").set("gentoo")
    start_conversation(page, "reload me")
    # update_query_string has run by the time the response landed.
    page.wait_for_url(lambda url: "_state_id_=" in url, timeout=10_000)

    page.reload()

    controller.InputText(page, "filter_text").expect_value(
        "gentoo", timeout=30_000
    )
    ChatController(page, "chat").expect_latest_message(
        "echo: reload me", timeout=30_000
    )


def test_bookmark_mode_stale_state_id_falls_back_to_draft(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A bogus _state_id_ must not break the app: history falls through to a
    fresh draft."""
    page.goto(local_app.url + "?_state_id_=doesnotexist")

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    # App is functional: a new conversation can be started.
    start_conversation(page, "fresh start")
