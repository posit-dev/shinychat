from __future__ import annotations

import json
import re

from playwright.sync_api import Page, WebSocketRoute, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def _is_history_update(message: str | bytes) -> bool:
    if not isinstance(message, str):
        return False
    try:
        payload = json.loads(message)
        action = payload["custom"]["shinyChatMessage"]["action"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    return action.get("type") == "history_update"


def test_initial_history_update_blocks_and_preserves_draft_until_release(
    page: Page, local_app: ShinyAppProc
) -> None:
    held_history_updates: list[str | bytes] = []
    client_routes: list[WebSocketRoute] = []

    def hold_first_history_update(route: WebSocketRoute) -> None:
        server = route.connect_to_server()
        client_routes.append(route)
        route.on_message(server.send)

        def forward_from_server(message: str | bytes) -> None:
            if not held_history_updates and _is_history_update(message):
                held_history_updates.append(message)
            else:
                route.send(message)

        server.on_message(forward_from_server)

    page.route_web_socket(re.compile(r".*"), hold_first_history_update)
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    controller.OutputText(page, "history_updates_sent").expect_value(
        "1", timeout=30_000
    )
    assert len(client_routes) == 1
    assert len(held_history_updates) == 1

    chat.set_user_input("held draft")
    page.set_input_files(
        "input[type=file]",
        {
            "name": "draft.txt",
            "mimeType": "text/plain",
            "buffer": b"held draft",
        },
    )
    expect(chat.loc_input).to_have_text("held draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    expect(page.get_by_role("button", name="Send message")).to_be_disabled()

    # An attachment-only Enter cannot clear the staged upload or send while
    # the held update keeps the v2 transition protocol unresolved.
    chat.loc_input.click()
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.press("Backspace")
    chat.loc_input.press("Enter")
    expect(chat.loc_input).to_have_text("")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    controller.OutputText(page, "accepted_submissions").expect_value("0:0")

    chat.set_user_input("held draft")
    chat.loc_input.press("Enter")
    expect(chat.loc_input).to_have_text("held draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    page.locator("#held-submit-suggestion").click()
    expect(chat.loc_input).to_have_text("held draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    controller.OutputText(page, "accepted_submissions").expect_value("0:0")

    client_routes[0].send(held_history_updates.pop())
    expect(page.get_by_role("button", name="Send message")).to_be_enabled(
        timeout=30_000
    )
    expect(chat.loc_input).to_have_text("held draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    controller.OutputText(page, "accepted_submissions").expect_value("0:0")

    chat.send_user_input(method="click")
    controller.OutputText(page, "accepted_submissions").expect_value(
        "1:1", timeout=30_000
    )
