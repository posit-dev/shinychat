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

    page.locator("select#model-select").select_option("Opus")
    page.locator("select#reasoning-select").select_option("high")
    chat.set_user_input("Remember this exchange")
    chat.send_user_input()
    chat.expect_latest_message(
        "Opus [high] replied to your message: Remember this exchange"
    )
    expect(
        sidebar.locator(
            ".shiny-chat-page-sidebar-panel:not([hidden]) "
            ".shiny-chat-history-item"
        )
    ).to_have_count(1)
    history_section = sidebar.locator(
        ".shiny-chat-page-sidebar-panel:not([hidden]) "
        ".shiny-chat-history-section"
    )
    expect(history_section).to_be_visible()
    assert history_section.evaluate(
        "(element) => getComputedStyle(element).backgroundColor"
    ) == sidebar.evaluate("(element) => getComputedStyle(element).backgroundColor")


def test_navigation_example_mobile_menu_includes_home_link(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(local_app.url)
    shell = page.locator("shiny-chat-page")
    home_link = shell.locator(".shiny-chat-page-home-link")
    chat = ChatController(page, "chat")

    expect(shell.locator(".shiny-chat-page-identity-title")).to_have_text(
        "Field notes"
    )
    chat.set_user_input("keep the mobile home link")
    chat.send_user_input()
    chat.expect_latest_message(
        "Sonnet [med] replied to your message: keep the mobile home link"
    )
    shell.locator(".shiny-chat-page-sidebar-toggle").click()
    expect(home_link).to_be_visible()
    expect(home_link).to_have_text("Field notes")
    home_box = home_link.bounding_box()
    sidebar_box = shell.locator(".shiny-chat-page-sidebar").bounding_box()
    sources_box = shell.get_by_role("button", name="Sources").bounding_box()
    assert home_box is not None
    assert sidebar_box is not None
    assert sources_box is not None
    assert home_box["y"] >= sidebar_box["y"]
    assert home_box["y"] + home_box["height"] <= sidebar_box["y"] + sidebar_box["height"]
    assert home_box["y"] + home_box["height"] <= sources_box["y"]

    shell.get_by_role("button", name="Sources").click()
    expect(shell).to_have_attribute("data-active-page", "Sources")

    shell.locator(".shiny-chat-page-sidebar-toggle").click()
    home_link.click()
    expect(shell).to_have_attribute("data-active-page", "home")


def test_navigation_example_mobile_artifact_trigger_does_not_overlay_messages(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    trigger = chat.loc.locator(".shiny-chat-artifact-trigger")
    scroll = chat.loc.locator(".shiny-chat-messages")
    greeting = chat.loc.locator(".shiny-chat-greeting")

    expect(chat.loc).to_be_visible()
    expect(trigger).to_be_visible()
    expect(greeting).to_be_visible()
    expect(scroll).to_have_css("padding-top", "48px")
    trigger_box = trigger.bounding_box()
    greeting_box = greeting.bounding_box()
    assert trigger_box is not None
    assert greeting_box is not None
    assert greeting_box["y"] >= trigger_box["y"] + trigger_box["height"]

    chat.set_user_input("hi there")
    chat.send_user_input()
    chat.expect_latest_message("Sonnet [med] replied to your message: hi there")

    expect(trigger).to_be_visible()
    expect(scroll).to_have_css("padding-top", "48px")


def test_navigation_example_shows_settings_offcanvas_from_global_toolbar(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    shell = page.locator("shiny-chat-page")
    settings_button = shell.locator("#show_settings")
    help_button = shell.locator("#help")

    expect(settings_button.locator("svg.bi-gear-fill")).to_be_visible()
    expect(help_button.locator("svg.bi-info-circle-fill")).to_be_visible()
    settings_button.click()

    offcanvas = page.locator("#answer_settings")
    expect(offcanvas).to_be_visible()
    expect(offcanvas.get_by_text("Answer settings", exact=True)).to_be_visible()
    expect(offcanvas.locator("#length")).to_be_visible()
    expect(offcanvas.locator("#citations")).to_be_visible()
    expect(offcanvas.get_by_role("button", name="Reset settings")).to_be_visible()


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
        "Sonnet [med] replied to your message: Check theme radius"
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
