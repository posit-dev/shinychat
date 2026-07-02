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
        page.locator(".shiny-chat-message-content", has_text="echo: first question")
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
        page.locator(".shiny-chat-message-content", has_text="echo: first question")
    ).to_be_visible(timeout=10_000)
    expect(message_count(page)).to_have_count(3, timeout=10_000)
