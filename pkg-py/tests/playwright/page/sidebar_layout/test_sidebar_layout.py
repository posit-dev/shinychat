from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc


def test_sidebar_resizer_uses_a_coarse_pointer_hit_target(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    session = page.context.new_cdp_session(page)
    session.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": True, "maxTouchPoints": 1},
    )
    page.set_viewport_size({"width": 800, "height": 700})
    page.goto(local_app.url)

    resizer = page.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible(timeout=30_000)
    expect(resizer).to_have_css("width", "26px")
    page.locator("shiny-chat-page").evaluate(
        "(element) => element.classList.add('shiny-chat-debug-resize-handle')"
    )
    debug_overlay = resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
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


def test_debug_resize_overlay_shows_sidebar_fine_targets(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    page.set_viewport_size({"width": 1200, "height": 700})
    page.goto(local_app.url)

    shell = page.locator("shiny-chat-page")
    resizer = shell.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible(timeout=30_000)
    production_overlay = resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert production_overlay == {
        "background": "rgba(0, 0, 0, 0)",
        "pointerEvents": "auto",
    }

    shell.evaluate(
        "(element) => element.classList.add('shiny-chat-debug-resize-handle')"
    )
    idle_overlay = resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert idle_overlay == {
        "width": 5,
        "background": "rgba(255, 193, 7, 0.28)",
        "pointerEvents": "auto",
    }
    indicator = resizer.locator("[data-shiny-chat-resize-indicator]")
    expect(indicator).to_be_visible()

    sidebar = shell.locator(".shiny-chat-page-sidebar")
    sidebar_box = sidebar.bounding_box()
    resizer_box = resizer.bounding_box()
    assert sidebar_box is not None
    assert resizer_box is not None
    boundary = sidebar_box["x"] + sidebar_box["width"]
    y = resizer_box["y"] + resizer_box["height"] / 2
    page.mouse.move(boundary + 4, y)
    page.mouse.move(boundary - 1, y)
    expect(resizer).to_have_attribute("data-boundary-armed", "")

    armed_overlay = resizer.evaluate(
        """(element) => {
          const style = getComputedStyle(element, "::after");
          return {
            width: Number.parseFloat(style.width),
            background: style.backgroundColor,
            pointerEvents: style.pointerEvents,
          };
        }"""
    )
    assert armed_overlay == {
        "width": 24,
        "background": "rgba(25, 135, 84, 0.3)",
        "pointerEvents": "auto",
    }

    indicator_box = indicator.bounding_box()
    assert indicator_box is not None
    page.mouse.move(
        indicator_box["x"] + indicator_box["width"] / 2,
        indicator_box["y"] + indicator_box["height"] / 2,
    )
    resizer.evaluate("(element) => element.removeAttribute('data-boundary-armed')")
    page.mouse.down()
    expect(resizer).to_have_attribute("data-resizing", "")
    page.mouse.up()


def test_sidebar_resizer_keeps_mouse_clicks_transparent_on_hybrid_devices(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    session = page.context.new_cdp_session(page)
    session.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": True, "maxTouchPoints": 1},
    )
    page.set_viewport_size({"width": 800, "height": 700})
    page.goto(local_app.url)

    shell = page.locator("shiny-chat-page")
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    resizer = shell.get_by_role("separator", name="Resize sidebar")
    expect(resizer).to_be_visible(timeout=30_000)
    sidebar.evaluate(
        """(element) => {
          element.dataset.resizeUnderlayClicks = "0";
          element.addEventListener("click", () => {
            element.dataset.resizeUnderlayClicks = String(
              Number(element.dataset.resizeUnderlayClicks) + 1
            );
          });
        }"""
    )

    resizer_box = resizer.bounding_box()
    assert resizer_box is not None
    page.mouse.click(
        resizer_box["x"] + resizer_box["width"] - 1,
        resizer_box["y"] + 100,
    )

    expect(sidebar).to_have_attribute("data-resize-underlay-clicks", "1")


def test_sidebar_clamps_to_page_and_supports_touch_drag(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
    session = page.context.new_cdp_session(page)
    session.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": True, "maxTouchPoints": 1},
    )
    page.set_viewport_size({"width": 800, "height": 700})
    page.goto(local_app.url)

    shell = page.locator("shiny-chat-page")
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    main = shell.locator(".shiny-chat-page-main")
    resizer = shell.get_by_role("separator", name="Resize sidebar")
    expect(shell).to_be_visible(timeout=30_000)
    expect(resizer).to_be_visible()

    shell_box = shell.bounding_box()
    sidebar_box = sidebar.bounding_box()
    main_box = main.bounding_box()
    assert shell_box is not None
    assert sidebar_box is not None
    assert main_box is not None
    assert sidebar_box["width"] == shell_box["width"] - 360
    assert main_box["width"] == 360
    assert resizer.evaluate(
        "(element) => getComputedStyle(element).touchAction"
    ) == ("none")

    resizer_box = resizer.bounding_box()
    assert resizer_box is not None
    start_x = resizer_box["x"] + resizer_box["width"] - 1
    touch_y = resizer_box["y"] + 100
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": "touchStart",
            "touchPoints": [{"x": start_x, "y": touch_y, "id": 7}],
        },
    )
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": "touchMove",
            "touchPoints": [{"x": start_x - 50, "y": touch_y, "id": 7}],
        },
    )
    session.send(
        "Input.dispatchTouchEvent",
        {
            "type": "touchMove",
            "touchPoints": [{"x": 0, "y": touch_y, "id": 7}],
        },
    )
    session.send(
        "Input.dispatchTouchEvent",
        {"type": "touchEnd", "touchPoints": []},
    )

    expect(sidebar).to_have_attribute("data-sidebar-width", "150px")
    resized_sidebar_box = sidebar.bounding_box()
    resized_main_box = main.bounding_box()
    assert resized_sidebar_box is not None
    assert resized_main_box is not None
    assert resized_sidebar_box["width"] == 150
    assert resized_main_box["width"] == 650
