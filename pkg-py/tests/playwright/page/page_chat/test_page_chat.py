from __future__ import annotations

from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

TIMEOUT = 30_000


def open_page(
    page: Page,
    local_app: ShinyAppProc,
    *,
    viewport: tuple[int, int],
) -> tuple[ChatController, Locator]:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    shell = page.locator("shiny-chat-page")
    expect(shell).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat, shell


def test_desktop_navigation_streaming_and_history_auto_open(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    chat, shell = open_page(page, local_app, viewport=(1280, 800))
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    toggle = shell.locator(".shiny-chat-page-sidebar-toggle")
    toolbar_input = page.locator("#toolbar_value")

    expect(shell).to_have_attribute("data-active-page", "home")
    expect(sidebar).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toolbar_input).to_have_count(1)
    toolbar_input.fill("preserved toolbar state")

    expect(chat.loc_input).to_be_visible(timeout=TIMEOUT)
    chat.set_user_input("stream while hidden")
    chat.send_user_input()
    chat.set_user_input("preserved draft")

    shell.get_by_role("button", name="Settings").click()
    expect(shell).to_have_attribute("data-active-page", "settings")
    expect(chat.loc).to_be_hidden()
    expect(page.locator("#settings_page_input")).to_be_visible()
    expect(page.locator("#about_page_input")).to_be_hidden()
    expect(sidebar).to_have_attribute("data-sidebar-key", "page-2")
    expect(sidebar).to_be_hidden()

    toggle.click()
    expect(sidebar).to_be_visible()
    expect(page.locator("#custom_sidebar_input")).to_be_visible()
    resizer = shell.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible()
    resizer.press("End")
    expect(resizer).to_have_attribute("aria-valuenow", "920")
    resizer.press("Home")
    expect(resizer).to_have_attribute("aria-valuenow", "150")

    chat.expect_latest_message("echo: stream while hidden", timeout=TIMEOUT)
    shell.get_by_role("button", name="Return to chat").click()
    expect(chat.loc).to_be_visible()
    chat.expect_user_input("preserved draft")
    expect(toolbar_input).to_have_value("preserved toolbar state")
    expect(toolbar_input).to_have_count(1)

    # The first empty history snapshot decides auto-open once. Saving the new
    # conversation later must not override that decision.
    expect(sidebar).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    shell.get_by_role("button", name="History", exact=True).click()
    expect(shell).to_have_attribute("data-active-page", "history")
    expect(sidebar).to_have_attribute("data-sidebar-key", "default")
    expect(sidebar).to_be_hidden()

    shell.get_by_role("button", name="About").click()
    expect(shell).to_have_attribute("data-active-page", "about")
    assert sidebar.get_attribute("data-sidebar-key") is None
    expect(sidebar).to_be_hidden()
    expect(toggle).to_be_hidden()

    shell.get_by_role("button", name="Return to chat").click()
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )
    page.wait_for_function(
        "localStorage.getItem('shinychat-current:chat') !== null"
    )
    page.reload()
    expect(shell).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(sidebar).to_be_visible(timeout=TIMEOUT)
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )
    chat.expect_latest_message("echo: stream while hidden", timeout=TIMEOUT)


def test_mobile_moves_controls_and_manages_dialog_focus(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, shell = open_page(page, local_app, viewport=(390, 760))
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    toggle = shell.locator(".shiny-chat-page-sidebar-toggle")
    controls = shell.locator(".shiny-chat-page-controls")

    expect(controls).to_have_count(1)
    expect(
        shell.locator(
            ".shiny-chat-page-controls-mount-mobile > .shiny-chat-page-controls"
        )
    ).to_have_count(1)
    expect(page.locator("#toolbar_value")).to_have_count(1)
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    expect(shell).to_have_attribute("data-mobile-menu-open", "true")
    expect(sidebar).to_have_attribute("role", "dialog")
    expect(sidebar).to_have_attribute("aria-modal", "true")
    expect(sidebar).to_be_focused()

    page.keyboard.press("Tab")
    expect(shell.get_by_role("button", name="Close app menu")).to_be_focused()
    page.keyboard.press("Escape")
    expect(shell).not_to_have_attribute("data-mobile-menu-open", "true")
    expect(toggle).to_be_focused()

    toggle.click()
    shell.get_by_role("button", name="About").click()
    expect(shell).to_have_attribute("data-active-page", "about")
    expect(shell).not_to_have_attribute("data-mobile-menu-open", "true")
    expect(toggle).to_be_focused()
    expect(toggle).not_to_be_disabled()

    # A page without a sidebar still retains the mobile app menu because it
    # owns navigation and toolbar controls.
    toggle.click()
    expect(shell).to_have_attribute("data-mobile-menu-open", "true")
    assert sidebar.get_attribute("data-sidebar-key") is None
    shell.locator(".shiny-chat-page-sidebar-scrim").click(
        position={"x": 380, "y": 100}
    )
    expect(shell).not_to_have_attribute("data-mobile-menu-open", "true")
    expect(toggle).to_be_focused()

    toggle.click()
    shell.get_by_role("button", name="Pinned").click()
    expect(shell).to_have_attribute("data-active-page", "pinned")
    expect(toggle).not_to_be_disabled()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    expect(shell).to_have_attribute("data-mobile-menu-open", "true")
    expect(toggle).to_have_attribute("aria-expanded", "true")


def test_reduced_motion_disables_mobile_sidebar_transition(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    _, shell = open_page(page, local_app, viewport=(390, 760))
    sidebar = shell.locator(".shiny-chat-page-sidebar")

    expect(sidebar).to_have_css("transition-duration", "0s")
