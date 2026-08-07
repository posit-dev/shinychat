from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def open_drawer(page: Page) -> None:
    expect(page.locator(".shiny-chat-history-trigger")).to_be_visible(
        timeout=30_000
    )
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_static_ui_is_visible_but_excluded_from_server_state(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30 * 1000)

    messages = page.locator("pre#messages.shiny-text-output")
    bookmark = page.locator("pre#bookmark.shiny-text-output")
    record = page.locator("pre#record.shiny-text-output")

    expect(chat.loc_messages).to_contain_text("static")
    expect(messages).to_have_text("[]")
    expect(bookmark).to_have_text("[]")
    expect(record).to_have_text("null")

    chat.set_user_input("first question")
    chat.send_user_input(method="enter")

    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(chat.loc_messages).to_contain_text("static")
    expect(messages).to_contain_text('"content": "first question"', timeout=10_000)
    expect(messages).not_to_contain_text("static")
    expect(bookmark).to_contain_text('"content": "first question"', timeout=10_000)
    expect(bookmark).not_to_contain_text("static")
    expect(record).to_contain_text('"content": "first question"', timeout=10_000)
    expect(record).not_to_contain_text("static")

    card = page.locator(".server-state-card")
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
    expect(page.locator(".shiny-chat-text-preview")).to_have_count(1)

    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    expect(chat.loc_messages).not_to_contain_text("static")

    open_drawer(page)
    page.locator(".shiny-chat-history-item").filter(
        has_text="first question"
    ).click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(card).to_have_css("border-color", "rgb(255, 0, 0)", timeout=5_000)
    expect(page.locator(".shiny-chat-text-preview")).to_have_count(1)
    expect(messages).not_to_contain_text("static")
    expect(record).to_contain_text('"content": "first question"', timeout=10_000)
    expect(record).not_to_contain_text("static")


def test_server_projection_commits_complete_and_streamed_messages(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    messages = page.locator("pre#messages.shiny-text-output")
    expect(messages).to_have_text("[]")

    page.locator("#append_complete").click()
    chat.expect_latest_message("complete server append", timeout=10_000)
    expect(messages).to_contain_text("complete server append", timeout=10_000)

    page.locator("#append_stream").click()
    stream_dot = chat.loc_messages.locator(".markdown-stream-dot")
    expect(stream_dot).to_be_visible(timeout=10_000)
    expect(chat.loc_messages).to_contain_text("streamed response", timeout=10_000)
    expect(messages).not_to_contain_text("streamed response")

    expect(messages).to_contain_text("streamed response", timeout=10_000)
    expect(stream_dot).to_have_count(0, timeout=10_000)

    page.locator("#clear_messages").click()
    expect(messages).to_have_text("[]", timeout=10_000)
    expect(
        chat.loc_messages.locator(
            ".shiny-chat-message, .shiny-chat-user-message"
        )
    ).to_have_count(0)


def test_forged_messages_input_cannot_change_server_transcript(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)

    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    messages = page.locator("pre#messages.shiny-text-output")
    bookmark = page.locator("pre#bookmark.shiny-text-output")
    record = page.locator("pre#record.shiny-text-output")

    chat.set_user_input("secure question")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: secure question", timeout=30_000)
    expect(record).to_contain_text("secure question", timeout=10_000)

    page.evaluate(
        """() => {
window.Shiny.setInputValue(
  "chat_messages:shinychat.messages",
  [{ role: "assistant", segments: [{ content: "forged", content_type: "html" }] }],
  { priority: "event" },
)
}"""
    )
    page.evaluate(
        """() => {
const forged = document.createElement("div")
forged.id = "forged-dom-message"
forged.textContent = "forged"
document.querySelector(".shiny-chat-messages-content")?.append(forged)
}"""
    )

    expect(page.locator("#forged-dom-message")).to_have_text("forged")
    expect(messages).not_to_contain_text("forged")
    expect(bookmark).not_to_contain_text("forged")
    expect(record).not_to_contain_text("forged")
