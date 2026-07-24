from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_web_asides(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    message_state = controller.OutputCode(page, "message_state")

    message_state.expect_value("()", timeout=30 * 1000)
    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    expect(chat.loc_input_button).to_be_disabled()

    chat.set_user_input("tell me about e-bike motors")
    chat.send_user_input()

    # Wait for the stream to finish: two aside groups should appear.
    groups = page.locator(".shiny-aside-group")
    expect(groups).to_have_count(2, timeout=30 * 1000)

    # First group: two asides sharing one sentence, different labels →
    # labeled chip (first source's label) with a "+1" overflow.
    first = groups.nth(0)
    expect(first.locator(".shiny-aside-pill__label")).to_have_text("eBicycles")
    expect(first.locator(".shiny-aside-pill__overflow")).to_have_text("+1")

    # Clicking the pill opens the popover on the first source. The popover
    # renders through a portal (attached to document.body), so it is not a
    # descendant of the group — locate it from the page. Only one popover is
    # open at a time, so this resolves unambiguously.
    first.locator(".shiny-aside-pill").click()
    popover = page.locator(".shiny-aside-popover")
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("eBicycles")
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("1 / 2")

    # Paging to the second source.
    popover.get_by_role("button", name="Next source").click()
    expect(popover).to_contain_text("WIRED")
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("2 / 2")

    # Second group: a bare, label-less developer-authored aside → falls
    # back to a plain count pill (no chip, no favicon).
    second = groups.nth(1)
    expect(second.locator(".shiny-aside-pill--count")).to_have_text("1")
    second.locator(".shiny-aside-pill").click()

    # The label-less aside carries a rich block body (a list) in its
    # popover.
    second_popover = page.locator(".shiny-aside-popover")
    expect(second_popover).to_contain_text("Methodology")
    expect(second_popover).to_contain_text("40 commuter e-bike models")
    expect(second_popover).to_contain_text("released in 2024")


def test_web_aside_symmetric_padding_when_favicon_fails(
    page: Page, local_app: ShinyAppProc
) -> None:
    # A labeled aside whose favicon fails to load shows no icon, so its
    # pill must keep symmetric padding — not the reduced start padding
    # reserved for pills that actually display an icon. The failed <img> must
    # be removed from the DOM (not merely hidden) so `:has(img)` reflects
    # actual icon visibility.
    page.route("**/icons.duckduckgo.com/**", lambda route: route.abort())
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    chat.set_user_input("tell me about e-bike motors")
    chat.send_user_input()

    pill = page.locator(".shiny-aside-group").first.locator(".shiny-aside-pill")
    expect(pill.locator(".shiny-aside-pill__label")).to_have_text(
        "eBicycles", timeout=30 * 1000
    )
    expect(pill.locator("img")).to_have_count(0)

    padding = pill.evaluate(
        "el => { const s = getComputedStyle(el);"
        " return [s.paddingLeft, s.paddingRight]; }"
    )
    assert padding[0] == padding[1], (
        f"expected symmetric padding for iconless pill, got {padding}"
    )
