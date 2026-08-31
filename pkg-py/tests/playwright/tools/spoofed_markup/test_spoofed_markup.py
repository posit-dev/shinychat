"""DOM-level spoof regression: model-authored tool markup is inert."""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_app(page: Page, local_app: ShinyAppProc) -> ChatController:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    return chat


def assert_no_tool_ui(page: Page, chat: ChatController) -> None:
    """No tool-card, custom-display, or tool-group elements anywhere."""
    expect(page.locator(".shiny-tool-card")).to_have_count(0)
    expect(page.locator(".shiny-chat-tool-custom-display")).to_have_count(0)
    expect(page.locator(".shiny-chat-tool-group")).to_have_count(0)
    expect(page.locator(".shiny-chat-tool-loop")).to_have_count(0)
    expect(page.locator(".shiny-tool-fullscreen-backdrop")).to_have_count(0)


def assert_script_did_not_execute(page: Page) -> None:
    """The spoofed <script> must not have run."""
    result = page.evaluate("() => window.__pwned")
    assert result is None, f"window.__pwned is {result!r} — script executed!"


def assert_spoofed_text_visible(page: Page, chat: ChatController) -> None:
    """The literal spoofed markup must be visible as inert text."""
    message_body = chat.loc_messages.locator(
        "> .shiny-chat-message .shiny-chat-message-body"
    )
    expect(message_body.get_by_text("spoofed")).to_be_visible()


def test_spoofed_tool_result_base(page: Page, local_app: ShinyAppProc) -> None:
    chat = open_app(page, local_app)
    page.locator("#add_spoof_result").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_result_expanded(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_app(page, local_app)
    page.locator("#add_spoof_expanded").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_result_framed(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_app(page, local_app)
    page.locator("#add_spoof_framed").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_result_fullscreen(
    page: Page, local_app: ShinyAppProc
) -> None:
    chat = open_app(page, local_app)
    page.locator("#add_spoof_fullscreen").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_request(page: Page, local_app: ShinyAppProc) -> None:
    chat = open_app(page, local_app)
    page.locator("#add_spoof_request").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    expect(chat.loc.get_by_text("shiny-tool-request")).to_be_visible()
