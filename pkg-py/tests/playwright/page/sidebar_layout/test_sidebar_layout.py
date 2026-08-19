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
