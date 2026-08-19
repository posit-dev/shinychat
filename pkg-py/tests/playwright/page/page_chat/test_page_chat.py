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
    expect(toggle).to_be_disabled()
    expect(toggle).to_have_attribute("aria-expanded", "false")

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


def test_desktop_header_keeps_controls_available_with_a_long_title(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, shell = open_page(page, local_app, viewport=(800, 760))
    header = shell.locator(".shiny-chat-page-header")
    identity_title = shell.locator(".shiny-chat-page-identity-title")
    controls_mount = shell.locator(".shiny-chat-page-controls-mount-desktop")
    toolbar_sources = shell.locator(".shiny-chat-page-toolbar-sources")
    toolbar_source = toolbar_sources.locator(
        ".shiny-chat-page-toolbar-source"
    ).first
    toolbar_input = page.locator("#toolbar_value")

    identity_title.evaluate(
        """element => {
            element.textContent = "A page chat title long enough to test header overflow";
        }"""
    )

    expect(shell.get_by_role("button", name="Settings")).to_be_visible()
    expect(toolbar_input).to_be_visible()
    toolbar_box = toolbar_input.bounding_box()
    identity_title_box = identity_title.bounding_box()
    assert toolbar_box is not None
    assert identity_title_box is not None
    assert identity_title_box["width"] >= 150
    assert toolbar_box["x"] > identity_title_box["x"]
    expect(controls_mount).to_have_css("overflow-x", "visible")
    expect(toolbar_sources).to_be_hidden()
    expect(toolbar_source).to_be_hidden()


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


def test_page_toolbars_move_without_duplicate_controls(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, shell = open_page(page, local_app, viewport=(1280, 800))
    toolbar = shell.locator(".shiny-chat-page-toolbar")
    toolbar_sources = shell.locator(".shiny-chat-page-toolbar-sources")
    home_input = page.locator("#toolbar_value")
    settings_input = page.locator("#settings_toolbar_value")

    expect(toolbar.locator("#toolbar_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(toolbar_sources).to_be_hidden()
    expect(page.locator("#toolbar_value")).to_have_count(1)
    expect(page.locator("#settings_toolbar_value")).to_have_count(1)
    home_input.fill("home toolbar state")

    shell.get_by_role("button", name="History", exact=True).click()
    expect(shell).to_have_attribute("data-active-page", "history")
    expect(toolbar.locator("#toolbar_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(page.locator("#toolbar_value")).to_have_count(1)
    expect(home_input).to_have_value("home toolbar state")

    shell.get_by_role("button", name="Settings").click()
    expect(shell).to_have_attribute("data-active-page", "settings")
    expect(toolbar.locator("#settings_toolbar_value")).to_have_count(1)
    expect(toolbar.locator("#toolbar_value")).to_have_count(0)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(home_input).to_have_count(1)
    expect(settings_input).to_have_count(1)
    settings_input.fill("settings toolbar state")

    shell.get_by_role("button", name="About").click()
    expect(shell).to_have_attribute("data-active-page", "about")
    expect(toolbar.locator("input")).to_have_count(0)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(0)
    expect(home_input).to_have_count(1)
    expect(settings_input).to_have_count(1)

    shell.get_by_role("button", name="Return to chat").click()
    expect(toolbar.locator("#toolbar_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(home_input).to_have_value("home toolbar state")
    expect(settings_input).to_have_value("settings toolbar state")
    expect(shell.locator(".shiny-chat-page-toolbar-content")).to_have_count(2)

    page.set_viewport_size({"width": 390, "height": 760})
    expect(
        shell.locator(
            ".shiny-chat-page-controls-mount-mobile "
            ".shiny-chat-page-toolbar #toolbar_value"
        )
    ).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    toggle = shell.locator(".shiny-chat-page-sidebar-toggle")
    toggle.click()
    shell.get_by_role("button", name="Settings").click()
    expect(
        shell.locator(
            ".shiny-chat-page-controls-mount-mobile "
            ".shiny-chat-page-toolbar #settings_toolbar_value"
        )
    ).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(settings_input).to_have_value("settings toolbar state")
    expect(page.locator("#settings_toolbar_value")).to_have_count(1)


def test_reduced_motion_disables_mobile_sidebar_transition(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    _, shell = open_page(page, local_app, viewport=(390, 760))
    sidebar = shell.locator(".shiny-chat-page-sidebar")

    expect(sidebar).to_have_css("transition-duration", "0s")
