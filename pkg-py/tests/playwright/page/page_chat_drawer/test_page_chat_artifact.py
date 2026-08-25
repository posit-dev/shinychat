import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController, PageChatController

TIMEOUT = 30_000


def open_page(
    page: Page,
    local_app: ShinyAppProc,
    *,
    drawer_width: str | None = None,
    chat_width: str | None = None,
    viewport: tuple[int, int] = (1440, 900),
) -> tuple[ChatController, PageChatController]:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    query: list[str] = []
    if drawer_width:
        query.append(f"drawer_width={drawer_width}")
    if chat_width:
        query.append(f"chat_width={chat_width}")
    url = f"{local_app.url}?{'&'.join(query)}" if query else local_app.url
    page.goto(url)
    chat = ChatController(page, "chat")
    page_chat = PageChatController(page, "chat")
    expect(page_chat.loc).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat, page_chat


def test_mobile_drawer_capable_chat_fills_page_and_keeps_composer_inset(
    page: Page, local_app: ShinyAppProc
) -> None:
    viewport = (390, 760)
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
    assert wrapper_box["height"] == pytest.approx(chat_box["height"], abs=1)
    assert input_box["x"] >= chat_box["x"] + 16
    assert (
        input_box["x"] + input_box["width"]
        <= chat_box["x"] + chat_box["width"] - 16
    )
    assert (
        input_box["y"] + input_box["height"]
        >= chat_box["y"] + chat_box["height"] - 16
    )


def test_percentage_drawer_keeps_desktop_chat_width(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    page.get_by_role("button", name="Show drawer").click()

    panel = chat.loc.locator(".shiny-chat-drawer")
    layout = chat.loc.locator(".shiny-chat-layout")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    panel_box = panel.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert panel_box is not None
    assert wrapper_box is not None
    assert panel_box["width"] > 0
    assert wrapper_box["width"] >= 360
    assert panel_box["x"] >= layout_box["x"] + wrapper_box["width"]

    grid_tracks = layout.evaluate(
        """(element) =>
          getComputedStyle(element).gridTemplateColumns
            .split(" ")
            .map((value) => Number.parseFloat(value))"""
    )
    assert isinstance(grid_tracks, list)
    assert len(grid_tracks) == 2
    assert grid_tracks[0] >= 360
    assert wrapper_box["width"] <= grid_tracks[0] + 1
    assert panel_box["width"] == pytest.approx(grid_tracks[1], abs=1)
    wrapper_center = wrapper_box["x"] + wrapper_box["width"] / 2
    chat_track_center = layout_box["x"] + grid_tracks[0] / 2
    assert wrapper_center == pytest.approx(chat_track_center, abs=1)

    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(separator).to_be_visible()
    minimum = int(separator.get_attribute("aria-valuemin") or "0")
    maximum = int(separator.get_attribute("aria-valuemax") or "0")
    current = int(separator.get_attribute("aria-valuenow") or "0")
    assert minimum == 240
    assert minimum <= current <= maximum
    expect(separator).to_have_attribute("aria-valuetext", f"{current} pixels")


@pytest.mark.parametrize(
    ("chat_width", "expected_max_width", "expected_rendered_width"),
    [
        pytest.param("full", "100%", None, id="full"),
        pytest.param("wide", "900px", 900, id="wide"),
        pytest.param("intrinsic", "fit-content", None, id="intrinsic"),
    ],
)
def test_drawer_open_preserves_configured_chat_width(
    page: Page,
    local_app: ShinyAppProc,
    chat_width: str,
    expected_max_width: str,
    expected_rendered_width: int | None,
) -> None:
    chat, _ = open_page(
        page,
        local_app,
        drawer_width="default",
        chat_width=chat_width,
    )
    page.get_by_role("button", name="Show drawer").click()

    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    panel_box = panel.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert panel_box is not None
    assert wrapper_box is not None
    assert wrapper.evaluate(
        "(element) => getComputedStyle(element).maxWidth"
    ) == (expected_max_width)
    assert wrapper_box["x"] >= layout_box["x"]
    assert wrapper_box["x"] + wrapper_box["width"] <= panel_box["x"]

    if expected_rendered_width is not None:
        grid_tracks = layout.evaluate(
            """(element) =>
              getComputedStyle(element).gridTemplateColumns
                .split(" ")
                .map((value) => Number.parseFloat(value))"""
        )
        assert isinstance(grid_tracks, list)
        assert len(grid_tracks) == 2
        assert wrapper_box["width"] == pytest.approx(
            min(expected_rendered_width, grid_tracks[0]), abs=1
        )


def test_drawer_separator_remains_mouse_reachable_after_maximum_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    page.get_by_role("button", name="Show drawer").click()

    panel = chat.loc.locator(".shiny-chat-drawer")
    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(separator).to_be_visible()
    page.wait_for_timeout(220)

    def arm_and_drag(delta_x: float) -> None:
        box = separator.bounding_box()
        assert box is not None
        start_x = box["x"] + 1
        y = box["y"] + box["height"] / 2
        # Cross the panel edge from the chat column before grabbing. The
        # unarmed handle is pointer-transparent, so this follows mouse use.
        page.mouse.move(max(0, start_x - 2), y)
        page.mouse.move(start_x + 1, y)
        expect(separator).to_have_attribute("data-boundary-armed", "")
        page.mouse.down()
        expect(separator).to_have_attribute("data-resizing", "")
        page.mouse.move(start_x + delta_x, y)
        page.mouse.up()

    # Grow to the clamp, moving the separator's geometry in the process.
    arm_and_drag(-1000)
    page.wait_for_timeout(220)
    maximum = int(separator.get_attribute("aria-valuenow") or "0")
    maximum_bound = int(separator.get_attribute("aria-valuemax") or "0")
    assert maximum == maximum_bound

    arm_and_drag(100)
    page.wait_for_timeout(220)
    resized = int(separator.get_attribute("aria-valuenow") or "0")
    assert 240 <= resized < maximum
    resized_box = panel.bounding_box()
    assert resized_box is not None
    assert resized_box["width"] == pytest.approx(resized, abs=1)

    separator.press("End")
    end_width = int(separator.get_attribute("aria-valuenow") or "0")
    separator.press("ArrowLeft")
    expected_width = end_width
    page.wait_for_timeout(220)
    expect(separator).to_have_attribute("aria-valuenow", str(expected_width))
    settled_box = panel.bounding_box()
    assert settled_box is not None
    assert settled_box["width"] == pytest.approx(expected_width, abs=1)


def test_drawer_separator_uses_bslib_sized_trip_and_active_targets(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    page.get_by_role("button", name="Show drawer").click()

    panel = chat.loc.locator(".shiny-chat-drawer")
    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(separator).to_be_visible()
    page.wait_for_timeout(220)
    panel.evaluate(
        """(element) => {
          element.dataset.resizeUnderlayClicks = "0";
          element.addEventListener("click", () => {
            element.dataset.resizeUnderlayClicks = String(
              Number(element.dataset.resizeUnderlayClicks) + 1
            );
          });
        }"""
    )

    def assert_bslib_sized_target(panel_direction: float) -> None:
        box = separator.bounding_box()
        assert box is not None
        boundary = box["x"] if panel_direction > 0 else box["x"] + box["width"]
        y = box["y"] + box["height"] / 2
        target = separator.evaluate(
            """(element) => {
              const trip = getComputedStyle(element, "::after");
              return {
                width: Number.parseFloat(trip.width),
                offset: trip.insetInlineStart,
              };
            }"""
        )
        assert target == {"width": 5, "offset": "-2px"}

        # Both sides of the true divider can enter the transparent 5px trip.
        page.mouse.move(boundary - panel_direction * 2, y)
        expect(separator).to_have_attribute("data-boundary-armed", "")
        active_width = separator.evaluate(
            """(element) =>
              Number.parseFloat(getComputedStyle(element, "::after").width)"""
        )
        assert active_width == 24

        # Eleven pixels from the divider is outside the idle trip but inside
        # the 24px armed target, so it remains usable without a precise
        # reacquisition.
        page.mouse.move(boundary + panel_direction * 11, y)
        expect(separator).to_have_attribute("data-boundary-armed", "")
        page.mouse.down()
        expect(separator).to_have_attribute("data-resizing", "")
        page.mouse.up()
        expect(separator).not_to_have_attribute("data-resizing", "")

        page.mouse.move(boundary + panel_direction * 2, y)
        expect(separator).to_have_attribute("data-boundary-armed", "")
        page.mouse.move(boundary + panel_direction * 13, y)
        expect(separator).not_to_have_attribute("data-boundary-armed", "")

        # The real indicator retains bslib's direct-grab bypass even before
        # the pointer has crossed the activation proximity.
        indicator = separator.locator("[data-shiny-chat-resize-indicator]")
        indicator_box = indicator.bounding_box()
        assert indicator_box is not None
        page.mouse.move(
            indicator_box["x"] + indicator_box["width"] / 2,
            indicator_box["y"] + indicator_box["height"] / 2,
        )
        separator.evaluate(
            "(element) => element.removeAttribute('data-boundary-armed')"
        )
        page.mouse.down()
        expect(separator).to_have_attribute("data-resizing", "")
        page.mouse.up()

    box = separator.bounding_box()
    assert box is not None
    y = box["y"] + box["height"] / 2
    # Five pixels inside the panel is outside the 5px divider trip, so this
    # real mouse click reaches the adjacent panel content below the handle.
    page.mouse.click(box["x"] + 5, y)
    expect(panel).to_have_attribute("data-resize-underlay-clicks", "1")
    assert_bslib_sized_target(1)

    page.evaluate("document.documentElement.dir = 'rtl'")
    page.wait_for_timeout(220)
    rtl_box = separator.bounding_box()
    assert rtl_box is not None
    previous_clicks = int(
        panel.get_attribute("data-resize-underlay-clicks") or "0"
    )
    page.mouse.click(rtl_box["x"] + 2, y)
    expect(panel).to_have_attribute(
        "data-resize-underlay-clicks", str(previous_clicks + 1)
    )
    assert_bslib_sized_target(-1)


def test_debug_resize_overlays_show_drawer_fine_targets(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    page.get_by_role("button", name="Show drawer").click()
    drawer_resizer = page.get_by_role("separator", name="Resize drawer panel")
    expect(drawer_resizer).to_be_visible(timeout=TIMEOUT)
    page.wait_for_timeout(220)

    production_overlay = drawer_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert production_overlay["background"] == "rgba(0, 0, 0, 0)"

    page.locator("body").evaluate(
        "(element) => element.classList.add('shiny-chat-debug-resize-handle')"
    )
    idle_overlay = drawer_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert idle_overlay["width"] == 5
    assert idle_overlay["background"] != "rgba(0, 0, 0, 0)"
    assert idle_overlay["pointerEvents"] == production_overlay["pointerEvents"]

    indicator = drawer_resizer.locator("[data-shiny-chat-resize-indicator]")
    expect(indicator).to_be_visible()

    drawer_idle = drawer_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
          };
        }"""
    )
    assert drawer_idle["width"] == 5
    assert drawer_idle["background"] != "rgba(0, 0, 0, 0)"

    indicator_color = indicator.evaluate(
        "(element) => getComputedStyle(element).backgroundColor"
    )
    assert indicator_color != "rgba(0, 0, 0, 0)"

    drawer_box = drawer_resizer.bounding_box()
    assert drawer_box is not None
    drawer_y = drawer_box["y"] + drawer_box["height"] / 2
    page.mouse.move(drawer_box["x"] - 4, drawer_y)
    page.mouse.move(drawer_box["x"] + drawer_box["width"] + 4, drawer_y)
    expect(drawer_resizer).to_have_attribute("data-boundary-armed", "")
    drawer_armed = drawer_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
          };
        }"""
    )
    assert drawer_armed["width"] == 24
    assert drawer_armed["background"] != drawer_idle["background"]


def test_drawer_resizer_uses_coarse_touch_geometry(
    page: Page, local_app: ShinyAppProc
) -> None:
    session = page.context.new_cdp_session(page)
    session.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": True, "maxTouchPoints": 1},
    )
    chat, _ = open_page(page, local_app, drawer_width="default")
    page.get_by_role("button", name="Show drawer").click()

    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(separator).to_be_visible(timeout=TIMEOUT)
    expect(separator).to_have_css("width", "26px")
    page.locator("body").evaluate(
        "(element) => element.classList.add('shiny-chat-debug-resize-handle')"
    )
    debug_overlay = separator.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::before");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert debug_overlay == {
        "width": 26,
        "background": "rgba(13, 110, 253, 0.28)",
        "pointerEvents": "none",
    }
    page.wait_for_timeout(220)
    initial_width = int(separator.get_attribute("aria-valuenow") or "0")
    box = separator.bounding_box()
    assert box is not None
    start_x = box["x"] + box["width"] - 1
    y = box["y"] + 100
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": "touchStart",
            "touchPoints": [{"x": start_x, "y": y, "id": 7}],
        },
    )
    expect(separator).to_have_attribute("data-resizing", "")
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": "touchMove",
            "touchPoints": [{"x": start_x - 80, "y": y, "id": 7}],
        },
    )
    session.send(
        "Input.dispatchTouchEvent",
        {"type": "touchEnd", "touchPoints": []},
    )
    assert int(separator.get_attribute("aria-valuenow") or "0") > initial_width


def test_drawer_resizer_recovers_after_responsive_takeover(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    page.get_by_role("button", name="Show drawer").click()

    panel = chat.loc.locator(".shiny-chat-drawer")
    separator = page.get_by_role("separator", name="Resize drawer panel")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(separator).to_be_visible()

    page.set_viewport_size({"width": 600, "height": 900})
    expect(chat.loc.locator(".shiny-chat-layout")).to_have_attribute(
        "data-drawer-takeover", ""
    )
    expect(separator).to_have_count(0)

    page.set_viewport_size({"width": 1440, "height": 900})
    expect(chat.loc.locator(".shiny-chat-layout")).not_to_have_attribute(
        "data-drawer-takeover", ""
    )
    expect(separator).to_be_visible()
    width = int(separator.get_attribute("aria-valuenow") or "0")
    separator.press("ArrowLeft")
    expect(separator).to_have_attribute("aria-valuenow", str(width + 10))


def test_ninety_percent_drawer_is_bounded_before_reveal(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="90pct")
    layout = chat.loc.locator(".shiny-chat-layout")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    page.get_by_role("button", name="Show drawer").click()
    expect(layout).to_have_attribute("data-drawer-open", "")
    expect(layout).to_have_css("--shiny-chat-drawer-width", "1056px")
    page.wait_for_timeout(70)

    grid_tracks = layout.evaluate(
        """(element) =>
          getComputedStyle(element).gridTemplateColumns
            .split(" ")
            .map((value) => Number.parseFloat(value))"""
    )
    wrapper_box = wrapper.bounding_box()
    assert isinstance(grid_tracks, list)
    assert len(grid_tracks) == 2
    assert grid_tracks[0] >= 360
    assert wrapper_box is not None
    assert wrapper_box["width"] >= 360


def test_default_drawer_width_centers_chat_wrapper(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    closed_box = wrapper.bounding_box()
    assert closed_box is not None

    page.evaluate(
        """() => {
          const layout = document.querySelector(".shiny-chat-layout");
          const wrapper = document.querySelector(".shiny-chat-wrapper");
          if (!layout || !wrapper) {
            return;
          }
          window.__shinychatDrawerOpeningX = new Promise((resolve) => {
            const observer = new MutationObserver(() => {
              if (!layout.hasAttribute("data-drawer-open")) return;
              observer.disconnect();
              resolve(wrapper.getBoundingClientRect().x);
            });
            observer.observe(layout, { attributes: true });
          });
        }"""
    )
    page.get_by_role("button", name="Show drawer").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    opening_x = page.evaluate("() => window.__shinychatDrawerOpeningX")
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    panel_box = panel.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert panel_box is not None
    assert wrapper_box is not None
    assert isinstance(opening_x, (int, float))
    assert panel_box["width"] == pytest.approx(400, abs=1)

    first_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(getComputedStyle(element).gridTemplateColumns.split(" ")[0])"""
    )
    gap = layout.evaluate(
        "(element) => Number.parseFloat(getComputedStyle(element).columnGap)"
    )
    wrapper_center = wrapper_box["x"] + wrapper_box["width"] / 2
    track_center = layout_box["x"] + first_track / 2

    assert wrapper_center == pytest.approx(track_center, abs=1)
    assert panel_box["x"] - (layout_box["x"] + first_track) == pytest.approx(
        gap, abs=1
    )
    assert opening_x == pytest.approx(closed_box["x"], abs=1)
    assert wrapper_box["x"] != pytest.approx(closed_box["x"], abs=1)

    panel.get_by_role("button", name="Close drawer").click()


def test_rtl_closed_drawer_wrapper_stays_centered(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="default")
    layout = chat.loc.locator(".shiny-chat-layout")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    page.evaluate("document.documentElement.dir = 'rtl'")
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert wrapper_box is not None
    assert wrapper_box["x"] >= layout_box["x"]
    assert wrapper_box["x"] + wrapper_box["width"] <= (
        layout_box["x"] + layout_box["width"]
    )
    assert wrapper_box["x"] + wrapper_box["width"] / 2 == pytest.approx(
        layout_box["x"] + layout_box["width"] / 2, abs=1
    )


def test_relative_drawer_width_refreshes_without_layout_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, drawer_width="relative")
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")

    page.get_by_role("button", name="Show drawer").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(layout).to_have_css("--shiny-chat-drawer-width", "512px")
    page.wait_for_timeout(220)
    initial_layout_box = layout.bounding_box()
    assert initial_layout_box is not None

    page.evaluate("document.documentElement.style.fontSize = '20px'")
    expect(layout).to_have_css("--shiny-chat-drawer-width", "640px")
    refreshed_layout_box = layout.bounding_box()
    assert refreshed_layout_box is not None
    assert refreshed_layout_box["width"] == pytest.approx(
        initial_layout_box["width"], abs=1
    )


def test_page_drawer_survives_navigation_and_history(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, page_chat = open_page(page, local_app)
    panel = chat.loc.locator(".shiny-chat-drawer")

    page.get_by_role("button", name="Show drawer").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Initial drawer")

    page.get_by_role("button", name="Update drawer").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated drawer")
    drawer_input = panel.locator("#drawer_text")
    drawer_input.fill("edited drawer")
    expect(panel.locator("#drawer_value")).to_have_text(
        "Drawer value: edited drawer",
        timeout=TIMEOUT,
    )

    page_chat.select_page("Details")
    page_chat.expect_active_page("details")
    expect(chat.loc).to_be_hidden()
    expect(panel).to_be_hidden()
    expect(page.locator("#details_page")).to_be_visible()

    page_chat.return_home()
    expect(chat.loc).to_be_visible()
    expect(panel).to_be_visible()
    expect(drawer_input).to_have_value("edited drawer")
    expect(panel.locator("#drawer_value")).to_have_text(
        "Drawer value: edited drawer",
        timeout=TIMEOUT,
    )

    chat.set_user_input("first conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: first conversation", timeout=TIMEOUT)

    sidebar = page_chat.loc_sidebar
    toggle = page_chat.loc_sidebar_toggle
    expect(sidebar).to_be_hidden()
    toggle.click()
    expect(sidebar).to_be_visible()
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )

    sidebar.locator(".shiny-chat-history-new").click()
    expect(chat.loc_messages.locator("> *")).to_have_count(0, timeout=TIMEOUT)
    expect(panel).to_be_visible()
    expect(drawer_input).to_have_value("edited drawer")

    chat.set_user_input("second conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: second conversation", timeout=TIMEOUT)
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=TIMEOUT
    )

    sidebar.locator(
        ".shiny-chat-history-item-select", has_text="first conversation"
    ).click()
    chat.expect_latest_message("echo: first conversation", timeout=TIMEOUT)
    expect(panel).to_be_visible()
    expect(panel.get_by_role("heading")).to_have_text("Updated drawer")
    expect(drawer_input).to_have_value("edited drawer")
    expect(panel.locator("#drawer_value")).to_have_text(
        "Drawer value: edited drawer",
        timeout=TIMEOUT,
    )


def test_drawer_motion_retains_close_panel_and_suppresses_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")

    assert "--shiny-chat-drawer-layout-width" in layout.evaluate(
        "(element) => getComputedStyle(element).transitionProperty"
    )
    page.locator("#show_drawer").click()
    expect(panel).to_have_attribute("data-motion", "open")
    expect(layout).to_have_attribute("data-drawer-open", "")

    separator = page.get_by_role("separator", name="Resize drawer panel")
    separator.dispatch_event("resize-start")
    expect(layout).to_have_attribute("data-drawer-resizing", "")
    expect(layout).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close drawer").click()
    expect(panel).to_have_attribute("data-motion", "closing")
    expect(layout).not_to_have_attribute("data-drawer-resizing", "")
    expect(panel).to_have_attribute("aria-hidden", "true")
    assert panel.evaluate("(element) => element.hidden") is False
    expect(layout).to_have_attribute("data-drawer-open", "")
    expect(panel).to_be_hidden(timeout=TIMEOUT)
    expect(layout).not_to_have_attribute("data-drawer-open", "")


def test_drawer_layout_track_interpolates_during_desktop_reveal(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")

    page.locator("#show_drawer").click()
    expect(layout).to_have_attribute("data-drawer-open", "")
    expect(panel).to_be_visible()
    page.wait_for_function(
        """() => {
          const element = document.querySelector(".shiny-chat-layout");
          if (!element) return false;
          const track = Number.parseFloat(
            getComputedStyle(element).gridTemplateColumns.split(" ")[1]
          );
          const target = Number.parseFloat(
            getComputedStyle(element).getPropertyValue(
              "--shiny-chat-drawer-width"
            )
          );
          return track > 0 && track < target;
        }""",
        polling="raf",
        timeout=TIMEOUT,
    )
    intermediate_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(
            getComputedStyle(element).gridTemplateColumns.split(" ")[1]
          )"""
    )
    page.wait_for_timeout(220)
    final_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(
            getComputedStyle(element).gridTemplateColumns.split(" ")[1]
          )"""
    )

    assert intermediate_track > 0
    assert intermediate_track < final_track


def test_drawer_motion_respects_reduced_motion_and_takeover(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    page.get_by_role("button", name="Show drawer").click()
    expect(layout).to_have_css("transition-duration", "0s")
    expect(panel).to_have_css("transition-duration", "0s")
    expect(wrapper).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close drawer").click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)

    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 600, "height": 900})
    chat.loc.locator(".shiny-chat-drawer-trigger").click()
    expect(layout).to_have_attribute("data-drawer-takeover", "")
    expect(layout).to_have_css("transition-duration", "0s")


def test_drawer_stays_adjacent_with_open_desktop_sidebar(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, page_chat = open_page(
        page,
        local_app,
        drawer_width="default",
        viewport=(1024, 900),
    )
    sidebar = page_chat.loc_sidebar
    if sidebar.is_hidden():
        page_chat.loc_sidebar_toggle.click()
    expect(sidebar).to_be_visible(timeout=TIMEOUT)

    page.get_by_role("button", name="Show drawer").click()
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-drawer")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(layout).not_to_have_attribute("data-drawer-takeover")
    expect(
        page.get_by_role("separator", name="Resize drawer panel")
    ).to_be_visible()


@pytest.mark.parametrize(
    "viewport",
    [
        pytest.param((390, 760), id="mobile"),
        pytest.param((800, 760), id="constrained-container"),
    ],
)
def test_compact_drawer_trigger_does_not_overlay_messages(
    page: Page,
    local_app: ShinyAppProc,
    viewport: tuple[int, int],
) -> None:
    chat, page_chat = open_page(page, local_app, viewport=viewport)

    expect(chat.loc.locator(".shiny-chat-messages")).to_have_css(
        "padding-top", "0px"
    )
    chat.set_user_input("hi there")
    chat.send_user_input()
    chat.expect_latest_message("echo: hi there", timeout=TIMEOUT)

    if viewport[0] <= 799:
        page_chat.loc_sidebar_toggle.click()
    page.get_by_role("button", name="Show drawer").click()
    page.get_by_role("button", name="Close drawer").click()

    trigger = chat.loc.locator(".shiny-chat-drawer-trigger")
    message = chat.loc.locator(".shiny-chat-user-message").first
    expect(trigger).to_be_visible()
    expect(message).to_be_visible()
    expect(chat.loc.locator(".shiny-chat-messages")).to_have_css(
        "padding-top", "48px"
    )

    trigger_box = trigger.bounding_box()
    message_box = message.bounding_box()
    assert trigger_box is not None
    assert message_box is not None
    assert message_box["y"] >= trigger_box["y"] + trigger_box["height"]
