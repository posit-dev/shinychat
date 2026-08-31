from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

# Known failure on feat/structured-content-types: this app injects a
# side-channel append_message() DURING streaming, so the extra message sits
# between turn-derived messages in the client snapshot. extend_record_linear's
# positional extras alignment (first n_derived reported messages == derived)
# then treats the trailing turn-derived message as an extra too — duplicating
# it on restore. This is the F3 "positional drop/dup" class from roborev 1063,
# dispositioned as transient: the exchange-tree rewrite (kata epic 6d0d)
# captures every server-sent message eagerly and resolves this by
# construction. strict=True so the suite flags when 6d0d (or any fix) makes
# it pass again.
pytestmark = pytest.mark.xfail(
    reason=(
        "F3-class positional snapshot/turns reconciliation bug; resolved by "
        "exchange-tree history rewrite (kata epic 6d0d). See roborev 1063 "
        "disposition on kata#c15v."
    ),
    strict=True,
)


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
        page.locator(
            ".shiny-chat-message-content", has_text="echo: first question"
        )
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
        page.locator(
            ".shiny-chat-message-content", has_text="echo: first question"
        )
    ).to_be_visible(timeout=30_000)

    # CRITICAL: the non-streaming path's HTMLDependency must be re-sent to
    # the client on cross-session restore, not just its rendered markup.
    card = page.locator(".cross-session-nonstream-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
