import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def test_selected_branch_survives_worker_compaction_and_return_to_shiny(
    page: Page, local_app: ShinyAppProc
):
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.set_user_input("original")
    expect(chat.loc_input_button).to_be_enabled()
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: original")

    original = page.locator(".shiny-chat-user-message").first
    original.hover()
    original.locator(".shiny-chat-edit-btn").click()
    editor = original.get_by_role("textbox", name="Chat message")
    editor.fill("alternative")
    original.locator(".shiny-chat-btn-send").click()
    chat.expect_latest_message("echo: alternative")
    alternative = page.locator(".shiny-chat-user-message").first
    alternative.hover()
    alternative.get_by_role("button", name="Previous version").click()
    chat.expect_latest_message("echo: original")

    page.get_by_role("button", name="Save for worker").click()
    expect(page.locator("#saved")).to_contain_text('"id": "c_')
    handoff = json.loads(page.locator("#saved").inner_text())
    page.goto("about:blank")
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("worker.py")),
            handoff["directory"],
            handoff["id"],
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    page.goto(local_app.url)
    expect(chat.loc).to_be_visible(timeout=30_000)
    chat.expect_latest_message("Saved worker answer")
    expect(page.locator(".shiny-chat-user-message")).to_have_count(2)
    expect(page.locator(".shiny-chat-message")).to_have_count(2)
    expect(page.locator("#run_id")).to_have_text("run-worker")
    page.get_by_role("button", name="Inspect model context").click()
    expect(page.locator("#turns")).to_contain_text("Worker summary")
    turns = json.loads(page.locator("#turns").inner_text())
    assert [turn["contents"][0]["text"] for turn in turns] == [
        "Worker summary",
        "Continue in worker",
        "Provider worker answer",
    ]
    expect(page.locator(".shiny-chat-messages-content")).to_contain_text(
        "echo: original"
    )

    # The unselected sibling remains available after the worker saved its branch.
    first = page.locator(".shiny-chat-user-message").first
    first.hover()
    first.get_by_role("button", name="Next version").click()
    chat.expect_latest_message("echo: alternative")
    expect(page.locator(".shiny-chat-user-message")).to_have_count(1)
    first.hover()
    first.get_by_role("button", name="Previous version").click()
    chat.expect_latest_message("Saved worker answer")
