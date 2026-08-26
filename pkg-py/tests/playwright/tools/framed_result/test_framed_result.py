"""Browser coverage for framed rich tool result presentation."""

from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_app(page: Page, local_app: ShinyAppProc) -> ChatController:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    return chat


def add_result(page: Page, control_id: str) -> Locator:
    page.locator(control_id).click()
    loop = page.locator(".shiny-chat-tool-loop").last
    expect(loop).to_be_visible(timeout=10_000)
    return loop


def open_single_call(loop: Locator) -> None:
    loop.locator(".shiny-chat-tool-group__row").click()
    expect(loop.locator(".shiny-tool-card")).to_be_visible(timeout=5_000)


def border_widths(locator: Locator) -> list[str]:
    return locator.evaluate(
        """(el) => {
            const style = getComputedStyle(el);
            return [
                style.borderTopWidth,
                style.borderRightWidth,
                style.borderBottomWidth,
                style.borderLeftWidth,
                style.borderInlineStartWidth,
            ];
        }"""
    )


def test_framed_result_has_one_outer_frame_and_contained_footer(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A framed single result uses the group as its only normal-view card frame."""
    open_app(page, local_app)
    loop = add_result(page, "#add_framed")
    open_single_call(loop)

    frame = loop.locator(".shiny-chat-tool-group--framed")
    expect(frame).to_be_visible()
    assert (
        frame.evaluate("(el) => getComputedStyle(el).borderTopStyle") == "solid"
    )
    assert frame.locator(".shiny-tool-card").count() == 1
    assert frame.locator(".card-footer").count() == 1
    assert frame.locator(".card-footer").evaluate(
        "(el) => el.closest('.shiny-chat-tool-group--framed') !== null"
    )
    assert border_widths(frame.locator(".shiny-tool-card")) == ["0px"] * 5
    expect(frame.get_by_text("Recognizable framed body")).to_be_visible()
    expect(frame.get_by_text("Recognizable framed footer")).to_be_visible()


def test_framed_result_focus_visible_stays_inside_outer_frame(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Keyboard focus keeps the disclosure outline inside its clipped frame."""
    open_app(page, local_app)
    loop = add_result(page, "#add_framed")
    open_single_call(loop)

    summary = loop.locator(".shiny-chat-tool-group--framed > button")
    summary.focus()
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    assert summary.evaluate("(el) => el.matches(':focus-visible')")
    assert (
        summary.evaluate("(el) => getComputedStyle(el).outlineWidth") != "0px"
    )
    assert (
        summary.evaluate("(el) => getComputedStyle(el).outlineStyle") == "solid"
    )
    assert (
        summary.evaluate("(el) => getComputedStyle(el).outlineOffset") == "-2px"
    )


def test_grouped_result_frames_only_the_selected_framed_call(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A framed call in a multi-call group must not frame its default sibling."""
    open_app(page, local_app)
    loop = add_result(page, "#add_grouped")

    loop.locator(".shiny-chat-tool-group__row").click()
    framed_call = loop.locator("li", has_text="framed")
    default_call = loop.locator("li", has_text="default")
    framed_call.locator(".shiny-chat-tool-call-row__summary").click()

    group = loop.locator(".shiny-chat-tool-group")
    expect(framed_call).to_have_class(
        "shiny-chat-tool-call-row shiny-chat-tool-call-row--framed"
    )
    assert (
        framed_call.evaluate("(el) => getComputedStyle(el).borderTopStyle")
        == "solid"
    )
    assert (
        framed_call.evaluate("(el) => getComputedStyle(el).borderTopWidth")
        != "0px"
    )
    expect(default_call).to_have_class("shiny-chat-tool-call-row")
    assert border_widths(default_call) == ["0px"] * 5
    assert not group.evaluate(
        "(el) => el.classList.contains('shiny-chat-tool-group--framed')"
    )
    assert border_widths(group) == ["0px"] * 5
    expect(framed_call.locator(".shiny-tool-card")).to_be_visible()
    assert border_widths(framed_call.locator(".shiny-tool-card")) == ["0px"] * 5


def test_framed_fullscreen_result_keeps_leaf_overlay(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Fullscreen still applies to the leaf card after framed normal rendering."""
    open_app(page, local_app)
    loop = add_result(page, "#add_fullscreen")
    open_single_call(loop)

    frame = loop.locator(".shiny-chat-tool-group--framed")
    frame.locator(".tool-fullscreen-toggle").click()

    fullscreen_card = page.locator(".shiny-tool-card[fullscreen]")
    expect(fullscreen_card).to_be_visible(timeout=5_000)
    assert (
        fullscreen_card.evaluate("(el) => getComputedStyle(el).borderTopStyle")
        == "solid"
    )


def test_errored_framed_result_uses_default_error_presentation(
    page: Page, local_app: ShinyAppProc
) -> None:
    """An error requesting framed display must not receive framed classes."""
    open_app(page, local_app)
    loop = add_result(page, "#add_error")
    open_single_call(loop)

    expect(loop.locator(".shiny-chat-tool-group--framed")).to_have_count(0)
    expect(loop.locator(".shiny-chat-tool-call-row--framed")).to_have_count(0)
    expect(loop.get_by_text("Recognizable framed error")).to_be_visible()


def test_custom_result_bypasses_framed_tool_group(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Author-supplied standalone output takes precedence over framed display."""
    chat = open_app(page, local_app)
    add_result(page, "#add_custom")

    custom_display = chat.loc.locator(".shiny-chat-tool-custom-display")
    expect(custom_display).to_be_visible(timeout=10_000)
    expect(custom_display.locator("#custom-standalone-output")).to_be_visible()
    expect(chat.loc.locator(".shiny-chat-tool-group--framed")).to_have_count(0)
    expect(chat.loc.locator(".shiny-chat-tool-call-row--framed")).to_have_count(
        0
    )
