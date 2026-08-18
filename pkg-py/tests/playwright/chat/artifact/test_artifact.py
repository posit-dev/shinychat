from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

TIMEOUT = 30_000


def open_chat(
    page: Page,
    local_app: ShinyAppProc,
    *,
    viewport: tuple[int, int],
) -> ChatController:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=TIMEOUT)
    return chat


def chat_input(chat: ChatController):
    return chat.loc.get_by_role("textbox", name="Chat message")


def test_artifact_desktop_transport_and_rebinding(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_chat(page, local_app, viewport=(1440, 900))

    page.locator("#show_artifact").click()
    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Initial artifact")
    expect(panel.locator(".artifact-content-label")).to_have_text(
        "Initial content"
    )
    marker = panel.locator(".artifact-dependency-marker")
    expect(marker).to_have_css("border-top-color", "rgb(24, 119, 242)")
    expect(chat_input(chat)).to_be_visible()
    expect(
        page.get_by_role("separator", name="Resize artifact panel")
    ).to_be_visible()

    wrapper = chat.loc.locator(".shiny-chat-wrapper")
    wrapper_box = wrapper.bounding_box()
    panel_box = panel.bounding_box()
    assert wrapper_box is not None
    assert panel_box is not None
    assert panel_box["x"] >= wrapper_box["x"] + wrapper_box["width"]

    artifact_input = page.locator("#artifact_text")
    expect(artifact_input).to_be_visible()
    artifact_input.fill("desktop value")
    expect(page.locator("#artifact_echo")).to_have_text(
        "Echo: desktop value",
        timeout=TIMEOUT,
    )

    page.locator("#update_artifact").click()
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    expect(panel.locator(".artifact-content-label")).to_have_text(
        "Updated content"
    )
    expect(marker).to_have_css("border-top-color", "rgb(24, 119, 242)")
    expect(artifact_input).to_have_value("Updated")
    artifact_input.fill("rebound value")
    expect(page.locator("#artifact_echo")).to_have_text(
        "Echo: rebound value",
        timeout=TIMEOUT,
    )

    page.locator("#hide_artifact").click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)

    page.locator("#show_preserved").click()
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(panel.get_by_role("heading")).to_have_text("Updated artifact")
    expect(artifact_input).to_have_value("rebound value")


def test_artifact_takeover_focus_and_close(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_chat(page, local_app, viewport=(800, 900))
    input_loc = chat_input(chat)
    input_loc.focus()
    expect(input_loc).to_be_focused()

    # A programmatic click keeps focus in the chat while exercising the real
    # server-side action and Shiny transport path.
    page.locator("#show_artifact").evaluate("(button) => button.click()")

    panel = page.get_by_role("complementary")
    expect(panel).to_be_visible(timeout=TIMEOUT)
    expect(chat.loc.locator(".shiny-chat-wrapper")).to_be_hidden()
    back = page.get_by_role("button", name="Back to chat")
    expect(back).to_be_visible()
    expect(back).to_be_focused()

    back.click()
    expect(panel).to_be_hidden(timeout=TIMEOUT)
    expect(chat.loc.locator(".shiny-chat-wrapper")).to_be_visible()
    expect(input_loc).to_be_focused()
