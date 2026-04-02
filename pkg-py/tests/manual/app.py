"""
Manual test app for shinychat.

Run with: shiny run pkg-py/tests/manual/app.py

Test checklist:
  1. Streaming: Send "stream" -> see words appear one at a time with loading dots
  2. Markdown rendering: Send "markdown" -> verify headings, bold, code blocks, tables, lists
  3. External link dialog: Send "links" -> click the external link ->
     confirm dialog appears with Open Link / Cancel / Always open external links
  4. Input suggestions: Click suggestion chips in the welcome message ->
     verify text populates input (or auto-submits for the "submit" variant)
  5. Tool call cards: Click "Add tool result" button -> verify card renders,
     expands/collapses, and fullscreen works
  6. Custom icons: Send "icon" -> verify per-message icon override
  7. Code highlighting: Send "code" -> verify syntax-highlighted code block
  8. HTML content: Send "html" -> verify raw HTML renders correctly in assistant message
  9. Clear messages: Click "Clear messages" button -> verify all messages removed
  10. Update input: Click "Update input" -> verify input text and placeholder change
  11. Auto-scroll: Send "long" -> verify chat scrolls to bottom during streaming
  12. User input transform: Send anything with "secret" in it -> verify it gets redacted
"""

import asyncio

from shiny import reactive
from shiny.express import input, ui
from shiny.ui import HTML
from shinychat.express import Chat

ui.page_opts(title="shinychat Manual Test", fillable=True)

with ui.sidebar():
    ui.h4("Actions")
    ui.input_action_button("add_tool", "Add tool result card")
    ui.input_action_button("add_tool_fullscreen", "Add fullscreen tool result")
    ui.input_action_button("clear", "Clear messages")
    ui.input_action_button("update_input", "Update input")
    ui.hr()
    ui.h4("Instructions")
    ui.markdown(
        """
Type one of these keywords:
- **stream** - test streaming
- **markdown** - test markdown rendering
- **links** - test external link dialog
- **code** - test syntax highlighting
- **html** - test raw HTML content
- **long** - test auto-scroll with long stream
- **icon** - test per-message icon
- **error** - test error display
- anything with **secret** - test input transform
"""
    )

welcome_msg = """
Hello! This is a manual test app. Try the keywords in the sidebar,
or click one of these suggestions:

<span class="suggestion">Tell me about streaming</span> |
<span class="suggestion submit">Auto-submit suggestion</span> |
<span class="suggestion" data-suggestion="Custom suggestion text">Different display text</span>
"""

chat = Chat(id="chat")
chat.ui(
    messages=[welcome_msg],
    placeholder="Type a keyword to test a feature...",
)


@chat.transform_user_input
async def transform(input: str) -> str:
    return input.replace("secret", "[REDACTED]")


@chat.on_user_submit
async def handle_user_input(user_input: str):
    keyword = user_input.strip().lower()

    if keyword == "stream":
        words = "This response is being streamed word by word to test the streaming feature.".split()

        async def stream():
            for w in words:
                yield w + " "
                await asyncio.sleep(0.15)

        await chat.append_message_stream(stream())

    elif keyword == "markdown":
        md = """\
# Heading 1
## Heading 2

**Bold text** and *italic text* and `inline code`.

- Bullet 1
- Bullet 2
  - Nested bullet

1. Ordered item
2. Another item

> A blockquote with some wisdom.

| Column A | Column B | Column C |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |

---

A paragraph with a [relative link](#test) that should open normally,
and some ***bold italic*** text for good measure.
"""
        await chat.append_message(md)

    elif keyword == "links":
        await chat.append_message(
            "Here are some external links to test the dialog:\n\n"
            "- [Google](https://www.google.com)\n"
            "- [GitHub](https://github.com)\n"
            "- [Shiny for Python docs](https://shiny.posit.co/py/)\n\n"
            "Clicking any of these should show the external link confirmation dialog. "
            "Try 'Open Link', 'Cancel', and 'Always open external links'."
        )

    elif keyword == "code":
        await chat.append_message(
            "Here's some syntax-highlighted code:\n\n"
            "```python\n"
            "import asyncio\n"
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class ChatMessage:\n"
            '    role: str = "assistant"\n'
            "    content: str = \"\"\n\n"
            "async def stream_response(messages: list[ChatMessage]) -> str:\n"
            '    result = ""\n'
            "    for msg in messages:\n"
            "        await asyncio.sleep(0.1)\n"
            "        result += msg.content\n"
            "    return result\n"
            "```\n\n"
            "And some JavaScript:\n\n"
            "```javascript\n"
            "const chat = document.querySelector('shiny-chat-container');\n"
            "chat.addEventListener('click', (e) => {\n"
            "  console.log('clicked', e.target);\n"
            "});\n"
            "```"
        )

    elif keyword == "html":
        from htmltools import div, tags

        html_content = div(
            tags.strong("This is Shiny UI HTML"),
            " rendered via a ",
            tags.code("shinychat-html"),
            " island.",
            tags.ul(tags.li("Item A"), tags.li("Item B")),
            style="padding: 12px; border: 2px solid #4a90d9; border-radius: 8px; "
            "background: linear-gradient(135deg, #667eea22, #764ba222);",
        )
        await chat.append_message(html_content)

    elif keyword == "long":
        lines = [f"Line {i}: " + "lorem ipsum dolor sit amet " * 3 for i in range(1, 51)]

        async def long_stream():
            for line in lines:
                yield line + "\n\n"
                await asyncio.sleep(0.08)

        await chat.append_message_stream(long_stream())

    elif keyword == "icon":
        svg_icon = HTML(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
            'fill="currentColor" viewBox="0 0 16 16">'
            '<path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16m.93-9.412-1 4.705'
            "c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416"
            "c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468"
            'c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287z'
            'M8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/>'
            "</svg>"
        )
        await chat.append_message(
            "This message has a custom info-circle icon instead of the default robot.",
            icon=svg_icon,
        )

    elif keyword == "error":
        raise ValueError("This is a test error to verify error handling in the chat UI.")

    else:
        await chat.append_message(f"You said: {user_input}")


@reactive.effect
@reactive.event(input.add_tool)
async def _():
    # Tool elements must be passed as strings (not HTML()) so they go through
    # the React pipeline and are intercepted by bridge components.
    tool_str = (
        "<shiny-tool-request "
        'request-id="manual-req-1" '
        'tool-name="get_data" '
        'tool-title="Fetching Data" '
        'arguments=\'{"query": "SELECT * FROM users", "limit": 10}\' '
        ">"
        "</shiny-tool-request>"
        "<shiny-tool-result "
        'request-id="manual-req-1" '
        'tool-name="get_data" '
        'tool-title="Data Results" '
        'value="Found 10 rows matching your query. The data includes user IDs, names, and email addresses." '
        'value-type="text" '
        'status="success" '
        "expanded "
        ">"
        "</shiny-tool-result>"
    )
    await chat.append_message(tool_str)


@reactive.effect
@reactive.event(input.add_tool_fullscreen)
async def _():
    table_md = (
        "| ID | Name | Email |\\n"
        "|-----|------|-------|\\n"
        "| 1 | Alice | alice@example.com |\\n"
        "| 2 | Bob | bob@example.com |\\n"
        "| 3 | Carol | carol@example.com |"
    )
    tool_str = (
        "<shiny-tool-result "
        'request-id="manual-fs-1" '
        'tool-name="generate_report" '
        'tool-title="Report Output" '
        f'value="{table_md}" '
        'value-type="markdown" '
        'status="success" '
        "expanded "
        "full-screen "
        ">"
        "</shiny-tool-result>"
    )
    await chat.append_message(tool_str)


@reactive.effect
@reactive.event(input.clear)
async def _():
    await chat.clear_messages()


@reactive.effect
@reactive.event(input.update_input)
async def _():
    chat.update_user_input(
        value="Pre-filled text from server",
        placeholder="Placeholder was updated!",
        focus=True,
    )
