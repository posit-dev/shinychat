import re

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_escape_cancels_stream_before_closing_chat_modal(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    page.get_by_role("button", name="Open chat").click()

    modal = page.get_by_role("dialog")
    expect(modal).to_be_visible()
    expect(modal.get_by_role("heading", name="Chat modal")).to_be_visible()
    chat = ChatController(page, "chat")
    chat.set_user_input("Start streaming")
    chat.send_user_input(method="enter")

    expect(chat.loc_input_button).to_have_attribute("data-state", "cancel")
    chat.loc_input.focus()
    page.keyboard.press("Escape")

    expect(modal).to_have_class(re.compile(r"\bshow\b"))
    controller.OutputText(page, "cancel_received").expect_value("True")
    expect(chat.loc_input).to_be_focused()

    expect(chat.loc_input_button).to_have_attribute("data-state", "empty")
    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible()


def test_escape_closes_suggestion_before_cancelling_stream(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    page.get_by_role("button", name="Open chat").click()

    modal = page.get_by_role("dialog")
    expect(modal).to_be_visible()
    chat = ChatController(page, "chat")
    expect(chat.loc_input).to_have_attribute("aria-haspopup", "listbox")
    chat.set_user_input("Start streaming")
    chat.send_user_input(method="enter")
    expect(chat.loc_input_button).to_have_attribute("data-state", "cancel")

    chat.loc_input.focus()
    page.keyboard.type("/")
    palette = page.get_by_role("listbox", name="Slash commands")
    expect(palette).to_be_visible()

    page.keyboard.press("Escape")
    expect(palette).not_to_be_visible()
    controller.OutputText(page, "cancel_received").expect_value("False")
    expect(chat.loc_input_button).to_have_attribute("data-state", "cancel")
    expect(modal).to_have_class(re.compile(r"\bshow\b"))

    page.keyboard.press("Escape")
    controller.OutputText(page, "cancel_received").expect_value("True")
    expect(modal).to_have_class(re.compile(r"\bshow\b"))
