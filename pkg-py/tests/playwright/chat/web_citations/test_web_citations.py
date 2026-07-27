from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_web_citations(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    message_state = controller.OutputCode(page, "message_state")

    message_state.expect_value("()", timeout=30 * 1000)
    expect(chat.loc).to_be_visible(timeout=30 * 1000)
    expect(chat.loc_input_button).to_be_disabled()

    chat.set_user_input("tell me about e-bike motors")
    chat.send_user_input()

    # Wait for the stream to finish: three aside groups should appear.
    groups = page.locator(".shiny-aside-group")
    expect(groups).to_have_count(3, timeout=30 * 1000)

    # First group: two web citations sharing one sentence, different
    # sources → labeled chip (auto-derived domain) with a "+1" overflow.
    first = groups.nth(0)
    expect(first.locator(".shiny-aside-pill__label")).to_have_text(
        "ebicycles.example"
    )
    expect(first.locator(".shiny-aside-pill__overflow")).to_have_text("+1")

    # Clicking the pill opens the popover on the first source. The popover
    # renders through a portal (attached to document.body), so it is not a
    # descendant of the group — locate it from the page.
    first.locator(".shiny-aside-pill").click()
    popover = page.locator(".shiny-aside-popover")
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("ebicycles.example")
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("1 / 2")

    # Paging to the second source.
    popover.get_by_role("button", name="Next source").click()
    expect(popover).to_contain_text("wired.example")
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("2 / 2")

    # Dismiss before interacting with the next pill: the portal-rendered
    # popover can visually overlap a later pill on the same line, which
    # would otherwise intercept the next click.
    page.keyboard.press("Escape")
    expect(popover).to_be_hidden()

    # Second group: a bare, label-less developer-authored aside → falls
    # back to a plain count pill (no chip, no favicon).
    second = groups.nth(1)
    expect(second.locator(".shiny-aside-pill--count")).to_have_text("1")
    second.locator(".shiny-aside-pill").click()
    second_popover = page.locator(".shiny-aside-popover")
    expect(second_popover).to_contain_text(
        "Measured across 40 commuter e-bike models"
    )
    page.keyboard.press("Escape")
    expect(second_popover).to_be_hidden()

    # Same source cited twice in one paragraph collapses to a single entry.
    third = groups.nth(2)
    third.locator(".shiny-aside-pill").click()
    popover = page.locator(".shiny-aside-popover")
    expect(popover).to_be_visible(timeout=10 * 1000)
    # A single entry has no "n / m" pager.
    expect(popover.locator(".shiny-aside-popover__count")).to_have_count(0)

    # End-of-message Sources summary pill: two distinct cited URLs across the
    # whole message (ebicycles cited twice + wired once); the hand-authored
    # aside is not a citation and is excluded.
    sources_pill = page.get_by_role("button", name="Sources, 2 sources")
    expect(sources_pill).to_be_visible()

    sources_pill.click()
    sources_popover = page.locator(".shiny-sources-popover")
    expect(sources_popover).to_be_visible()
    expect(sources_popover).to_contain_text("ebicycles.example")
    expect(sources_popover).to_contain_text("wired.example")
    expect(sources_popover.locator(".shiny-sources-item")).to_have_count(2)
