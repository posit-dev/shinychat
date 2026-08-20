from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _contrast_ratio(foreground: list[int], background: list[int]) -> float:
    def luminance(rgb: list[int]) -> float:
        red, green, blue = (
            value / 255 if value <= 10 else ((value / 255 + 0.055) / 1.055) ** 2.4
            for value in rgb
        )
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter, darker = sorted(
        (luminance(foreground), luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_navigation_example_saves_conversations(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    shell = page.locator("shiny-chat-page")
    sidebar = shell.locator(".shiny-chat-page-sidebar")
    expect(shell).to_be_visible()
    expect(chat.loc).to_be_visible()

    if sidebar.is_hidden():
        shell.locator(".shiny-chat-page-sidebar-toggle").click()
    expect(sidebar).to_be_visible()

    chat.set_user_input("Remember this exchange")
    chat.send_user_input()
    chat.expect_latest_message(
        "The assistant replied to your message: Remember this exchange"
    )
    expect(
        sidebar.locator(
            ".shiny-chat-page-sidebar-panel:not([hidden]) "
            ".shiny-chat-history-item"
        )
    ).to_have_count(1)


def test_navigation_example_history_new_button_meets_aa_contrast(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    new_button = page.locator(".shiny-chat-history-new").first

    for theme in ("light", "dark"):
        page.locator("html").evaluate(
            "(element, value) => element.setAttribute('data-bs-theme', value)",
            theme,
        )
        colors = new_button.evaluate(
            """(element) => {
              const styles = getComputedStyle(element);
              const parse = (color) =>
                color.match(/\\d+/g).slice(0, 3).map(Number);
              return {
                foreground: parse(styles.color),
                background: parse(styles.backgroundColor),
              };
            }"""
        )
        assert _contrast_ratio(colors["foreground"], colors["background"]) >= 4.5


def test_navigation_example_locally_themed_header_meets_aa_contrast(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    header = page.locator(".shiny-chat-page-header")

    for theme in ("light", "dark"):
        header.evaluate(
            "(element, value) => element.setAttribute('data-bs-theme', value)",
            theme,
        )
        colors = header.evaluate(
            """(element) => {
              const styles = getComputedStyle(element);
              const parse = (color) =>
                color.match(/\\d+/g).slice(0, 3).map(Number);
              return {
                foreground: parse(styles.color),
                background: parse(styles.backgroundColor),
              };
            }"""
        )
        assert _contrast_ratio(colors["foreground"], colors["background"]) >= 4.5


def test_navigation_example_chat_surfaces_follow_theme_radius(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    expected_radius = page.evaluate(
        """() => {
          const probe = document.createElement("div");
          probe.style.borderRadius = "var(--bs-border-radius)";
          document.body.append(probe);
          const radius = getComputedStyle(probe).borderRadius;
          probe.remove();
          return radius;
        }"""
    )

    suggestion = page.locator(".shiny-chat-suggestion-list-item").first
    expect(suggestion).to_be_visible()
    assert suggestion.evaluate(
        "(element) => getComputedStyle(element).borderRadius"
    ) == expected_radius

    chat = ChatController(page, "chat")
    chat.set_user_input("Check theme radius")
    chat.send_user_input()
    chat.expect_latest_message(
        "The assistant replied to your message: Check theme radius"
    )

    user_message = page.locator(".shiny-chat-user-message").last
    assert user_message.evaluate(
        "(element) => getComputedStyle(element).borderRadius"
    ) == expected_radius
    assert user_message.evaluate(
        """(element) => {
          const styles = getComputedStyle(element);
          return [styles.paddingBlock, styles.paddingInline];
        }"""
    ) == ["8px", "12px"]

    assistant_message = page.locator(".shiny-chat-message").last
    assert assistant_message.evaluate(
        "(element) => getComputedStyle(element).marginTop"
    ) == "-8px"
