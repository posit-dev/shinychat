from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc


def test_sidebar_clamps_to_page_and_supports_touch_drag(
    page: Page,
    local_app: ShinyAppProc,
) -> None:
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

    start_x = sidebar_box["x"] + sidebar_box["width"]
    resizer.evaluate(
        """(element, startX) => {
          element.setPointerCapture = () => {};
          element.hasPointerCapture = () => false;
          const event = (type, clientX) => new PointerEvent(type, {
            bubbles: true,
            button: 0,
            clientX,
            isPrimary: true,
            pointerId: 7,
            pointerType: "touch",
          });
          element.dispatchEvent(event("pointerdown", startX));
          element.dispatchEvent(event("pointermove", startX - 1000));
          element.dispatchEvent(event("pointerup", startX - 1000));
        }""",
        start_x,
    )

    expect(sidebar).to_have_attribute("data-sidebar-width", "150px")
    resized_sidebar_box = sidebar.bounding_box()
    resized_main_box = main.bounding_box()
    assert resized_sidebar_box is not None
    assert resized_main_box is not None
    assert resized_sidebar_box["width"] == 150
    assert resized_main_box["width"] == 650
