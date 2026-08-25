from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

TIMEOUT = 30_000


def open_chat(
    page: Page,
    local_app: ShinyAppProc,
    *,
    viewport: tuple[int, int],
) -> ChatController:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat


def chat_input(chat: ChatController):
    return chat.loc.get_by_role("textbox", name="Chat message")


def test_drawer_desktop_transport_and_rebinding(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_chat(page, local_app, viewport=(1440, 900))

    page.locator("#show_drawer").click()
    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Initial drawer")
    expect(panel.locator(".drawer-content-label")).to_have_text(
        "Initial content"
    )
    marker = panel.locator(".drawer-dependency-marker")
    expect(marker).to_have_css("border-top-color", "rgb(24, 119, 242)")
    expect(chat_input(chat)).to_be_visible()
    expect(
        page.get_by_role("separator", name="Resize drawer panel")
    ).to_be_visible()

    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    page.wait_for_timeout(220)
    page.wait_for_function(
        """() => {
          const wrapper = document.querySelector("#chat .shiny-chat-wrapper");
          const panel = document.querySelector(".shiny-chat-drawer");
          if (!wrapper || !panel) return false;
          const wrapperBox = wrapper.getBoundingClientRect();
          const panelBox = panel.getBoundingClientRect();
          return panelBox.x >= wrapperBox.x + wrapperBox.width;
        }""",
        timeout=TIMEOUT,
    )
    wrapper_box = wrapper.bounding_box()
    panel_box = panel.bounding_box()
    assert wrapper_box is not None
    assert panel_box is not None
    assert panel_box["x"] >= wrapper_box["x"] + wrapper_box["width"]

    drawer_input = page.locator("#drawer_text")
    expect(drawer_input).to_be_visible()
    expect(panel.locator("#drawer_output")).to_have_text(
        "Drawer output: Initial",
        timeout=TIMEOUT,
    )
    drawer_input.fill("desktop value")
    expect(page.locator("#drawer_echo")).to_have_text(
        "Echo: desktop value",
        timeout=TIMEOUT,
    )
    expect(panel.locator("#drawer_output")).to_have_text(
        "Drawer output: desktop value",
        timeout=TIMEOUT,
    )

    page.locator("#update_drawer").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated drawer")
    expect(panel.locator(".drawer-content-label")).to_have_text(
        "Updated content"
    )
    expect(marker).to_have_css("border-top-color", "rgb(24, 119, 242)")
    expect(drawer_input).to_have_value("Updated")
    expect(panel.locator("#drawer_output")).to_have_text(
        "Drawer output: Updated",
        timeout=TIMEOUT,
    )
    drawer_input.fill("rebound value")
    expect(page.locator("#drawer_echo")).to_have_text(
        "Echo: rebound value",
        timeout=TIMEOUT,
    )
    expect(panel.locator("#drawer_output")).to_have_text(
        "Drawer output: rebound value",
        timeout=TIMEOUT,
    )

    page.locator("#hide_drawer").click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)

    page.locator("#show_preserved").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Updated drawer")
    expect(drawer_input).to_have_value("rebound value")


def test_drawer_explicitly_clears_content_and_title(
    page: Page, local_app: ShinyAppProc
) -> None:
    open_chat(page, local_app, viewport=(1440, 900))

    page.locator("#show_drawer").click()
    panel = page.get_by_role("complementary")
    expect(panel.get_by_role("heading")).to_have_text("Initial drawer")
    expect(panel.locator(".drawer-content-label")).to_have_text(
        "Initial content"
    )

    page.locator("#clear_drawer").click()
    expect(panel.get_by_role("heading")).to_have_text("Drawer", timeout=TIMEOUT)
    expect(panel.locator(".drawer-content-label")).to_have_count(0)
    expect(panel.locator("#drawer_text")).to_have_count(0)
    expect(panel.locator("#drawer_output")).to_have_count(0)


def test_drawer_desktop_resize_semantics_focus_and_signaling(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_chat(page, local_app, viewport=(1440, 900))
    input_loc = chat_input(chat)
    page.evaluate(
        """() => {
          window.__drawerResizeEvents = 0;
          window.addEventListener("resize", () => {
            window.__drawerResizeEvents += 1;
          });
        }"""
    )
    input_loc.focus()
    expect(input_loc).to_be_focused()

    page.locator("#show_drawer").evaluate("(button) => button.click()")
    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(input_loc).to_be_focused()
    page.wait_for_function("window.__drawerResizeEvents > 0")

    heading = panel.get_by_role("heading")
    title_id = heading.get_attribute("id")
    assert title_id is not None
    expect(panel).to_have_attribute("aria-labelledby", title_id)
    expect(page.get_by_role("button", name="Close drawer")).to_be_visible()

    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(separator).to_have_attribute("aria-orientation", "vertical")
    expect(separator).to_have_attribute("aria-valuemin", "240")
    initial_width = int(separator.get_attribute("aria-valuenow") or "0")
    expect(separator).to_have_attribute(
        "aria-valuetext", f"{initial_width} pixels"
    )

    separator.press("ArrowLeft")
    keyboard_width = initial_width + 10
    expect(separator).to_have_attribute("aria-valuenow", str(keyboard_width))

    separator.evaluate(
        """(handle) => {
          handle.setPointerCapture = () => {};
          const box = handle.getBoundingClientRect();
          const startX = box.x + box.width / 2;
          const indicator = handle.querySelector(
            "[data-shiny-chat-resize-indicator]"
          );
          if (!indicator) throw new Error("Resize indicator is missing");
          const event = (type, clientX) => new PointerEvent(type, {
            bubbles: true,
            button: 0,
            clientX,
            isPrimary: true,
            pointerId: 7,
            pointerType: "mouse",
          });
          indicator.dispatchEvent(event("pointerdown", startX));
          indicator.dispatchEvent(event("pointermove", startX - 80));
          indicator.dispatchEvent(event("pointerup", startX - 80));
        }"""
    )
    expect(separator).to_have_attribute(
        "aria-valuenow", str(keyboard_width + 80)
    )

    resize_events_before_update = page.evaluate("window.__drawerResizeEvents")
    page.locator("#update_drawer").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated drawer")
    page.wait_for_function(
        "(beforeUpdate) => window.__drawerResizeEvents > beforeUpdate",
        arg=resize_events_before_update,
    )


def test_drawer_honors_reduced_motion(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_chat(page, local_app, viewport=(1440, 900))

    page.locator("#show_drawer").click()
    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    assert panel.evaluate(
        "(element) => getComputedStyle(element).animationName"
    ) == ("none")

    separator = page.get_by_role("separator", name="Resize drawer panel")
    indicator = separator.locator("[data-shiny-chat-resize-indicator]")
    assert indicator.evaluate(
        "(element) => getComputedStyle(element).transitionProperty"
    ) == ("none")


def test_drawer_takeover_focus_and_close(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_chat(page, local_app, viewport=(600, 900))
    input_loc = chat_input(chat)
    input_loc.focus()
    expect(input_loc).to_be_focused()

    # A programmatic click keeps focus in the chat while exercising the real
    # server-side action and Shiny transport path.
    page.locator("#show_drawer").evaluate("(button) => button.click()")

    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc.locator(".shiny-chat-wrapper")).to_be_hidden()
    close = page.get_by_role("button", name="Close drawer")
    expect(close).to_be_visible()
    expect(close).to_be_focused()

    close.click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)
    expect(chat.loc.locator(".shiny-chat-wrapper")).to_be_visible()
    expect(input_loc).to_be_focused()
