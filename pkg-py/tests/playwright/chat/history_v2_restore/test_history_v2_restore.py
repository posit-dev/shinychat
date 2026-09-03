from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, WebSocketRoute, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def _message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def _is_history_update(message: str | bytes) -> bool:
    return _action_type(message) == "history_update"


def _action_type(message: str | bytes) -> str | None:
    if not isinstance(message, str):
        return None
    try:
        payload = json.loads(message)
        action = payload["custom"]["shinyChatMessage"]["action"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    action_type = action.get("type")
    return action_type if isinstance(action_type, str) else None


def test_v2_restore_replays_turns_and_continues_provider_context(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("first question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(_message_count(page)).to_have_count(2, timeout=10_000)

    # The history drawer is the production synchronization point for the
    # browser's active conversation ID before the new session restores it.
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        1, timeout=10_000
    )
    page.keyboard.press("Escape")

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: first question", timeout=30_000)
    expect(_message_count(page)).to_have_count(2, timeout=10_000)
    controller.OutputText(page, "history_updates").expect_value(
        "1", timeout=10_000
    )

    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"first question"'), timeout=10_000
    )
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"echo: first question"'), timeout=10_000
    )
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"turn_count": 2'), timeout=10_000
    )
    controller.OutputText(page, "recorder").expect_value(
        re.compile(r'"node_count": 2'), timeout=10_000
    )

    chat.set_user_input("second question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second question", timeout=30_000)
    expect(_message_count(page)).to_have_count(4, timeout=10_000)
    controller.OutputText(page, "provider_context").expect_value(
        "[first question] | [echo: first question] | second question",
        timeout=10_000,
    )
    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"turn_count": 4'), timeout=10_000
    )
    controller.OutputText(page, "recorder").expect_value(
        re.compile(r'"node_count": 3'), timeout=10_000
    )


def test_v2_switch_replays_the_active_conversation(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("conversation A")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: conversation A", timeout=30_000)

    page.locator(".shiny-chat-history-trigger").click()
    expect(
        page.locator(".shiny-chat-history-item", has_text="conversation A")
    ).to_have_count(1, timeout=10_000)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    chat.set_user_input("conversation B")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: conversation B", timeout=30_000)

    page.locator(".shiny-chat-history-trigger").click()
    page.locator(".shiny-chat-history-item", has_text="conversation A").click()
    chat.expect_latest_message("echo: conversation A", timeout=30_000)

    page.locator(".shiny-chat-history-trigger").click()
    page.locator(".shiny-chat-history-item", has_text="conversation B").click()
    chat.expect_latest_message("echo: conversation B", timeout=30_000)
    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "recorder").expect_value(
        re.compile(r'"node_count": 2'), timeout=10_000
    )


def test_v2_edit_projects_once_through_the_real_provider_and_preserves_draft(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A v2 edit reaches the normal raw-input/provider path exactly once."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("original")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: original", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("1")
    controller.OutputText(page, "accepted_submissions").expect_value("1")

    replacement_attachment = HERE / "replacement.txt"
    draft_attachment = HERE / "draft.txt"
    page.set_input_files(
        ".shiny-chat-composer input[type=file]",
        str(draft_attachment),
    )
    chat.set_user_input("unrelated draft")
    expect(chat.loc_input).to_have_text("unrelated draft")
    expect(
        page.locator(".shiny-chat-composer .shiny-chat-input-attachments > *")
    ).to_have_count(1)

    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    edit_box = original.locator(".shiny-chat-edit-box")
    edit_box.locator("input[type=file]").set_input_files(
        str(replacement_attachment)
    )
    editor = original.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("replacement")
    original.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("echo: replacement", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("2")
    controller.OutputText(page, "accepted_submissions").expect_value("2")
    controller.OutputText(page, "provider_attachment_counts").expect_value(
        "0,1"
    )
    controller.OutputText(page, "accepted_attachment_counts").expect_value(
        "0,1"
    )
    controller.OutputText(page, "provider_attachment_names").expect_value(
        "replacement.txt"
    )
    controller.OutputText(page, "accepted_attachment_names").expect_value(
        "replacement.txt"
    )

    replacement = page.locator(".shiny-chat-user-message").first
    expect(replacement.locator("p")).to_have_text("replacement")
    expect(chat.loc_input).to_have_text("unrelated draft")
    expect(
        page.locator(".shiny-chat-composer .shiny-chat-input-attachments > *")
    ).to_have_count(1)

    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: unrelated draft", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("3")
    controller.OutputText(page, "accepted_submissions").expect_value("3")
    controller.OutputText(page, "provider_attachment_counts").expect_value(
        "0,1,1"
    )
    controller.OutputText(page, "accepted_attachment_counts").expect_value(
        "0,1,1"
    )
    controller.OutputText(page, "provider_attachment_names").expect_value(
        "replacement.txt,draft.txt"
    )
    controller.OutputText(page, "accepted_attachment_names").expect_value(
        "replacement.txt,draft.txt"
    )


def test_v2_restored_failure_retries_through_the_real_provider(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("retry me")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    expect(page.locator(".shiny-chat-user-message")).to_have_count(
        1, timeout=30_000
    )
    expect(page.locator(".shiny-chat-message")).to_have_count(0, timeout=10_000)

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    retry = page.get_by_role("button", name="Retry message")
    expect(retry).to_be_visible(timeout=10_000)
    retry.press("Enter")

    chat.expect_latest_message("echo: retry me", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("1")
    controller.OutputText(page, "accepted_submissions").expect_value("1")
    expect(page.locator(".shiny-chat-user-message")).to_have_count(1)


def test_v2_navigation_replays_the_selected_sibling_and_continues_from_it(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("original")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: original", timeout=30_000)

    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    editor = original.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("replacement")
    original.locator(".shiny-chat-btn-send").click()
    chat.expect_latest_message("echo: replacement", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("2")

    replacement = page.locator(".shiny-chat-user-message").first
    replacement.hover()
    replacement.get_by_role("button", name="Previous version").click()
    chat.expect_latest_message("echo: original", timeout=30_000)
    expect(page.locator(".shiny-chat-user-message").first).to_contain_text(
        "original", timeout=10_000
    )
    controller.OutputText(page, "provider_calls").expect_value("2")

    controller.InputActionButton(page, "inspect_turns").click()
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"turn_count": 2'), timeout=10_000
    )
    controller.OutputText(page, "turns").expect_value(
        re.compile(r'"original"'), timeout=10_000
    )
    expect(page.locator(".shiny-chat-messages-content")).not_to_contain_text(
        "replacement", timeout=10_000
    )

    # The persisted selected-child path survives reload and supplies the
    # exact model prefix for the next ordinary provider submission.
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: original", timeout=30_000)
    chat.set_user_input("continued")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: continued", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("1")
    controller.OutputText(page, "provider_context").expect_value(
        "[original] | [echo: original] | continued",
        timeout=10_000,
    )


def test_v2_restore_holds_retry_edit_and_navigation_until_history_release(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    # Create a failed exchange, then edit it into a sibling. Restore the
    # original failed sibling so its error/retry and sibling metadata share
    # the same restored v2 path.
    chat.set_user_input("held retry")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    failed = page.locator(".shiny-chat-user-message").first
    expect(failed).to_contain_text("held retry", timeout=30_000)
    expect(page.locator(".shiny-chat-message")).to_have_count(0, timeout=10_000)

    failed.hover()
    failed.locator(".shiny-chat-edit-btn").click()
    editor = failed.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("first sibling")
    failed.locator(".shiny-chat-btn-send").click()
    chat.expect_latest_message("echo: first sibling", timeout=30_000)

    first_sibling = page.locator(".shiny-chat-user-message").first
    first_sibling.hover()
    first_sibling.get_by_role("button", name="Previous version").click()
    failed = page.locator(".shiny-chat-user-message").first
    expect(failed).to_contain_text("held retry", timeout=30_000)
    expect(page.get_by_role("button", name="Retry message")).to_be_visible()

    held_history_updates: list[str | bytes] = []
    client_routes: list[WebSocketRoute] = []
    restored_action_types: list[str] = []

    def hold_first_history_update(route: WebSocketRoute) -> None:
        server = route.connect_to_server()
        client_routes.append(route)
        route.on_message(server.send)

        def forward_from_server(message: str | bytes) -> None:
            action_type = _action_type(message)
            if action_type is not None:
                restored_action_types.append(action_type)
            if not held_history_updates and _is_history_update(message):
                held_history_updates.append(message)
            else:
                route.send(message)

        server.on_message(forward_from_server)

    page.route_web_socket(re.compile(r".*"), hold_first_history_update)
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(page.locator(".shiny-chat-messages-content")).to_contain_text(
        "held retry", timeout=30_000
    )
    controller.OutputText(page, "history_updates").expect_value(
        "1", timeout=30_000
    )
    assert len(client_routes) == 1
    assert len(held_history_updates) == 1
    assert restored_action_types.index("update_exchange_metadata") < (
        restored_action_types.index("history_update")
    )
    assert restored_action_types.index("update_siblings") < (
        restored_action_types.index("history_update")
    )

    # The restored branch controls cannot dispatch before the authoritative
    # initial update: retry/edit are withheld, and the real valid direction
    # remains visible but disabled.
    failed = page.locator(".shiny-chat-user-message").first
    next_version = failed.get_by_role("button", name="Next version")
    expect(next_version).to_be_visible()
    expect(next_version).to_be_disabled()
    expect(page.get_by_role("button", name="Retry message")).to_have_count(0)
    expect(failed.locator(".shiny-chat-edit-btn")).to_have_count(0)
    next_version.click(force=True)
    controller.OutputText(page, "provider_calls").expect_value("0")
    controller.OutputText(page, "accepted_submissions").expect_value("0")
    controller.OutputText(page, "history_updates").expect_value("1")

    client_routes[0].send(held_history_updates.pop())
    retry = page.get_by_role("button", name="Retry message")
    expect(retry).to_be_visible(timeout=30_000)
    expect(retry).to_be_enabled()
    failed = page.locator(".shiny-chat-user-message").first
    failed.hover()
    edit = failed.locator(".shiny-chat-edit-btn")
    expect(edit).to_be_visible()
    expect(edit).to_be_enabled()
    next_version = failed.get_by_role("button", name="Next version")
    expect(next_version).to_be_enabled()

    retry.click()
    chat.expect_latest_message("echo: held retry", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("1")
    controller.OutputText(page, "accepted_submissions").expect_value("1")

    failed = page.locator(".shiny-chat-user-message").first
    failed.hover()
    failed.locator(".shiny-chat-edit-btn").click()
    editor = failed.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("edited retry")
    failed.locator(".shiny-chat-btn-send").click()
    chat.expect_latest_message("echo: edited retry", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("2")
    controller.OutputText(page, "accepted_submissions").expect_value("2")

    edited = page.locator(".shiny-chat-user-message").first
    edited.hover()
    previous = edited.get_by_role("button", name="Previous version")
    expect(previous).to_be_enabled()
    previous.click()
    expect(page.locator(".shiny-chat-messages-content")).to_contain_text(
        "held retry", timeout=30_000
    )


@pytest.mark.parametrize("local_app", ["app_bookmark.py"], indirect=True)
def test_v2_server_bookmarks_restore_distinct_sibling_leaves(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("original bookmark")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: original bookmark", timeout=30_000)
    page.wait_for_url(lambda url: "_state_id_=" in url, timeout=10_000)
    original_url = page.url

    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    editor = original.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("replacement bookmark")
    original.locator(".shiny-chat-btn-send").click()
    chat.expect_latest_message("echo: replacement bookmark", timeout=30_000)
    page.wait_for_url(
        lambda url: "_state_id_=" in url and url != original_url, timeout=10_000
    )
    replacement_url = page.url

    page.goto(original_url)
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: original bookmark", timeout=30_000)
    expect(page.locator(".shiny-chat-messages-content")).not_to_contain_text(
        "replacement bookmark", timeout=10_000
    )

    page.goto(replacement_url)
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: replacement bookmark", timeout=30_000)
    expect(page.locator(".shiny-chat-messages-content")).not_to_contain_text(
        "original bookmark", timeout=10_000
    )


@pytest.mark.parametrize("local_app", ["app_url.py"], indirect=True)
def test_v2_url_restore_publishes_one_history_update(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("url restore")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: url restore", timeout=30_000)
    page.wait_for_url(
        lambda url: "shinychat_conversation_id=" in url, timeout=10_000
    )
    restore_url = page.url

    page.goto(restore_url)
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("echo: url restore", timeout=30_000)
    controller.OutputText(page, "history_updates").expect_value(
        "1", timeout=10_000
    )
