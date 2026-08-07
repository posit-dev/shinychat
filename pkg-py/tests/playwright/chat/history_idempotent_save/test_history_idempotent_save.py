from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def open_drawer(page: Page) -> None:
    expect(page.locator(".shiny-chat-history-trigger")).to_be_visible(
        timeout=30_000
    )
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_restore_does_not_trigger_extra_save(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    Restoring a conversation must not trigger another managed-response save or
    change the restored transcript.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    save_count = controller.OutputTextVerbatim(page, "save_count")
    save_count.expect_value("0")

    # --- Conversation A: one exchange, one save. ---
    chat.set_user_input("first question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    save_count.expect_value("1", timeout=10_000)
    expect(message_count(page)).to_have_count(2, timeout=10_000)

    # --- Start a second conversation so there's something to switch away to. ---
    # `new_chat()` unconditionally calls `save_current()` (a real,
    # switch-triggered save of conversation A before leaving it) — that's
    # outside the idempotency guard under test, so save_count advances here.
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    save_count.expect_value("2", timeout=10_000)

    chat.set_user_input("second question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second question", timeout=30_000)
    save_count.expect_value("3", timeout=10_000)

    # --- Switch back to conversation A: this is the restore path under test. ---
    # `switch_to()` also unconditionally calls `save_current()` (saving B
    # before leaving it), then replays A's server-owned transcript.
    open_drawer(page)
    conv_a = page.locator(".shiny-chat-history-item").filter(
        has_text="first question"
    )
    conv_a.click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    save_count.expect_value("4", timeout=10_000)

    # Restored conversation must be intact: exactly the 2 original messages,
    # not truncated and not duplicated.
    expect(message_count(page)).to_have_count(2, timeout=10_000)

    # The completed restore does not settle another managed response.
    save_count.expect_value("4", timeout=5_000)

    # Re-open the drawer: still exactly 2 conversations (no phantom save
    # created a 3rd entry), and conversation A is active again.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=10_000
    )
    expect(
        page.locator(".shiny-chat-history-item.active").filter(
            has_text="first question"
        )
    ).to_be_visible(timeout=10_000)
