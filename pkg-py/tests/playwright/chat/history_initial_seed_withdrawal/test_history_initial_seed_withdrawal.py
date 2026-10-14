from __future__ import annotations

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_history_disabled_update_withdraws_static_seed(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "disabled")
    expect(chat.loc).to_be_visible(timeout=30_000)
    controller.OutputText(page, "disabled_history_update").expect_value(
        "False", timeout=30_000
    )
    disabled_actions = (
        page.locator("#disabled_action_order").inner_text().split(",")
    )
    assert disabled_actions.index("message") < disabled_actions.index(
        "history_update"
    )
    chat.expect_latest_message("disabled constructor message")

    chat.set_user_input("disabled input")
    expect(chat.loc_input_button).to_be_enabled()
    chat.send_user_input(method="click")
    controller.OutputText(page, "disabled_submissions").expect_value(
        "1", timeout=30_000
    )
