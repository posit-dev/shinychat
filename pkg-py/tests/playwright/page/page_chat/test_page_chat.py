from __future__ import annotations

from math import ceil

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController, PageChatController

TIMEOUT = 30_000


def open_page(
    page: Page,
    local_app: ShinyAppProc,
    *,
    viewport: tuple[int, int],
) -> tuple[ChatController, PageChatController]:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    page_chat = PageChatController(page, "chat")
    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat, page_chat


def test_desktop_navigation_streaming_and_history_auto_open(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    chat, page_chat = open_page(page, local_app, viewport=(1280, 800))
    sidebar = page_chat.loc_sidebar
    toggle = page_chat.loc_sidebar_toggle
    toolbar_input = page.locator("#toolbar_value")
    toolbar_global_input = page.locator("#toolbar_global_value")

    page_chat.expect_active_page("__home__")
    expect(page_chat.loc_header).to_have_css("min-height", "52px")
    expect(sidebar).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toolbar_input).to_have_count(1)
    expect(toolbar_global_input).to_have_count(1)
    toolbar_input.fill("preserved toolbar state")
    toolbar_global_input.fill("preserved global toolbar state")

    expect(chat.loc_input).to_be_visible(timeout=TIMEOUT)
    chat.set_user_input("stream while hidden")
    chat.send_user_input()
    chat.set_user_input("preserved draft")

    page_chat.select_page("Settings")
    page_chat.expect_active_page("settings")
    expect(chat.loc).to_be_hidden()
    expect(page.locator("#settings_page_input")).to_be_visible()
    expect(page.locator("#about_page_input")).to_be_hidden()
    expect(sidebar).to_have_attribute("data-sidebar-key", "page-2")
    expect(sidebar).to_be_hidden()

    toggle.click()
    expect(sidebar).to_be_visible()
    expect(page.locator("#custom_sidebar_input")).to_be_visible()
    resizer = page_chat.loc.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible()
    resizer.press("End")
    expect(resizer).to_have_attribute("aria-valuenow", "920")
    resizer.press("Home")
    expect(resizer).to_have_attribute("aria-valuenow", "150")

    chat.expect_latest_message("echo: stream while hidden", timeout=TIMEOUT)
    page_chat.return_home()
    expect(chat.loc).to_be_visible()
    chat.expect_user_input("preserved draft")
    expect(toolbar_input).to_have_value("preserved toolbar state")
    expect(toolbar_global_input).to_have_value("preserved global toolbar state")
    expect(toolbar_input).to_have_count(1)
    expect(toolbar_global_input).to_have_count(1)

    # The first empty history snapshot decides auto-open once. Saving the new
    # conversation later must not override that decision.
    expect(sidebar).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    page_chat.select_page("History", exact=True)
    page_chat.expect_active_page("history")
    expect(sidebar).to_have_attribute("data-sidebar-key", "default")
    expect(sidebar).to_be_hidden()

    page_chat.select_page("About")
    page_chat.expect_active_page("about")
    assert sidebar.get_attribute("data-sidebar-key") is None
    expect(sidebar).to_be_hidden()
    expect(toggle).to_be_disabled()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    page_chat.return_home()
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )
    page.wait_for_function(
        "localStorage.getItem('shinychat-current:chat') !== null"
    )
    page.reload()
    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(sidebar).to_be_visible(timeout=TIMEOUT)
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )
    chat.expect_latest_message("echo: stream while hidden", timeout=TIMEOUT)


def test_explicit_theme_keeps_embedded_chat_composer_chrome(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 800, "height": 760})
    page.goto(f"{local_app.url}?standard_theme=true")
    chat = ChatController(page, "chat")
    composer = chat.loc.locator(".shiny-chat-input .tiptap")
    input_area = chat.loc.locator(".shiny-chat-input")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    page_chat = PageChatController(page, "chat")

    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(composer).to_have_css("border-radius", "26px")
    expect(wrapper).to_have_css("padding-left", "4px")
    expect(input_area).to_have_css("padding-bottom", "4px")

    page_chat.loc.evaluate(
        """(element) => {
          element.style.setProperty('--shiny-chat-page-fill-padding', '2rem');
          element.style.setProperty(
            '--shiny-chat-page-input-padding-bottom',
            '3rem',
          );
        }"""
    )
    expect(wrapper).to_have_css("padding-left", "32px")
    expect(input_area).to_have_css("padding-bottom", "48px")


def test_page_chat_footer_aligns_with_the_composer(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app, viewport=(800, 760))
    input_area = chat.loc.locator(".shiny-chat-input")
    input_editor = input_area.locator(".tiptap")
    footer = chat.loc.locator(".shiny-chat-footer")
    footer_content = chat.loc.locator(".page-chat-footer")

    expect(input_area).to_have_css("padding-bottom", "16px")
    expect(footer).to_have_css("padding-left", "0px")
    expect(footer).to_have_css("margin-top", "-12px")
    expect(footer).to_have_css("padding-bottom", "16px")

    input_box = input_editor.bounding_box()
    footer_box = footer_content.bounding_box()
    assert input_box is not None
    assert footer_box is not None
    assert footer_box["x"] == pytest.approx(input_box["x"], abs=1)
    assert footer_box["y"] - (
        input_box["y"] + input_box["height"]
    ) == pytest.approx(8, abs=1)


@pytest.mark.parametrize(
    "title, is_long_title",
    [
        pytest.param("Short title", False, id="short-title"),
        pytest.param(
            "A page chat title long enough to test header overflow",
            True,
            id="long-title",
        ),
    ],
)
def test_desktop_header_keeps_controls_available(
    page: Page,
    local_app: ShinyAppProc,
    title: str,
    is_long_title: bool,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(800, 760))
    header = page_chat.loc_header
    identity = page_chat.loc_identity
    identity_title = page_chat.loc_identity_title
    controls_mount = page_chat.loc_controls_mount_desktop
    toolbar = page_chat.loc_toolbar
    toolbar_sources = page_chat.loc.locator(".shiny-chat-page-toolbar-sources")
    toolbar_source = toolbar_sources.locator(
        ".shiny-chat-page-toolbar-source"
    ).first
    toolbar_input = page.locator("#toolbar_value")

    identity_title.evaluate(
        "(element, value) => { element.textContent = value; }",
        title,
    )

    expect(page_chat.loc.get_by_role("button", name="Settings")).to_be_visible()
    expect(toolbar_input).to_be_visible()
    header_box = header.bounding_box()
    identity_box = identity.bounding_box()
    identity_title_box = identity_title.bounding_box()
    controls_mount_box = controls_mount.bounding_box()
    toolbar_box = toolbar.bounding_box()
    toolbar_input_box = toolbar_input.bounding_box()
    assert header_box is not None
    assert identity_box is not None
    assert identity_title_box is not None
    assert controls_mount_box is not None
    assert toolbar_box is not None
    assert toolbar_input_box is not None

    title_cap_px = page.evaluate(
        "12 * parseFloat(getComputedStyle(document.documentElement).fontSize)"
    )
    header_right = header_box["x"] + header_box["width"]
    controls_mount_right = controls_mount_box["x"] + controls_mount_box["width"]
    identity_title_right = identity_title_box["x"] + identity_title_box["width"]
    toolbar_right = toolbar_box["x"] + toolbar_box["width"]
    toolbar_input_right = toolbar_input_box["x"] + toolbar_input_box["width"]

    assert identity_box["width"] <= title_cap_px
    if is_long_title:
        assert identity_title_box["width"] >= 150
    else:
        assert identity_box["width"] < title_cap_px
    assert identity_title_right <= toolbar_box["x"]
    assert toolbar_box["x"] >= controls_mount_box["x"]
    assert toolbar_right <= controls_mount_right
    assert toolbar_box["x"] >= header_box["x"]
    assert toolbar_right <= header_right
    assert toolbar_input_box["x"] >= controls_mount_box["x"]
    assert toolbar_input_right <= controls_mount_right
    assert toolbar_input_box["x"] >= header_box["x"]
    assert toolbar_input_right <= header_right

    expect(controls_mount).to_have_css("overflow-x", "visible")
    expect(toolbar_sources).to_be_hidden()
    expect(toolbar_source).to_be_hidden()


def test_single_page_title_is_not_truncated(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 800, "height": 760})
    page.goto(f"{local_app.url}?single=true")
    page_chat = PageChatController(page, "chat")
    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)

    identity = page_chat.loc_identity
    identity_title = page_chat.loc_identity_title
    header = page_chat.loc_header
    controls_mount = page_chat.loc_controls_mount_desktop
    toolbar = page_chat.loc_toolbar
    main = page_chat.loc_main
    expect(identity).to_have_count(1)
    expect(identity).to_have_attribute("class", "shiny-chat-page-identity")
    expect(identity).not_to_have_attribute("data-page-home")
    expect(identity_title).to_have_css("overflow", "visible")
    expect(identity_title).to_have_css("text-overflow", "clip")
    expect(identity_title).to_have_css("white-space", "normal")

    identity_title.evaluate(
        "(element) => { element.textContent = 'A title with a deliberately "
        "unusually long unbroken run of characters that must wrap without "
        "pushing toolbar controls outside the page'; }"
    )
    identity_box = identity.bounding_box()
    header_box = header.bounding_box()
    controls_mount_box = controls_mount.bounding_box()
    toolbar_box = toolbar.bounding_box()
    main_box = main.bounding_box()
    shell_box = page_chat.loc.bounding_box()
    assert identity_box is not None
    assert header_box is not None
    assert controls_mount_box is not None
    assert toolbar_box is not None
    assert main_box is not None
    assert shell_box is not None
    title_cap_px = page.evaluate(
        "12 * parseFloat(getComputedStyle(document.documentElement).fontSize)"
    )
    assert identity_box["width"] > title_cap_px
    assert identity_box["x"] + identity_box["width"] <= toolbar_box["x"]
    assert toolbar_box["x"] >= controls_mount_box["x"]
    assert toolbar_box["x"] + toolbar_box["width"] <= (
        header_box["x"] + header_box["width"]
    )
    assert header_box["height"] > 52
    assert main_box["y"] == pytest.approx(
        header_box["y"] + header_box["height"], abs=1
    )
    assert main_box["y"] + main_box["height"] == pytest.approx(
        shell_box["y"] + shell_box["height"], abs=1
    )


def test_identity_tooltip_discloses_title_and_return_action(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 800, "height": 760})
    page.goto(f"{local_app.url}?long_title=true")
    page_chat = PageChatController(page, "chat")
    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)

    identity = page_chat.loc_identity
    title = "Research Assistant for long-running analyses and multi-step investigations"
    updated_title = f"Updated {title}"
    tooltip = page.get_by_role("tooltip")

    identity.locator(".shiny-chat-page-identity-title").evaluate(
        "(element, value) => { element.textContent = value; }",
        updated_title,
    )
    identity.hover()
    expect(tooltip).to_have_text(updated_title)

    page_chat.select_page("Settings")
    expect(tooltip).not_to_be_visible()
    identity.hover()
    expect(tooltip).to_contain_text("Return to chat")
    expect(tooltip).to_contain_text(updated_title)
    expect(tooltip.locator("br")).to_have_count(1)

    identity.click()
    identity.hover()
    expect(tooltip).to_have_text(updated_title)


def test_mobile_moves_controls_and_manages_dialog_focus(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(390, 760))
    sidebar = page_chat.loc_sidebar
    toggle = page_chat.loc_sidebar_toggle
    controls = page_chat.loc_controls

    expect(controls).to_have_count(1)
    expect(
        page_chat.loc_controls_mount_mobile.locator(
            "> .shiny-chat-page-controls"
        )
    ).to_have_count(1)
    expect(page.locator("#toolbar_value")).to_have_count(1)
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    page_chat.expect_mobile_menu_open()
    expect(sidebar).to_have_attribute("role", "dialog")
    expect(sidebar).to_have_attribute("aria-modal", "true")
    expect(sidebar).to_be_focused()
    close_button = page_chat.loc.get_by_role("button", name="Close app menu")
    expect(close_button).to_be_visible()
    expect(close_button).to_have_css("position", "absolute")
    expect(close_button).to_have_css("top", "8px")
    expect(close_button).to_have_css("right", "8px")
    expect(close_button).to_have_css("place-items", "center")
    close_icon = close_button.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::before");
          return {
            content: style.content,
            width: style.width,
            height: style.height,
            backgroundColor: style.backgroundColor,
          };
        }"""
    )
    assert close_icon["content"] == '""'
    assert close_icon["width"] == "18px"
    assert close_icon["height"] == "2px"
    assert close_icon["backgroundColor"] != "rgba(0, 0, 0, 0)"

    page.keyboard.press("Tab")
    expect(close_button).to_be_focused()
    page.keyboard.press("Escape")
    page_chat.expect_mobile_menu_closed()
    expect(toggle).to_be_focused()

    toggle.click()
    page_chat.select_page("About")
    page_chat.expect_active_page("about")
    page_chat.expect_mobile_menu_closed()
    expect(toggle).to_be_focused()
    expect(toggle).not_to_be_disabled()

    # A page without a sidebar still retains the mobile app menu because it
    # owns navigation and toolbar controls.
    toggle.click()
    page_chat.expect_mobile_menu_open()
    assert sidebar.get_attribute("data-sidebar-key") is None
    page_chat.loc.locator(".shiny-chat-page-sidebar-scrim").click(
        position={"x": 380, "y": 100}
    )
    page_chat.expect_mobile_menu_closed()
    expect(toggle).to_be_focused()

    toggle.click()
    page_chat.select_page("Pinned")
    page_chat.expect_active_page("pinned")
    expect(toggle).not_to_be_disabled()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    page_chat.expect_mobile_menu_open()
    expect(toggle).to_have_attribute("aria-expanded", "true")


def test_sidebarless_page_hides_desktop_toggle_and_keeps_mobile_app_menu(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{local_app.url}?sidebarless=true")
    page_chat = PageChatController(page, "chat")
    toggle = page_chat.loc_sidebar_toggle

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(toggle).to_be_hidden()

    page.set_viewport_size({"width": 390, "height": 760})

    expect(toggle).to_be_visible()
    expect(toggle).not_to_be_disabled()
    toggle.click()
    page_chat.expect_mobile_menu_open()
    expect(page_chat.loc.get_by_role("button", name="About")).to_be_visible()
    expect(page.locator("#sidebarless_toolbar")).to_be_visible()


def test_mobile_menu_remains_available_for_navigation_controls_only(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(f"{local_app.url}?controls_only=true")
    page_chat = PageChatController(page, "chat")
    toggle = page_chat.loc_sidebar_toggle

    expect(toggle).to_be_visible()
    toggle.click()
    page_chat.expect_mobile_menu_open()
    action = page.locator("#controls_only_action")
    expect(action).to_be_visible()
    action.click()


def test_desktop_dropdown_navigation_is_clickable_and_closes_after_selection(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{local_app.url}?crowded_dropdown=true")
    page_chat = PageChatController(page, "chat")
    menu = page_chat.loc.locator(".shiny-chat-page-nav-menu")
    nav = page_chat.loc_nav
    details = menu.locator(".shiny-chat-page-nav-link")

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(nav).to_have_css("overflow-x", "auto")
    assert nav.evaluate(
        "(element) => element.scrollWidth > element.clientWidth"
    )
    menu.scroll_into_view_if_needed()
    details.evaluate(
        """(element) => {
          element.textContent = `Details ${"very long ".repeat(200)}`;
        }"""
    )
    menu.locator("summary").click()
    expect(menu).to_have_attribute("open", "")
    expect(details).to_be_visible()
    menu_items = menu.locator(".shiny-chat-page-nav-menu-items")
    page.wait_for_function(
        """(element) => {
          const bounds = element.getBoundingClientRect();
          return bounds.left >= 0 && bounds.right <= window.innerWidth;
        }""",
        arg=menu_items.element_handle(),
    )

    details_box = details.bounding_box()
    menu_items_box = menu_items.bounding_box()
    assert details_box is not None
    assert menu_items_box is not None
    assert menu_items_box["x"] >= 0
    assert menu_items_box["x"] + menu_items_box["width"] <= 1280
    assert menu_items_box["width"] == pytest.approx(1264, abs=1)
    hit_target = page.evaluate(
        """({ x, y }) => document.elementFromPoint(x, y)?.textContent""",
        {
            "x": details_box["x"] + details_box["width"] / 2,
            "y": details_box["y"] + details_box["height"] / 2,
        },
    )
    assert hit_target is not None
    assert "Details" in hit_target

    details.click()
    page_chat.expect_active_page("details")
    expect(page.locator("#dropdown_details_page")).to_be_visible()
    expect(menu).not_to_have_attribute("open", "")
    expect(menu.locator("summary")).to_be_focused()


def test_mobile_dropdown_navigation_remains_in_the_app_menu(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(f"{local_app.url}?dropdown=true")
    page_chat = PageChatController(page, "chat")
    toggle = page_chat.loc_sidebar_toggle
    menu = page_chat.loc.locator(".shiny-chat-page-nav-menu")

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    toggle.click()
    menu.locator("summary").click()
    expect(menu.locator(".shiny-chat-page-nav-menu-items")).to_have_css(
        "position", "static"
    )
    expect(menu.get_by_role("button", name="Details")).to_be_visible()


def test_desktop_dropdown_navigation_aligns_in_rtl(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{local_app.url}?dropdown=true")
    page_chat = PageChatController(page, "chat")
    menu = page_chat.loc.locator(".shiny-chat-page-nav-menu")
    summary = menu.locator("summary")
    items = menu.locator(".shiny-chat-page-nav-menu-items")

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    page.locator("html").evaluate("(element) => { element.dir = 'rtl' }")
    summary.click()
    page.wait_for_function(
        """(element) => {
          const summary = element.parentElement?.querySelector(
            ':scope > summary',
          );
          if (!summary) return false;
          return Math.abs(
            element.getBoundingClientRect().right -
              summary.getBoundingClientRect().right,
          ) <= 1;
        }""",
        arg=items.element_handle(),
    )
    summary_box = summary.bounding_box()
    items_box = items.bounding_box()
    assert summary_box is not None
    assert items_box is not None
    assert items_box["x"] + items_box["width"] == pytest.approx(
        summary_box["x"] + summary_box["width"], abs=1
    )


def test_open_mobile_dropdown_repositions_after_desktop_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(f"{local_app.url}?dropdown=true")
    page_chat = PageChatController(page, "chat")
    menu = page_chat.loc.locator(".shiny-chat-page-nav-menu")

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    page_chat.loc_sidebar_toggle.click()
    menu.locator("summary").click()
    expect(menu.locator(".shiny-chat-page-nav-menu-items")).to_have_css(
        "position", "static"
    )

    page.set_viewport_size({"width": 1280, "height": 800})
    expect(menu.locator(".shiny-chat-page-nav-menu-items")).to_have_css(
        "position", "fixed"
    )
    items_box = menu.locator(".shiny-chat-page-nav-menu-items").bounding_box()
    assert items_box is not None
    assert items_box["x"] >= 0
    assert items_box["x"] + items_box["width"] <= 1280


def test_sidebarless_mobile_history_trigger_does_not_overlay_messages(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(f"{local_app.url}?sidebarless=true")
    chat = ChatController(page, "chat")
    page_chat = PageChatController(page, "chat")
    trigger = chat.loc.locator(".shiny-chat-history-trigger")

    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(trigger).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc.locator(".shiny-chat-messages")).to_have_css(
        "padding-top", "48px"
    )

    chat.set_user_input("history spacing")
    chat.send_user_input()
    chat.expect_latest_message(
        "echo: history spacing",
        timeout=TIMEOUT,
    )

    trigger_box = trigger.bounding_box()
    message_box = chat.loc.locator(
        ".shiny-chat-user-message"
    ).first.bounding_box()
    assert trigger_box is not None
    assert message_box is not None
    assert message_box["y"] >= trigger_box["y"] + trigger_box["height"]


@pytest.mark.parametrize(
    "viewport",
    [
        pytest.param((1280, 800), id="desktop"),
        pytest.param((390, 760), id="mobile"),
    ],
)
def test_page_chat_keeps_content_inset_and_fills_its_page_region(
    page: Page,
    local_app: ShinyAppProc,
    viewport: tuple[int, int],
) -> None:
    chat, page_chat = open_page(page, local_app, viewport=viewport)
    main = page_chat.loc_main
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    shell_box = page_chat.loc.bounding_box()
    header_box = page_chat.loc_header.bounding_box()
    main_box = main.bounding_box()
    chat_box = chat.loc.bounding_box()
    wrapper_box = wrapper.bounding_box()
    input_box = chat.loc_input_container.bounding_box()
    assert shell_box is not None
    assert header_box is not None
    assert main_box is not None
    assert chat_box is not None
    assert wrapper_box is not None
    assert input_box is not None

    assert shell_box["height"] == pytest.approx(viewport[1], abs=1)
    assert main_box["y"] == pytest.approx(
        header_box["y"] + header_box["height"], abs=1
    )
    assert main_box["y"] + main_box["height"] == pytest.approx(
        shell_box["y"] + shell_box["height"], abs=1
    )
    assert chat_box["height"] == pytest.approx(main_box["height"], abs=1)
    assert chat_box["y"] == pytest.approx(main_box["y"], abs=1)
    assert wrapper_box["height"] == pytest.approx(chat_box["height"], abs=1)
    assert input_box["x"] >= chat_box["x"] + 16
    assert (
        input_box["x"] + input_box["width"]
        <= chat_box["x"] + chat_box["width"] - 16
    )
    assert input_box["y"] < chat_box["y"] + chat_box["height"] * 0.75
    expect(wrapper).to_have_css("padding-left", "16px")
    expect(wrapper).to_have_css("padding-right", "16px")


def test_page_chat_centers_fitting_greeting_composer_and_pins_overflow(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app, viewport=(1280, 800))
    layout = chat.loc.locator(".shiny-chat-layout")
    greeting = chat.loc_greeting
    composer = chat.loc.locator(".shiny-chat-composer")
    footer = chat.loc.locator(".page-chat-footer")

    expect(layout).to_have_attribute("data-composer-centered", "")
    expect(layout).not_to_have_attribute("data-composer-revealing")
    expect(layout).not_to_have_attribute("data-composer-resizing")
    greeting_box = greeting.bounding_box()
    composer_box = composer.bounding_box()
    footer_box = footer.bounding_box()
    assert greeting_box is not None
    assert composer_box is not None
    assert footer_box is not None
    assert composer_box["y"] >= greeting_box["y"] + greeting_box["height"]
    assert (
        composer_box["y"] - (greeting_box["y"] + greeting_box["height"]) <= 16
    )
    assert footer_box["y"] >= composer_box["y"]
    group_center = (
        greeting_box["y"] + composer_box["y"] + composer_box["height"]
    ) / 2
    chat_box = chat.loc.bounding_box()
    assert chat_box is not None
    assert group_center == pytest.approx(
        chat_box["y"] + chat_box["height"] / 2, abs=8
    )

    chat.set_user_input("Move the composer")
    chat.send_user_input()
    expect(layout).not_to_have_attribute(
        "data-composer-centered", timeout=TIMEOUT
    )
    input_box = chat.loc_input_container.bounding_box()
    chat_box = chat.loc.bounding_box()
    assert input_box is not None
    assert chat_box is not None
    assert (
        input_box["y"] + input_box["height"]
        >= chat_box["y"] + chat_box["height"] - 48
    )

    # A greeting taller than the chat region retains the usual bottom-pinned
    # composer instead of competing for the centered empty-state layout.
    page.reload()
    expect(layout).to_have_attribute("data-composer-centered", "")
    greeting.evaluate("(element) => { element.style.minHeight = '100vh'; }")
    expect(layout).not_to_have_attribute(
        "data-composer-centered", timeout=TIMEOUT
    )
    input_box = chat.loc_input_container.bounding_box()
    chat_box = chat.loc.bounding_box()
    assert input_box is not None
    assert chat_box is not None
    assert (
        input_box["y"] + input_box["height"]
        >= chat_box["y"] + chat_box["height"] - 48
    )
    scroll_box = chat.loc_scroll_container.bounding_box()
    greeting_box = greeting.bounding_box()
    assert scroll_box is not None
    assert greeting_box is not None
    assert greeting_box["y"] >= scroll_box["y"]
    assert chat.loc_scroll_container.evaluate(
        "(element) => element.scrollHeight > element.clientHeight"
    )


def test_page_chat_remeasures_greeting_after_history_new(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, page_chat = open_page(page, local_app, viewport=(1280, 800))
    layout = chat.loc.locator(".shiny-chat-layout")

    chat.set_user_input("Save this conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: Save this conversation", timeout=TIMEOUT)

    page_chat.select_page("History", exact=True)
    history = page_chat.loc.get_by_role(
        "region", name="History", exact=True
    ).locator("shiny-chat-history")
    expect(history).to_be_visible(timeout=TIMEOUT)
    history.get_by_role("button", name="New conversation").click()
    page_chat.return_home()

    expect(layout).to_have_attribute(
        "data-composer-centered", "", timeout=TIMEOUT
    )
    expect(layout).not_to_have_attribute("data-composer-revealing")
    expect(layout).not_to_have_attribute("data-composer-resizing")
    greeting_box = chat.loc_greeting.bounding_box()
    composer_box = chat.loc.locator(".shiny-chat-composer").bounding_box()
    assert greeting_box is not None
    assert composer_box is not None
    assert composer_box["y"] >= greeting_box["y"] + greeting_box["height"]
    assert (
        composer_box["y"] - (greeting_box["y"] + greeting_box["height"]) <= 16
    )


def test_page_chat_tracks_resize_without_composer_transition(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    chat, _ = open_page(page, local_app, viewport=(1280, 800))
    layout = chat.loc.locator(".shiny-chat-layout")
    composer = chat.loc.locator(".shiny-chat-composer")
    expect(layout).to_have_attribute("data-composer-centered", "")

    resize_samples = layout.evaluate(
        """async (element) => {
          const samples = [];
          for (const width of ['720px', '420px', '680px', '460px']) {
            element.style.width = width;
            await new Promise(requestAnimationFrame);
            await new Promise(requestAnimationFrame);
            const composer = element.querySelector('.shiny-chat-composer');
            samples.push({
              resizing: element.hasAttribute('data-composer-resizing'),
              transitionDuration: getComputedStyle(composer).transitionDuration,
            });
          }
          element.style.removeProperty('width');
          return samples;
        }"""
    )
    assert all(sample["resizing"] for sample in resize_samples)
    assert all(
        sample["transitionDuration"] == "0s" for sample in resize_samples
    )

    expect(layout).not_to_have_attribute(
        "data-composer-resizing",
        timeout=TIMEOUT,
    )
    expect(composer).to_have_css("transition-duration", "0.35s")


def test_page_chat_respects_reduced_motion_for_composer_positioning(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app, viewport=(1280, 800))
    layout = chat.loc.locator(".shiny-chat-layout")
    composer = chat.loc.locator(".shiny-chat-composer")

    expect(layout).to_have_attribute("data-composer-centered", "")
    expect(composer).to_have_css("transition-duration", "0s")
    assert layout.evaluate(
        """(element) => {
          const composer = element.querySelector('.shiny-chat-composer');
          element.setAttribute('data-composer-revealing', '');
          const styles = getComputedStyle(composer);
          const disabled =
            styles.animationName === 'none' && styles.animationDuration === '0s';
          element.removeAttribute('data-composer-revealing');
          return disabled;
        }"""
    )
    expect(chat.loc_greeting).to_have_css("transition-duration", "0s")


def test_top_aligned_toast_starts_below_the_page_title_bar(
    page: Page, local_app: ShinyAppProc
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    header = page_chat.loc_header
    page.get_by_role("button", name="Show toast").click()

    container = page.locator("body > .toast-container")
    expect(container).to_be_visible(timeout=TIMEOUT)
    header_box = header.bounding_box()
    container_box = container.bounding_box()
    assert header_box is not None
    assert container_box is not None

    header_bottom = header_box["y"] + header_box["height"]
    assert container_box["y"] == pytest.approx(header_bottom, abs=1)
    expect(container).to_have_css("top", f"{ceil(header_bottom)}px")


def test_page_toolbars_move_without_duplicate_controls(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    toolbar = page_chat.loc_toolbar
    toolbar_sources = page_chat.loc.locator(".shiny-chat-page-toolbar-sources")
    home_input = page.locator("#toolbar_value")
    settings_input = page.locator("#settings_toolbar_value")
    global_input = page.locator("#toolbar_global_value")

    expect(toolbar.locator("#toolbar_value")).to_have_count(1)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(toolbar_sources).to_be_hidden()
    expect(page.locator("#toolbar_value")).to_have_count(1)
    expect(page.locator("#settings_toolbar_value")).to_have_count(1)
    expect(page.locator("#toolbar_global_value")).to_have_count(1)
    home_input.fill("home toolbar state")
    global_input.fill("global toolbar state")

    page_chat.select_page("History", exact=True)
    page_chat.expect_active_page("history")
    expect(toolbar.locator("#toolbar_value")).to_have_count(0)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(0)
    expect(page.locator("#toolbar_value")).to_have_count(1)

    page_chat.select_page("Settings")
    page_chat.expect_active_page("settings")
    expect(toolbar.locator("#settings_toolbar_value")).to_have_count(1)
    expect(toolbar.locator("#toolbar_value")).to_have_count(0)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(home_input).to_have_count(1)
    expect(settings_input).to_have_count(1)
    expect(global_input).to_have_value("global toolbar state")
    settings_input.fill("settings toolbar state")

    page_chat.select_page("About")
    page_chat.expect_active_page("about")
    expect(toolbar.locator("input")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(0)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(home_input).to_have_count(1)
    expect(settings_input).to_have_count(1)

    page_chat.return_home()
    expect(toolbar.locator("#toolbar_value")).to_have_count(1)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(home_input).to_have_value("home toolbar state")
    expect(settings_input).to_have_value("settings toolbar state")
    expect(global_input).to_have_value("global toolbar state")
    expect(
        page_chat.loc.locator(".shiny-chat-page-toolbar-content")
    ).to_have_count(2)

    page.set_viewport_size({"width": 390, "height": 760})
    expect(
        page_chat.loc_controls_mount_mobile.locator(
            ".shiny-chat-page-toolbar #toolbar_value"
        )
    ).to_have_count(1)
    expect(
        page_chat.loc_controls_mount_mobile.locator(
            ".shiny-chat-page-toolbar #toolbar_global_value"
        )
    ).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(global_input).to_have_value("global toolbar state")
    toggle = page_chat.loc_sidebar_toggle
    toggle.click()
    page_chat.select_page("Settings")
    expect(
        page_chat.loc_controls_mount_mobile.locator(
            ".shiny-chat-page-toolbar #settings_toolbar_value"
        )
    ).to_have_count(1)
    expect(toolbar.locator("#toolbar_global_value")).to_have_count(1)
    expect(toolbar.locator(".shiny-chat-page-toolbar-content")).to_have_count(1)
    expect(settings_input).to_have_value("settings toolbar state")
    expect(global_input).to_have_value("global toolbar state")
    expect(page.locator("#settings_toolbar_value")).to_have_count(1)


def test_desktop_sidebar_motion_keeps_close_semantics_and_suppresses_resize(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    sidebar = page_chat.loc_sidebar
    body = page_chat.loc_body
    toggle = page_chat.loc_sidebar_toggle

    assert "grid-template-columns" in body.evaluate(
        "(element) => getComputedStyle(element).transitionProperty"
    )

    toggle.click()
    expect(page_chat.loc).to_have_attribute("data-sidebar-open", "")
    expect(sidebar).to_be_visible()
    expect(sidebar).to_have_attribute("aria-hidden", "false")

    resizer = page_chat.loc.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible()
    resizer.dispatch_event("resize-start")
    expect(page_chat.loc).to_have_attribute("data-sidebar-resizing", "")
    expect(body).to_have_css("transition-duration", "0s")
    resizer.dispatch_event("resize-end")
    expect(page_chat.loc).not_to_have_attribute("data-sidebar-resizing", "")

    toggle.click()
    expect(page_chat.loc).not_to_have_attribute("data-sidebar-open", "")
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    assert sidebar.evaluate("(element) => element.hidden") is False
    expect(sidebar).to_be_hidden(timeout=TIMEOUT)


def test_non_resizable_sidebar_uses_bounded_desktop_grid_track(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1000, 800))
    sidebar = page_chat.loc_sidebar
    main = page_chat.loc_main

    page_chat.select_page("Pinned")
    expect(sidebar).to_be_visible()
    expect(
        page_chat.loc.get_by_role("separator", name="Resize sidebar")
    ).to_be_hidden()

    sidebar_box = sidebar.bounding_box()
    main_box = main.bounding_box()
    assert sidebar_box is not None
    assert main_box is not None
    assert sidebar_box["width"] <= 640
    assert main_box["width"] >= 360


def test_reduced_motion_disables_mobile_sidebar_transition(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    _, page_chat = open_page(page, local_app, viewport=(390, 760))
    sidebar = page_chat.loc_sidebar

    expect(sidebar).to_have_css("transition-duration", "0s")


def test_update_navset_selects_a_non_home_page(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    active_page = page.locator("#active_page_value")

    page_chat.expect_active_page("__home__")
    expect(active_page).to_have_text("__home__")

    page_chat.open_nav_offcanvas()
    page.locator("#select_settings").click()

    page_chat.expect_active_page("settings")
    expect(page.locator("#settings_page_input")).to_be_visible()
    expect(active_page).to_have_text("settings")


def test_update_navset_returns_home(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    chat, page_chat = open_page(page, local_app, viewport=(1280, 800))
    active_page = page.locator("#active_page_value")

    page_chat.select_page("Settings")
    page_chat.expect_active_page("settings")
    expect(active_page).to_have_text("settings")

    page_chat.open_nav_offcanvas()
    page.locator("#select_home").click()

    page_chat.expect_active_page("__home__")
    expect(chat.loc).to_be_visible()
    expect(active_page).to_have_text("__home__")


def test_update_navset_selects_a_page_inside_a_nav_menu(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    active_page = page.locator("#active_page_value")
    menu = page_chat.loc.locator(".shiny-chat-page-nav-menu")

    page_chat.expect_active_page("__home__")

    page_chat.open_nav_offcanvas()
    page.locator("#select_secret").click()

    page_chat.expect_active_page("secret")
    expect(page.locator("#secret_page")).to_be_visible()
    expect(active_page).to_have_text("secret")
    expect(menu).not_to_have_attribute("open", "")


def test_update_navset_with_unknown_value_reports_error_without_changing_state(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    _, page_chat = open_page(page, local_app, viewport=(1280, 800))
    active_page = page.locator("#active_page_value")

    page_chat.select_page("About")
    page_chat.expect_active_page("about")
    expect(active_page).to_have_text("about")

    with page.expect_console_message(
        lambda msg: msg.type == "error" and "nonexistent-page" in msg.text,
        timeout=TIMEOUT,
    ):
        page_chat.open_nav_offcanvas()
        page.locator("#select_unknown").click()

    page_chat.expect_active_page("about")
    expect(active_page).to_have_text("about")
