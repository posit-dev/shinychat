from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def _message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def test_v2_restore_replays_turns_and_continues_provider_context(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("first question")
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


def test_v2_switch_replays_without_recapturing_the_active_tree(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("conversation A")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: conversation A", timeout=30_000)

    page.locator(".shiny-chat-history-trigger").click()
    expect(
        page.locator(".shiny-chat-history-item", has_text="conversation A")
    ).to_have_count(1, timeout=10_000)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")

    chat.set_user_input("conversation B")
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
    edit_box.locator("input[type=file]").set_input_files(str(replacement_attachment))
    editor = original.get_by_role("textbox", name="Chat message")
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially("replacement")
    original.locator(".shiny-chat-btn-send").click()

    chat.expect_latest_message("echo: replacement", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("2")
    controller.OutputText(page, "accepted_submissions").expect_value("2")
    controller.OutputText(page, "provider_attachment_counts").expect_value("0,1")
    controller.OutputText(page, "accepted_attachment_counts").expect_value("0,1")
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
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: continued", timeout=30_000)
    controller.OutputText(page, "provider_calls").expect_value("1")
    controller.OutputText(page, "provider_context").expect_value(
        "[original] | [echo: original] | continued",
        timeout=10_000,
    )


@pytest.mark.parametrize("local_app", ["app_bookmark.py"], indirect=True)
def test_v2_server_bookmarks_restore_distinct_sibling_leaves(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("original bookmark")
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
