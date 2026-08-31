from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent


def open_drawer(page: Page) -> None:
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def start_transition(page: Page, operation: str) -> None:
    open_drawer(page)
    if operation == "new":
        page.locator(".shiny-chat-history-new").click()
        return

    page.locator(".shiny-chat-history-itemmenu button").first.click()
    page.locator(".shiny-chat-history-menu").get_by_role(
        "button", name="Delete", exact=True
    ).click()
    page.locator(".shiny-chat-history-confirm").get_by_role(
        "button", name="Confirm delete"
    ).click()


def remount_chat(page: Page) -> None:
    page.locator("#chat").evaluate(
        """element => {
            const parent = element.parentElement;
            element.remove();
            setTimeout(() => parent?.appendChild(element), 25);
        }"""
    )
    expect(page.locator("#chat")).to_be_visible(timeout=10_000)


@pytest.mark.parametrize("operation", ["new", "delete"])
def test_active_history_transition_preserves_draft_until_explicit_resubmit(
    page: Page, local_app: ShinyAppProc, operation: str
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("seed")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: seed", timeout=30_000)
    controller.OutputText(page, "submissions").expect_value("1")

    start_transition(page, operation)
    chat.set_user_input("draft")
    page.set_input_files("input[type=file]", str(HERE / "draft.txt"))

    expect(chat.loc_input).to_have_text("draft")
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    expect(
        chat.loc.locator(".shiny-chat-messages-content")
    ).not_to_contain_text("draft")
    controller.OutputText(page, "submissions").expect_value("1")

    expect(chat.loc_input).to_have_text("draft", timeout=10_000)
    expect(page.locator(".shiny-chat-input-attachments")).to_have_count(1)
    expect(page.get_by_role("button", name="Send message")).to_have_attribute(
        "data-state", "ready", timeout=10_000
    )

    page.keyboard.press("Escape")
    page.get_by_role("button", name="Remove draft.txt").click()
    chat.loc_input.click()
    page.keyboard.press("End")
    page.keyboard.insert_text(" ")
    page.keyboard.press("Backspace")
    expect(page.get_by_role("button", name="Send message")).to_be_enabled()
    page.get_by_role("button", name="Send message").click()
    controller.OutputText(page, "submissions").expect_value("2", timeout=30_000)


def test_remount_stale_completion_cannot_clear_new_marker(
    page: Page, local_app: ShinyAppProc
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("seed")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: seed", timeout=30_000)
    controller.OutputText(page, "submissions").expect_value("1")

    # Start a real active New transition, then unmount/re-mount the custom
    # element while its server handler is awaiting persistence.
    start_transition(page, "new")
    controller.OutputText(page, "transition_events").expect_value(
        re.compile(r"new-started"), timeout=10_000
    )
    remount_chat(page)

    # The first transition publishes completion-v1 to the remounted store.
    controller.OutputText(page, "transition_events").expect_value(
        "new-started,new-finished", timeout=30_000
    )

    # Create an active conversation again, then start a second New transition.
    # The fixture sends the first request's completion while this second
    # marker is pending, making it a genuine stale completion.
    chat.set_user_input("after-remount")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: after-remount", timeout=30_000)
    controller.OutputText(page, "submissions").expect_value("2")

    start_transition(page, "new")
    chat.set_user_input("blocked-by-new")
    chat.send_user_input(method="enter")
    controller.OutputText(page, "transition_events").expect_value(
        re.compile(
            r"new-started,new-finished,stale-completion-sent,new-started"
        ),
        timeout=30_000,
    )

    # The stale completion must not release the second marker. The attempted
    # input remains client-side and is not counted by the server.
    controller.OutputText(page, "transition_events").expect_value(
        "new-started,new-finished,stale-completion-sent,new-started,new-finished",
        timeout=30_000,
    )
    controller.OutputText(page, "submissions").expect_value("2")

    chat.send_user_input(method="enter")
    controller.OutputText(page, "submissions").expect_value("3", timeout=30_000)
    chat.expect_latest_message("echo: blocked-by-new", timeout=30_000)


@pytest.mark.parametrize(
    ("control_id", "protocol_label"),
    [
        ("protocol_absent", "absent"),
        ("protocol_unknown", "unknown"),
        ("protocol_withdrawn", "withdrawn"),
    ],
)
def test_legacy_transition_protocol_keeps_submission_usable(
    page: Page,
    local_app: ShinyAppProc,
    control_id: str,
    protocol_label: str,
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    chat.set_user_input("seed")
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: seed", timeout=30_000)
    controller.OutputText(page, "submissions").expect_value("1")

    page.locator(f"#{control_id}").click()
    controller.OutputText(page, "protocol_state").expect_value(protocol_label)

    start_transition(page, "new")
    chat.set_user_input(f"legacy-{protocol_label}")
    chat.send_user_input(method="enter")

    # Legacy New sends no request ID, so no client marker is persisted and
    # submission remains usable while the server transition is pending.
    controller.OutputText(page, "submissions").expect_value("2", timeout=30_000)
    chat.expect_latest_message(f"echo: legacy-{protocol_label}", timeout=30_000)
