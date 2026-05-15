import re

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _loc_greeting(chat: ChatController):
    return chat.loc.locator(".shiny-chat-greeting")


def _loc_greeting_content(chat: ChatController):
    return chat.loc.locator(".shiny-chat-greeting-content")


def _loc_suggestions(chat: ChatController):
    return _loc_greeting(chat).locator(".suggestion")


def test_greeting_appears_on_load(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    greeting = _loc_greeting(chat)
    expect(greeting).to_be_visible(timeout=10_000)
    expect(_loc_greeting_content(chat)).to_contain_text("Welcome to the Explainer")


def test_greeting_has_suggestion_cards(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    greeting = _loc_greeting(chat)
    expect(greeting).to_be_visible(timeout=10_000)

    suggestions = _loc_suggestions(chat)
    expect(suggestions).to_have_count(3)
    expect(suggestions.nth(0)).to_have_text("What is a closure?")
    expect(suggestions.nth(1)).to_have_text("Explain tidy evaluation")
    expect(suggestions.nth(2)).to_have_text("How does gradient descent work?")


def test_suggestion_click_fills_input(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)

    _loc_suggestions(chat).nth(0).click()
    chat.expect_user_input("What is a closure?")


def test_greeting_dismissed_on_user_message(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)

    chat.set_user_input("Hello")
    chat.send_user_input(method="enter")

    expect(_loc_greeting(chat)).not_to_be_visible(timeout=10_000)
    chat.expect_latest_message("You said: Hello", timeout=10_000)


def test_greeting_reappears_after_clear_chat(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)

    # Send a message to dismiss the greeting
    chat.set_user_input("Hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: Hello", timeout=10_000)
    expect(_loc_greeting(chat)).not_to_be_visible(timeout=10_000)

    # Clear chat (not greeting) — greeting should reappear
    page.locator("#clear_chat").click()
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)
    expect(_loc_greeting_content(chat)).to_contain_text("Welcome to the Explainer")


def test_clear_chat_and_greeting_regenerates(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)
    expect(_loc_greeting_content(chat)).to_contain_text("Welcome to the Explainer")

    # Send a message to dismiss
    chat.set_user_input("Hello")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: Hello", timeout=10_000)

    # Clear chat AND greeting — should get a new (different) greeting
    page.locator("#clear_chat_and_greeting").click()
    greeting = _loc_greeting(chat)
    expect(greeting).to_be_visible(timeout=10_000)
    expect(_loc_greeting_content(chat)).to_contain_text("Welcome Back")


def test_messages_gone_after_clear(page: Page, local_app: ShinyAppProc) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)

    # Send two messages
    chat.set_user_input("First")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: First", timeout=10_000)

    chat.set_user_input("Second")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("You said: Second", timeout=10_000)

    # Clear chat — messages should be gone, greeting reappears
    page.locator("#clear_chat").click()
    expect(_loc_greeting(chat)).to_be_visible(timeout=10_000)

    # No chat messages should be visible
    expect(chat.loc_messages.locator(".shiny-chat-message")).to_have_count(0, timeout=10_000)
