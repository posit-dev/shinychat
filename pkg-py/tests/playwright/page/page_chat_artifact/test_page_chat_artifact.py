import pytest
from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

TIMEOUT = 30_000


def open_page(
    page: Page, local_app: ShinyAppProc, *, artifact_width: str | None = None
) -> tuple[ChatController, Locator]:
    page.set_viewport_size({"width": 1440, "height": 900})
    url = local_app.url
    if artifact_width:
        url = f"{url}?artifact_width={artifact_width}"
    page.goto(url)
    chat = ChatController(page, "chat")
    shell = page.locator("shiny-chat-page")
    expect(shell).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat, shell


def test_percentage_artifact_keeps_desktop_chat_width(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    page.get_by_role("button", name="Show artifact").click()

    panel = chat.loc.locator(".shiny-chat-artifact")
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

    separator = page.get_by_role("separator", name="Resize artifact panel")
    expect(separator).to_be_visible()
    minimum = int(separator.get_attribute("aria-valuemin") or "0")
    maximum = int(separator.get_attribute("aria-valuemax") or "0")
    current = int(separator.get_attribute("aria-valuenow") or "0")
    assert minimum == 240
    assert minimum <= current <= maximum
    expect(separator).to_have_attribute("aria-valuetext", f"{current} pixels")


def test_artifact_separator_remains_mouse_reachable_after_maximum_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
    page.get_by_role("button", name="Show artifact").click()

    panel = chat.loc.locator(".shiny-chat-artifact")
    separator = page.get_by_role("separator", name="Resize artifact panel")
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
    expected_width = end_width - 10
    page.wait_for_timeout(220)
    expect(separator).to_have_attribute("aria-valuenow", str(expected_width))
    settled_box = panel.bounding_box()
    assert settled_box is not None
    assert settled_box["width"] == pytest.approx(expected_width, abs=1)


def test_artifact_separator_uses_bslib_sized_trip_and_active_targets(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
    page.get_by_role("button", name="Show artifact").click()

    panel = chat.loc.locator(".shiny-chat-artifact")
    separator = page.get_by_role("separator", name="Resize artifact panel")
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

    def assert_bslib_sized_target(boundary: float, panel_direction: float) -> None:
        box = separator.bounding_box()
        assert box is not None
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
    assert_bslib_sized_target(box["x"], 1)

    page.evaluate("document.documentElement.dir = 'rtl'")
    page.wait_for_timeout(220)
    rtl_box = separator.bounding_box()
    assert rtl_box is not None
    previous_clicks = int(panel.get_attribute("data-resize-underlay-clicks") or "0")
    page.mouse.click(rtl_box["x"] + 2, y)
    expect(panel).to_have_attribute(
        "data-resize-underlay-clicks", str(previous_clicks + 1)
    )
    assert_bslib_sized_target(rtl_box["x"] + rtl_box["width"], -1)


def test_debug_resize_overlays_show_artifact_fine_targets(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
    page.get_by_role("button", name="Show artifact").click()
    artifact_resizer = page.get_by_role("separator", name="Resize artifact panel")
    expect(artifact_resizer).to_be_visible(timeout=TIMEOUT)
    page.wait_for_timeout(220)

    production_overlay = artifact_resizer.evaluate(
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
    idle_overlay = artifact_resizer.evaluate(
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

    indicator = artifact_resizer.locator("[data-shiny-chat-resize-indicator]")
    expect(indicator).to_be_visible()

    artifact_idle = artifact_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
          };
        }"""
    )
    assert artifact_idle["width"] == 5
    assert artifact_idle["background"] != "rgba(0, 0, 0, 0)"

    indicator_color = indicator.evaluate(
        "(element) => getComputedStyle(element).backgroundColor"
    )
    assert indicator_color != "rgba(0, 0, 0, 0)"

    artifact_box = artifact_resizer.bounding_box()
    assert artifact_box is not None
    artifact_y = artifact_box["y"] + artifact_box["height"] / 2
    page.mouse.move(artifact_box["x"] - 4, artifact_y)
    page.mouse.move(artifact_box["x"] + artifact_box["width"] + 4, artifact_y)
    expect(artifact_resizer).to_have_attribute("data-boundary-armed", "")
    artifact_armed = artifact_resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
          };
        }"""
    )
    assert artifact_armed["width"] == 24
    assert artifact_armed["background"] != artifact_idle["background"]


def test_artifact_resizer_uses_coarse_touch_geometry(
    page: Page, local_app: ShinyAppProc
) -> None:
    session = page.context.new_cdp_session(page)
    session.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": True, "maxTouchPoints": 1},
    )
    chat, _ = open_page(page, local_app, artifact_width="default")
    page.get_by_role("button", name="Show artifact").click()

    separator = page.get_by_role("separator", name="Resize artifact panel")
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


def test_artifact_resizer_recovers_after_responsive_takeover(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
    page.get_by_role("button", name="Show artifact").click()

    panel = chat.loc.locator(".shiny-chat-artifact")
    separator = page.get_by_role("separator", name="Resize artifact panel")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(separator).to_be_visible()

    page.set_viewport_size({"width": 800, "height": 900})
    expect(chat.loc.locator(".shiny-chat-layout")).to_have_attribute(
        "data-artifact-takeover", ""
    )
    expect(separator).to_have_count(0)

    page.set_viewport_size({"width": 1440, "height": 900})
    expect(chat.loc.locator(".shiny-chat-layout")).not_to_have_attribute(
        "data-artifact-takeover", ""
    )
    expect(separator).to_be_visible()
    width = int(separator.get_attribute("aria-valuenow") or "0")
    separator.press("ArrowLeft")
    expect(separator).to_have_attribute("aria-valuenow", str(width - 10))


def test_ninety_percent_artifact_is_bounded_before_reveal(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="90pct")
    layout = chat.loc.locator(".shiny-chat-layout")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    page.get_by_role("button", name="Show artifact").click()
    expect(layout).to_have_attribute("data-artifact-open", "")
    expect(layout).to_have_css("--shiny-chat-artifact-width", "1056px")
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


def test_default_artifact_width_end_aligns_chat_wrapper(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    closed_box = wrapper.bounding_box()
    closed_translate = wrapper.evaluate(
        """(element) => new DOMMatrixReadOnly(
          getComputedStyle(element).transform
        ).m41"""
    )
    assert closed_box is not None
    assert closed_translate < 0

    page.get_by_role("button", name="Show artifact").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    page.wait_for_function(
        f"""() => {{
          const wrapper = document.querySelector(".shiny-chat-wrapper");
          if (!wrapper) return false;
          const translate = new DOMMatrixReadOnly(
            getComputedStyle(wrapper).transform
          ).m41;
          return translate > {closed_translate + 1} && translate < -1;
        }}""",
        polling="raf",
        timeout=TIMEOUT,
    )
    intermediate_open_box = wrapper.bounding_box()
    page.wait_for_timeout(220)

    layout_box = layout.bounding_box()
    panel_box = panel.bounding_box()
    wrapper_box = wrapper.bounding_box()
    assert layout_box is not None
    assert panel_box is not None
    assert wrapper_box is not None
    assert intermediate_open_box is not None
    assert panel_box["width"] == pytest.approx(400, abs=1)

    first_track = layout.evaluate(
        """(element) =>
          Number.parseFloat(getComputedStyle(element).gridTemplateColumns.split(" ")[0])"""
    )
    gap = layout.evaluate(
        "(element) => Number.parseFloat(getComputedStyle(element).columnGap)"
    )
    wrapper_right = wrapper_box["x"] + wrapper_box["width"]
    track_right = layout_box["x"] + first_track

    assert wrapper_right == pytest.approx(track_right, abs=1)
    assert panel_box["x"] - wrapper_right == pytest.approx(gap, abs=1)
    assert (
        min(closed_box["x"], wrapper_box["x"])
        < intermediate_open_box["x"]
        < max(closed_box["x"], wrapper_box["x"])
    )

    panel.get_by_role("button", name="Close artifact").click()
    page.wait_for_function(
        f"""() => {{
          const wrapper = document.querySelector(".shiny-chat-wrapper");
          if (!wrapper) return false;
          const translate = new DOMMatrixReadOnly(
            getComputedStyle(wrapper).transform
          ).m41;
          return translate < -1 && translate > {closed_translate + 1};
        }}""",
        polling="raf",
        timeout=TIMEOUT,
    )
    intermediate_close_box = wrapper.bounding_box()
    assert intermediate_close_box is not None
    assert (
        min(wrapper_box["x"], closed_box["x"])
        < intermediate_close_box["x"]
        < max(wrapper_box["x"], closed_box["x"])
    )


def test_rtl_closed_artifact_wrapper_stays_centered(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="default")
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


def test_relative_artifact_width_refreshes_without_layout_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app, artifact_width="relative")
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.get_by_role("button", name="Show artifact").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(layout).to_have_css("--shiny-chat-artifact-width", "512px")
    page.wait_for_timeout(220)
    initial_layout_box = layout.bounding_box()
    assert initial_layout_box is not None

    page.evaluate("document.documentElement.style.fontSize = '20px'")
    expect(layout).to_have_css("--shiny-chat-artifact-width", "640px")
    refreshed_layout_box = layout.bounding_box()
    assert refreshed_layout_box is not None
    assert refreshed_layout_box["width"] == pytest.approx(
        initial_layout_box["width"], abs=1
    )


def test_page_artifact_survives_navigation_and_history(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, shell = open_page(page, local_app)
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.get_by_role("button", name="Show artifact").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Initial artifact")

    page.get_by_role("button", name="Update artifact").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    artifact_input = panel.locator("#artifact_text")
    artifact_input.fill("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )

    shell.get_by_role("button", name="Details").click()
    expect(shell).to_have_attribute("data-active-page", "details")
    expect(chat.loc).to_be_hidden()
    expect(panel).to_be_hidden()
    expect(page.locator("#details_page")).to_be_visible()

    shell.get_by_role("button", name="Return to chat").click()
    expect(chat.loc).to_be_visible()
    expect(panel).to_be_visible()
    expect(artifact_input).to_have_value("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )

    chat.set_user_input("first conversation")
    chat.send_user_input()
    chat.expect_latest_message("echo: first conversation", timeout=TIMEOUT)

    sidebar = shell.locator(".shiny-chat-page-sidebar")
    toggle = shell.locator(".shiny-chat-page-sidebar-toggle")
    expect(sidebar).to_be_hidden()
    toggle.click()
    expect(sidebar).to_be_visible()
    expect(sidebar.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=TIMEOUT
    )

    sidebar.locator(".shiny-chat-history-new").click()
    expect(chat.loc_messages.locator("> *")).to_have_count(0, timeout=TIMEOUT)
    expect(panel).to_be_visible()
    expect(artifact_input).to_have_value("edited artifact")

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
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    expect(artifact_input).to_have_value("edited artifact")
    expect(panel.locator("#artifact_value")).to_have_text(
        "Artifact value: edited artifact",
        timeout=TIMEOUT,
    )


def test_artifact_motion_retains_close_panel_and_suppresses_resize(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    assert "--shiny-chat-artifact-layout-width" in layout.evaluate(
        "(element) => getComputedStyle(element).transitionProperty"
    )
    page.locator("#show_artifact").click()
    expect(panel).to_have_attribute("data-motion", "open")
    expect(layout).to_have_attribute("data-artifact-open", "")

    separator = page.get_by_role("separator", name="Resize artifact panel")
    separator.dispatch_event("resize-start")
    expect(layout).to_have_attribute("data-artifact-resizing", "")
    expect(layout).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close artifact").click()
    expect(panel).to_have_attribute("data-motion", "closing")
    expect(layout).not_to_have_attribute("data-artifact-resizing", "")
    expect(panel).to_have_attribute("aria-hidden", "true")
    assert panel.evaluate("(element) => element.hidden") is False
    expect(layout).to_have_attribute("data-artifact-open", "")
    expect(panel).to_be_hidden(timeout=TIMEOUT)
    expect(layout).not_to_have_attribute("data-artifact-open", "")


def test_artifact_layout_track_interpolates_during_desktop_reveal(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")

    page.locator("#show_artifact").click()
    expect(layout).to_have_attribute("data-artifact-open", "")
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
              "--shiny-chat-artifact-width"
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


def test_artifact_motion_respects_reduced_motion_and_takeover(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.emulate_media(reduced_motion="reduce")
    chat, _ = open_page(page, local_app)
    layout = chat.loc.locator(".shiny-chat-layout")
    panel = chat.loc.locator(".shiny-chat-artifact")
    wrapper = chat.loc.locator(".shiny-chat-wrapper")

    page.get_by_role("button", name="Show artifact").click()
    expect(layout).to_have_css("transition-duration", "0s")
    expect(panel).to_have_css("transition-duration", "0s")
    expect(wrapper).to_have_css("transition-duration", "0s")

    panel.get_by_role("button", name="Close artifact").click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)

    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 1024, "height": 900})
    page.locator("#show_artifact").click()
    expect(layout).to_have_attribute("data-artifact-takeover", "")
    expect(layout).to_have_css("transition-duration", "0s")
