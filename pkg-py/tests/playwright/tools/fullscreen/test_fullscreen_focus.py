"""Tests for fullscreen tool card focus management."""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _add_tool_result(page: Page) -> None:
    """Click the button to add a tool result card and wait for it to appear."""
    page.click("#add_tool")
    expect(page.locator(".shiny-tool-result")).to_be_visible(timeout=10_000)


def _enter_fullscreen(page: Page) -> None:
    """Click the fullscreen toggle to enter fullscreen mode."""
    page.locator(".tool-fullscreen-toggle").click()
    expect(page.locator(".shiny-tool-card[fullscreen]")).to_be_visible(
        timeout=5_000
    )


def test_fullscreen_enter_creates_overlay(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Entering fullscreen should create a backdrop and close button."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    expect(page.locator(".shiny-tool-fullscreen-backdrop")).to_be_attached()
    expect(page.locator(".shiny-tool-fullscreen-exit")).to_be_attached()


def test_fullscreen_escape_exits(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Pressing Escape should exit fullscreen mode."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    page.keyboard.press("Escape")

    expect(page.locator(".shiny-tool-card[fullscreen]")).not_to_be_attached(
        timeout=5_000
    )
    expect(page.locator(".shiny-tool-fullscreen-backdrop")).not_to_be_attached()
    expect(page.locator(".shiny-tool-fullscreen-exit")).not_to_be_attached()


def test_fullscreen_close_button_click(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Clicking the close button should exit fullscreen mode."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    page.locator(".shiny-tool-fullscreen-exit").click()

    expect(page.locator(".shiny-tool-card[fullscreen]")).not_to_be_attached(
        timeout=5_000
    )


def test_fullscreen_card_receives_focus(
    page: Page, local_app: ShinyAppProc
) -> None:
    """The card should receive focus when entering fullscreen."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    card = page.locator(".shiny-tool-card[fullscreen]")
    expect(card).to_be_focused(timeout=5_000)


def test_fullscreen_tab_reaches_close_button(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Pressing Tab from within the fullscreen card should reach the close button."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    # The card should have focus after entering fullscreen
    card = page.locator(".shiny-tool-card[fullscreen]")
    expect(card).to_be_focused(timeout=5_000)

    # Tab should eventually reach the close button
    close_btn = page.locator(".shiny-tool-fullscreen-exit")
    for _ in range(10):
        page.keyboard.press("Tab")
        if close_btn.evaluate("el => el === document.activeElement"):
            break
    expect(close_btn).to_be_focused()


def test_fullscreen_shift_tab_reaches_close_button(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Pressing Shift+Tab from the card should reach the close button."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    card = page.locator(".shiny-tool-card[fullscreen]")
    expect(card).to_be_focused(timeout=5_000)

    # Shift+Tab from the card should go to close button
    page.keyboard.press("Shift+Tab")
    close_btn = page.locator(".shiny-tool-fullscreen-exit")
    expect(close_btn).to_be_focused()


def test_fullscreen_focus_cycles(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Focus should cycle between card elements and close button, never escaping."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _add_tool_result(page)
    _enter_fullscreen(page)

    card = page.locator(".shiny-tool-card[fullscreen]")
    expect(card).to_be_focused(timeout=5_000)

    # Press Tab many times — focus should never leave the card + close button
    for i in range(20):
        page.keyboard.press("Tab")
        info = page.evaluate(
            """() => {
                const active = document.activeElement;
                const card = document.querySelector('.shiny-tool-card[fullscreen]');
                const closeBtn = document.querySelector('.shiny-tool-fullscreen-exit');
                const inCard = card?.contains(active) || active === card;
                const isClose = active === closeBtn;
                return {
                    ok: inCard || isClose,
                    tag: active?.tagName,
                    className: active?.className,
                    id: active?.id,
                    inCard,
                    isClose,
                };
            }"""
        )
        assert info["ok"], (
            f"Tab {i + 1}: Focus escaped! "
            f"tag={info['tag']}, class={info['className']}, id={info['id']}"
        )
