from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    expect(page.locator(".shiny-chat-history-trigger")).to_be_visible(timeout=30_000)
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_current_starts_fresh_on_first_visit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    resume="current" starts a blank draft when there is no stored
    conversation ID (first visit — fresh browser context, empty localStorage).
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Chat transcript must be empty (no conversation restored).
    expect(page.locator(".shiny-chat-message")).to_have_count(0, timeout=10_000)

    # No conversation should be active in the drawer.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item.active")).to_have_count(
        0, timeout=10_000
    )


def test_current_restores_active_not_most_recent(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    resume="current" reopens the conversation that was *active* when the user
    left, not necessarily the most recently modified one.

    Flow:
    1. Send "hello A" → conversation A is saved and active.
    2. Start a new chat → send "hello B" → conversation B is saved and active.
    3. Switch back to conversation A from the drawer → A is now active.
    4. Reload.
    5. Conversation A should be restored (resume="current"),
       even though B was modified more recently (resume="last" would pick B).
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # --- Conversation A ---
    chat.set_user_input("hello A")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello A", timeout=30_000)

    # --- Conversation B ---
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    chat.set_user_input("hello B")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello B", timeout=30_000)

    # --- Switch back to A ---
    open_drawer(page)
    conv_a = page.locator(".shiny-chat-history-item").filter(
        has_text="hello A"
    )
    conv_a.click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    chat.expect_latest_message("echo: hello A", timeout=30_000)
    # The drawer closes client-side before history_update (with the new activeId)
    # arrives. Re-open it and confirm conv A is active so we know activeId has
    # been committed to the Redux store — and therefore localStorage — before
    # reloading.
    open_drawer(page)
    expect(
        page.locator(".shiny-chat-history-item.active").filter(has_text="hello A")
    ).to_be_visible(timeout=10_000)
    page.keyboard.press("Escape")
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    # --- Reload → should restore A, not B ---
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: hello A", timeout=30_000)


def test_current_falls_back_to_fresh_when_stored_id_is_stale(
    page: Page, local_app: ShinyAppProc
) -> None:
    """
    resume="current" starts a fresh chat when the localStorage ID points to
    a conversation that no longer exists in the store.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Create a conversation so localStorage gets a real-looking ID written.
    chat.set_user_input("hello stale")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello stale", timeout=30_000)

    # Overwrite localStorage with a non-existent ID (simulates a store that
    # was wiped while the browser retained the old pointer).
    page.evaluate('localStorage.setItem("shinychat-current:chat", "nonexistent-id-xyz")')

    # Reload — server looks up "nonexistent-id-xyz", gets None, falls back.
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(page.locator(".shiny-chat-message")).to_have_count(0, timeout=10_000)

    # No active conversation in the drawer either.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item.active")).to_have_count(
        0, timeout=10_000
    )
