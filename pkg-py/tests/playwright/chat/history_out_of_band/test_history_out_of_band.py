from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

# Same F3 "positional drop/dup" class as the strict-xfailed sister tests in
# history_cross_session_deps/ and history_ui_offset_after_restore/ (this test
# was missed when those were xfailed). Diagnosed 2026-08-31 during kata#af81:
# the save effect fires mid-stream with snapshot [user, oob] while the mock
# chatlas client has already recorded both turns, so extend_record_linear's
# positional rule swallows the out-of-band message (never persisted); the
# follow-up save then treats the turn-derived reply as an extra and
# duplicates it. Restore faithfully replays the corrupted store. Resolved by
# the exchange-tree history rewrite (kata epic 6d0d). strict=True so the
# suite flags when a fix makes it pass again.
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


def message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def test_out_of_band_message_survives_history_restore(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    A message appended out-of-band (a second, independent `append_message`
    call inside `on_user_submit`, not the "reply" to the user's turn) must be
    captured in the client-authoritative `${id}_messages` snapshot and thus
    round-trip through a history save/restore, just like the primary
    assistant reply does.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    marker = page.locator("#oob-marker-content")

    # --- Conversation A: one exchange producing 3 messages (user, out-of-band
    # notice, streamed reply). ---
    chat.set_user_input("first question")
    chat.send_user_input(method="enter")
    expect(marker).to_be_visible(timeout=10_000)
    expect(marker).to_have_text("out-of-band notice")
    expect(
        page.locator(
            ".shiny-chat-message-content", has_text="echo: first question"
        )
    ).to_be_visible(timeout=10_000)
    expect(message_count(page)).to_have_count(3, timeout=10_000)

    # --- Switch to a new conversation so there's something to restore from. ---
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    expect(marker).to_have_count(0)

    # --- Switch back to conversation A: both the out-of-band notice and the
    # streamed reply must still be present after restore, not just one of
    # them. ---
    open_drawer(page)
    conv_a = page.locator(".shiny-chat-history-item").filter(
        has_text="first question"
    )
    conv_a.click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    expect(marker).to_be_visible(timeout=10_000)
    expect(marker).to_have_text("out-of-band notice")
    expect(
        page.locator(
            ".shiny-chat-message-content", has_text="echo: first question"
        )
    ).to_be_visible(timeout=10_000)
    expect(message_count(page)).to_have_count(3, timeout=10_000)
