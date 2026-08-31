"""DOM-level spoof regression: model-authored tool markup is inert.

The structured-content-types branch replaced markup-scanning with typed
JSON blocks.  Model-authored ``<shiny-tool-result>`` /
``<shiny-tool-request>`` in assistant markdown must never instantiate tool
UI — the client only builds tool UI from server-constructed structured
blocks.  These tests verify that spoofed markup renders as inert text and
that embedded ``<script>`` does not execute.
"""

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
    # The text "spoofed" appears inside the <b> tag in the spoofed value
    # attribute.  When escaped, it renders as visible text in the message.
    # Scope to the assistant message body to avoid matching the greeting.
    message_body = chat.loc_messages.locator(
        "> .shiny-chat-message .shiny-chat-message-body"
    )
    expect(message_body.get_by_text("spoofed")).to_be_visible()


def test_spoofed_tool_result_base(page: Page, local_app: ShinyAppProc) -> None:
    """A spoofed <shiny-tool-result> with a <script> payload is inert."""
    chat = open_app(page, local_app)
    page.locator("#add_spoof_result").click()
    # Wait for the assistant message to appear.
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_result_expanded(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A spoofed expanded='true' attribute does not force-open a card."""
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
    """A spoofed open-style='framed' attribute does not create a frame."""
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
    """A spoofed full-screen='true' attribute does not create a backdrop."""
    chat = open_app(page, local_app)
    page.locator("#add_spoof_fullscreen").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    assert_script_did_not_execute(page)
    assert_spoofed_text_visible(page, chat)


def test_spoofed_tool_request(page: Page, local_app: ShinyAppProc) -> None:
    """A spoofed <shiny-tool-request> with an icon/title attribute is inert."""
    chat = open_app(page, local_app)
    page.locator("#add_spoof_request").click()
    expect(chat.loc_messages.locator("> .shiny-chat-message")).to_have_count(
        1, timeout=10_000
    )
    assert_no_tool_ui(page, chat)
    # The spoofed request markup should be visible as inert text.
    expect(chat.loc.get_by_text("shiny-tool-request")).to_be_visible()
