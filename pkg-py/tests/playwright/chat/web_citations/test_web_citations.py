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
    first_paragraph = first.locator("xpath=ancestor::p[1]")
    first_grounded = first_paragraph.locator(".shiny-citation-grounded")
    expect(first_grounded).to_have_count(2)
    expect(first_grounded.nth(0)).to_have_attribute("data-active", "")
    expect(first_grounded.nth(1)).not_to_have_attribute("data-active", "")

    # Paging to the second source.
    popover.get_by_role("button", name="Next source").click()
    expect(popover).to_contain_text("wired.example")
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("2 / 2")
    expect(first_grounded.nth(0)).not_to_have_attribute("data-active", "")
    expect(first_grounded.nth(1)).to_have_attribute("data-active", "")

    # Dismiss before interacting with the next pill: the portal-rendered
    # popover can visually overlap a later pill on the same line, which
    # would otherwise intercept the next click.
    page.keyboard.press("Escape")
    expect(popover).to_be_hidden()
    expect(first_grounded.nth(1)).not_to_have_attribute("data-active", "")

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

    # Same source cited twice in one paragraph remains two local occurrences
    # so each grounded claim can be inspected independently.
    third = groups.nth(2)
    third.locator(".shiny-aside-pill").click()
    popover = page.locator(".shiny-aside-popover")
    expect(popover).to_be_visible(timeout=10 * 1000)
    expect(popover.locator(".shiny-aside-popover__count")).to_have_text("1 / 2")
    third_paragraph = third.locator("xpath=ancestor::p[1]")
    third_grounded = third_paragraph.locator(".shiny-citation-grounded")
    expect(third_grounded).to_have_count(2)
    expect(third_grounded.nth(0)).to_have_attribute("data-active", "")
    expect(third_grounded.nth(1)).not_to_have_attribute("data-active", "")

    popover.get_by_role("button", name="Next source").click()
    expect(third_grounded.nth(0)).not_to_have_attribute("data-active", "")
    expect(third_grounded.nth(1)).to_have_attribute("data-active", "")

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


# Two columns define the block: the chevron / rail / dot gutter, and the text
# column shared by the header label and the nested timeline rows.
COLUMN_CENTERS_JS = """
el => {
  const centerX = (r) => r.x + r.width / 2;
  const timeline = el.querySelector('.shiny-web-activity__timeline');
  const nodes = [...timeline.querySelectorAll('.shiny-web-activity__node')];
  const dots = nodes.map((node) => {
    const nodeRect = node.getBoundingClientRect();
    const dot = getComputedStyle(node, '::before');
    return nodeRect.x + parseFloat(dot.left) + parseFloat(dot.width) / 2;
  });
  // Each node draws its own rail segment; `content: none` means no segment.
  const rails = nodes.map((node) => {
    const nodeRect = node.getBoundingClientRect();
    const s = getComputedStyle(node, '::after');
    if (s.content === 'none') return null;
    const top = nodeRect.y + parseFloat(s.top);
    return {
      cx: nodeRect.x + parseFloat(s.left) + parseFloat(s.width) / 2,
      top,
      bottom: top + parseFloat(s.height),
    };
  });
  const dotCentersY = nodes.map((node) => {
    const nodeRect = node.getBoundingClientRect();
    const dot = getComputedStyle(node, '::before');
    return nodeRect.y + parseFloat(dot.top) + parseFloat(dot.height) / 2;
  });
  const header = el.querySelector('.shiny-web-activity__header');
  const labelNode = [...header.childNodes].find(
    (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim(),
  );
  const labelRange = document.createRange();
  labelRange.selectNode(labelNode);
  return {
    chevron: centerX(
      el.querySelector('.shiny-web-activity__chevron').getBoundingClientRect(),
    ),
    dots,
    dotCentersY,
    rails,
    headerLabelLeft: labelRange.getBoundingClientRect().x,
    rowLefts: nodes.map((node) => node.getBoundingClientRect().x),
    lastHasResults: !!nodes[nodes.length - 1].querySelector(
      '.shiny-web-activity__results',
    ),
  };
}
"""


def test_web_activity_timeline_alignment(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    chat.set_user_input("tell me about e-bike motors")
    chat.send_user_input()

    activity = page.locator(".shiny-web-activity").first
    header = activity.locator(".shiny-web-activity__header")
    expect(header).to_be_visible(timeout=30 * 1000)
    header.click()
    expect(activity.locator(".shiny-web-activity__timeline")).to_be_visible()

    centers = activity.evaluate(COLUMN_CENTERS_JS)

    # Sub-pixel layout means these will not be bit-identical; a half-pixel
    # budget still rules out the misalignment a reader can see.
    tolerance = 0.5

    dots = centers["dots"]
    rails = centers["rails"]
    assert dots, f"expected at least one timeline dot, got {centers}"

    # The chevron, every dot, and every rail segment share one column.
    column = centers["chevron"]
    labelled = [(f"dot[{i}]", d) for i, d in enumerate(dots)]
    labelled += [
        (f"rail[{i}]", r["cx"]) for i, r in enumerate(rails) if r is not None
    ]
    for name, value in labelled:
        assert abs(value - column) <= tolerance, (
            f"{name} center ({value}) is not on the chevron column ({column}): "
            f"{centers}"
        )

    # The nested rows hang off the same text column as the header label, so the
    # rail and dots sit in a gutter rather than staggering the text.
    label_left = centers["headerLabelLeft"]
    for i, row_left in enumerate(centers["rowLefts"]):
        assert abs(row_left - label_left) <= tolerance, (
            f"timeline row[{i}] left ({row_left}) is not on the header label "
            f"column ({label_left}): {centers}"
        )

    # Every rail segment spans exactly from its own dot to the next one, so the
    # rail never overshoots a dot or leaves a gap between rows.
    dot_ys = centers["dotCentersY"]
    for i, railseg in enumerate(rails[:-1]):
        assert railseg is not None, f"rail[{i}] should connect to dot[{i + 1}]"
        assert abs(railseg["top"] - dot_ys[i]) <= tolerance, (
            f"rail[{i}] starts at {railseg['top']}, not at dot[{i}] "
            f"({dot_ys[i]}): {centers}"
        )
        assert abs(railseg["bottom"] - dot_ys[i + 1]) <= tolerance, (
            f"rail[{i}] ends at {railseg['bottom']}, not at dot[{i + 1}] "
            f"({dot_ys[i + 1]}): {centers}"
        )

    # Nothing follows the last dot, so it only gets a rail when there is a
    # results panel for that rail to run alongside.
    assert not centers["lastHasResults"], (
        "this fixture's last timeline node is a one-line fetch row; update the "
        f"expectation below if that changes: {centers}"
    )
    assert rails[-1] is None, (
        f"last node has no results panel, so it should draw no rail: {centers}"
    )
