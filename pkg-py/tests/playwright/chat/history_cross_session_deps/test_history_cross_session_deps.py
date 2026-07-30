from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    expect(page.locator(".shiny-chat-history-trigger")).to_be_visible(
        timeout=30_000
    )
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_html_deps_reregister_across_sessions(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    HTMLDependency CSS/JS carried by chat messages must be re-registered
    after a *cross-session* history restore: reloading the page fresh (a
    brand new Shiny session, unlike an in-session conversation switch) and
    then restoring the saved conversation from the history drawer.

    Covers both the non-streaming (`append_message()`) and streaming
    (`append_message_stream()`) dependency paths, which are appended
    together on each submit.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    card = page.locator(".cross-session-nonstream-card")

    chat.set_user_input("first question")
    chat.send_user_input(method="enter")
    expect(
        page.locator(".shiny-chat-message-content", has_text="echo: first question")
    ).to_be_visible(timeout=30_000)

    expect(card).to_be_visible(timeout=10_000)
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)

    # Sync point: make sure the active conversation ID is written to
    # localStorage (via the drawer, as in history_restore_on_reload) before
    # reloading, so restore_mode="browser" restores the right conversation.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=10_000
    )
    page.keyboard.press("Escape")
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    # Reload the page fresh: this starts a brand new Shiny session, unlike
    # an in-session conversation switch.
    page.reload()
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Transcript (including the streamed reply) is restored.
    expect(
        page.locator(".shiny-chat-message-content", has_text="echo: first question")
    ).to_be_visible(timeout=30_000)

    # CRITICAL: the non-streaming path's HTMLDependency must be re-sent to
    # the client on cross-session restore, not just its rendered markup.
    card = page.locator(".cross-session-nonstream-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
