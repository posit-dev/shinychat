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
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"echo: {text}", timeout=30_000)


def inject_url_tracker(page: Page) -> None:
    """Instrument history.replaceState so we can count URL changes."""
    page.evaluate("""
        window._stateIdChanges = [];
        const orig = history.replaceState.bind(history);
        history.replaceState = function(state, title, url) {
            if (url && url.includes('_state_id_=')) {
                const m = url.match(/_state_id_=([^&]+)/);
                if (m) window._stateIdChanges.push(m[1]);
            }
            return orig(state, title, url);
        };
    """)


def get_url_changes(page: Page) -> list[str]:
    result = page.evaluate("window._stateIdChanges || []")
    return list(result)


def test_url_state_id_single_update_per_response(
    page: Page, local_app: ShinyAppProc
) -> None:
    """When ClientWithState + enable_bookmarking() precede enable_history(restore_mode=
    'url'), BookmarkMinter must be the sole source of URL updates after a response.
    Without the fix, enable_bookmarking(bookmark_on='response') fires a second
    session.bookmark() call, producing two replaceState calls per response.
    With the fix, only one replaceState happens."""
    page.goto(local_app.url)
    inject_url_tracker(page)

    start_conversation(page, "first message")

    # Wait for BookmarkMinter to update the URL.
    page.wait_for_url(lambda url: "_state_id_=" in url, timeout=10_000)

    # Allow any extra async activity to settle.
    page.wait_for_timeout(500)

    changes = get_url_changes(page)
    # Exactly one URL update: from BookmarkMinter. A double-mint produces two.
    assert len(changes) == 1, f"Expected 1 URL update, got {len(changes)}: {changes}"


def test_url_mode_with_state_reload_restores_conversation(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Reload must restore both the chat transcript and the bookmarked input value
    even when ClientWithState and enable_bookmarking() are both active."""
    page.goto(local_app.url)

    controller.InputText(page, "filter_text").set("gentoo")
    start_conversation(page, "reload me")
    page.wait_for_url(lambda url: "_state_id_=" in url, timeout=10_000)

    page.reload()

    controller.InputText(page, "filter_text").expect_value("gentoo", timeout=30_000)
    ChatController(page, "chat").expect_latest_message(
        "echo: reload me", timeout=30_000
    )
