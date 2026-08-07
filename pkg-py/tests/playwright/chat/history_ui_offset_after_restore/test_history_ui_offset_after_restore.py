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


def switch_to_conversation(page: Page, text: str) -> None:
    open_drawer(page)
    page.locator(".shiny-chat-history-item").filter(has_text=text).click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")


def start_new_conversation(page: Page) -> None:
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")


def test_new_turn_ui_survives_second_restore(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Regression test for a correct server transcript cursor after replay.

    Sequence:
      1. Conversation A: submit "q1" -> rich reply with marker #1. Wait for
         save.
      2. Start a new conversation (A's messages leave the DOM).
      3. Switch back to A (first restore -- this is where `ui_offset` goes
         stale under the bug).
      4. Submit "q2" in A -> rich reply with marker #2. Under the bug, this
         turn's saved node also re-absorbs q1's already-persisted messages.
      5. Switch away and back to A again (second restore).
      6. Assert the restored transcript has exactly the 6 expected messages
         (q1, marker #1, echo q1, q2, marker #2, echo q2) with no duplicates
         -- i.e. q2's turn was persisted with only its own `node.ui`, not
         polluted with re-absorbed copies of q1's messages.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    expect(page.locator("pre#save_count.shiny-text-output")).to_have_text(
        "0", timeout=10_000
    )

    all_messages = page.locator(
        ".shiny-chat-message-content, .shiny-chat-user-message-content"
    )
    messages = page.locator("pre#messages.shiny-text-output")
    record = page.locator("pre#record.shiny-text-output")

    # --- Conversation A, turn 1: rich reply with marker #1. ---
    chat.set_user_input("q1")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: q1", timeout=30_000)
    card_q1 = page.locator(
        ".ui-offset-marker-card", has_text="rich reply for: q1"
    )
    expect(card_q1).to_have_count(1, timeout=10_000)
    expect(messages).to_contain_text("rich reply for: q1", timeout=10_000)
    expect(record).to_contain_text("rich reply for: q1", timeout=10_000)

    # --- Start a new conversation: conversation A's messages leave the DOM. ---
    start_new_conversation(page)
    expect(page.locator(".ui-offset-marker-card")).to_have_count(0)

    # --- Switch back to A: first restore. This is where `ui_offset` would
    # go stale under the bug. ---
    switch_to_conversation(page, "q1")
    chat.expect_latest_message("echo: q1", timeout=30_000)
    expect(card_q1).to_have_count(1, timeout=10_000)

    # --- Conversation A, turn 2: rich reply with marker #2. Under the bug,
    # this turn's saved node re-absorbs q1's already-persisted messages. ---
    chat.set_user_input("q2")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: q2", timeout=30_000)
    card_q2 = page.locator(
        ".ui-offset-marker-card", has_text="rich reply for: q2"
    )
    expect(card_q2).to_have_count(1, timeout=10_000)
    expect(messages).to_contain_text("rich reply for: q2", timeout=10_000)
    expect(record).to_contain_text("rich reply for: q2", timeout=10_000)

    # --- Switch away and back to A again: second restore. ---
    start_new_conversation(page)
    expect(page.locator(".ui-offset-marker-card")).to_have_count(0)
    switch_to_conversation(page, "q1")

    # CRITICAL: after this SECOND restore, the transcript must contain
    # exactly the 6 original messages -- not q1's messages duplicated (or
    # misattached into q2's node) on top of q2's own. Both markers must be
    # present exactly once each, and the total message count must match.
    expect(card_q1).to_have_count(1, timeout=10_000)
    expect(card_q2).to_have_count(1, timeout=10_000)
    expect(card_q2).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
    expect(all_messages).to_have_count(6, timeout=10_000)
    expect(messages).to_contain_text("rich reply for: q1", timeout=10_000)
    expect(messages).to_contain_text("rich reply for: q2", timeout=10_000)
    expect(record).to_contain_text("rich reply for: q1", timeout=10_000)
    expect(record).to_contain_text("rich reply for: q2", timeout=10_000)
