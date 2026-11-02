from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def submit_message(
    page: Page,
    local_app: ShinyAppProc,
    *,
    viewport: tuple[int, int] = (320, 480),
    text_scale: int = 200,
) -> Locator:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(local_app.url)
    page.evaluate(f"document.documentElement.style.fontSize = '{text_scale}%'")

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.set_user_input("go")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input()

    pill = page.locator(".shiny-aside-pill")
    expect(pill).to_be_visible(timeout=30_000)
    return pill


def test_long_aside_pill_has_a_bounded_desktop_width(
    page: Page, local_app: ShinyAppProc
) -> None:
    pill = submit_message(page, local_app, viewport=(1440, 900), text_scale=100)

    pill_box = pill.bounding_box()
    assert pill_box is not None
    assert pill_box["width"] <= 240


def test_long_aside_pill_stays_compact(
    page: Page, local_app: ShinyAppProc
) -> None:
    pill = submit_message(page, local_app)
    message = page.locator(".shiny-chat-message-content").last
    label = pill.locator(".shiny-aside-pill__label")

    pill_box = pill.bounding_box()
    message_box = message.bounding_box()
    assert pill_box is not None
    assert message_box is not None
    assert pill_box["height"] <= 64
    assert pill_box["width"] <= message_box["width"]

    label_layout = label.evaluate(
        """element => {
          const style = getComputedStyle(element);
          return {
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
            textOverflow: style.textOverflow,
            whiteSpace: style.whiteSpace,
          };
        }"""
    )
    assert label_layout["whiteSpace"] == "nowrap"
    assert label_layout["textOverflow"] == "ellipsis"
    assert label_layout["scrollWidth"] > label_layout["clientWidth"]


def test_long_aside_popover_keeps_body_in_view(
    page: Page, local_app: ShinyAppProc
) -> None:
    pill = submit_message(page, local_app)
    pill.click()

    popover = page.locator(".shiny-aside-popover")
    label = popover.locator(".shiny-aside-popover__label")
    body = popover.locator(".shiny-aside-popover__body")
    expect(popover).to_be_visible()
    expect(body).to_be_visible()

    popover_box = popover.bounding_box()
    label_box = label.bounding_box()
    body_box = body.bounding_box()
    assert popover_box is not None
    assert label_box is not None
    assert body_box is not None

    viewport = page.viewport_size
    assert viewport is not None
    assert popover_box["x"] >= 8
    assert popover_box["y"] >= 8
    assert popover_box["x"] + popover_box["width"] <= viewport["width"] - 8
    assert popover_box["y"] + popover_box["height"] <= viewport["height"] - 8

    font_size = float(
        label.evaluate("element => getComputedStyle(element).fontSize")[:-2]
    )
    assert label_box["height"] <= font_size * 3
    assert body_box["y"] < popover_box["y"] + popover_box["height"]


def test_long_aside_popover_scrolls_body_only(
    page: Page, local_app: ShinyAppProc
) -> None:
    pill = submit_message(page, local_app)
    pill.click()

    popover = page.locator(".shiny-aside-popover")
    label = popover.locator(".shiny-aside-popover__label")
    body = popover.locator(".shiny-aside-popover__body")
    expect(body).to_be_visible()

    label_box_before = label.bounding_box()
    assert label_box_before is not None

    layout = popover.evaluate(
        """(element) => {
          const body = element.querySelector(".shiny-aside-popover__body");
          return {
            popoverOverflowY: getComputedStyle(element).overflowY,
            bodyOverflowY: getComputedStyle(body).overflowY,
            bodyClientHeight: body.clientHeight,
            bodyScrollHeight: body.scrollHeight,
          };
        }"""
    )
    assert layout["popoverOverflowY"] == "hidden"
    assert layout["bodyOverflowY"] == "auto"
    assert layout["bodyScrollHeight"] > layout["bodyClientHeight"]

    body.evaluate("(element) => { element.scrollTop = 200; }")

    label_box_after = label.bounding_box()
    assert label_box_after is not None
    assert body.evaluate("(element) => element.scrollTop") > 0
    assert popover.evaluate("(element) => element.scrollTop") == 0
    assert label_box_after["y"] == label_box_before["y"]
