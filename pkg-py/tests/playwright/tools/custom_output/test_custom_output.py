"""Coverage for Python's fully-custom tool UI path.

An author's `message_content_chunk` handler for their own `ContentToolResult`
subclass can return arbitrary UI instead of shinychat's tool card. That bypass
is streaming-only, so the app drives it through `chat.append_message_stream()`
(see `app.py`), not `chat.append_message()`.

Server-side, `_append_message_chunk` is expected to wrap that custom output in
a real `<shiny-tool-result custom-display>` so the client has an element to
pair against the request. Without that wrap, today's behavior leaves no
element to derive a "done" signal from, so the request row spins forever.
"""

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _run_tool_call(page: Page) -> None:
    page.click("#add_tool")
    expect(page.locator("#custom_tool_output")).to_be_visible(timeout=10_000)


def test_custom_tool_output_leaves_no_orphan_spinner(
    page: Page, local_app: ShinyAppProc
) -> None:
    """The tool request's spinner must disappear once the custom result
    lands -- a lingering spinner means the client never paired the result
    with its request."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _run_tool_call(page)

    expect(chat.loc.locator(".spinner-border")).not_to_be_attached(
        timeout=5_000
    )


def test_custom_tool_output_renders_outside_the_tool_group_row(
    page: Page, local_app: ShinyAppProc
) -> None:
    """The custom payload renders in a `.shiny-chat-tool-custom-display`
    wrapper, as a sibling after `.shiny-chat-tool-group` inside
    `.shiny-chat-tool-loop` -- never nested inside the tool group row itself."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _run_tool_call(page)

    custom_display = chat.loc.locator(".shiny-chat-tool-custom-display")
    expect(custom_display).to_be_visible(timeout=10_000)

    payload = custom_display.locator("#custom_tool_output")
    expect(payload).to_be_visible()

    # The payload must never end up nested inside the tool group row.
    nested_in_group = chat.loc.locator(
        ".shiny-chat-tool-group #custom_tool_output"
    )
    expect(nested_in_group).to_have_count(0)
