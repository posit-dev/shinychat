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


def wait_for_save_count_to_settle(page: Page) -> str:
    """
    Wait until `save_count` stops changing, then return its final value.

    Each turn in this app appends a message twice (the non-streamed rich-UI
    card, then the streamed echo reply), and each client re-report of its
    message snapshot fires a save -- so the exact count after a turn isn't a
    fixed, predictable number. This just needs a reliable "the save(s)
    landed" sync point before switching conversations, not an exact count.
    """
    loc = page.locator("pre#save_count.shiny-text-output")
    last = loc.inner_text()
    while True:
        page.wait_for_timeout(500)
        current = loc.inner_text()
        if current == last:
            return current
        last = current


def test_new_turn_ui_survives_second_restore(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Regression test for a stale `ui_offset` after `replay_ui`.

    `replay_ui` used to seed `self.ui_offset` from
    `len(self.chat._messages_for_bookmark())`, which reads the
    client-reported `${id}_messages` input -- an async, browser-driven
    snapshot that (immediately after the synchronous restore loop) still
    reflects the *previous* conversation, not the one just restored. That
    stale offset makes `extend_record_linear` re-slice UI messages from index
    0 instead of from the true restore point, so the next turn's node (and
    all subsequent nodes) end up re-absorbing every earlier message on top of
    their own: `node.ui` for the new turn is polluted with duplicated copies
    of prior turns' messages (including a prior turn's plain user message
    misattached into what should be a purely-assistant node), rather than
    holding just that turn's own UI.

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

    # --- Conversation A, turn 1: rich reply with marker #1. ---
    chat.set_user_input("q1")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: q1", timeout=30_000)
    card_q1 = page.locator(
        ".ui-offset-marker-card", has_text="rich reply for: q1"
    )
    expect(card_q1).to_have_count(1, timeout=10_000)
    wait_for_save_count_to_settle(page)

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
    wait_for_save_count_to_settle(page)

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
