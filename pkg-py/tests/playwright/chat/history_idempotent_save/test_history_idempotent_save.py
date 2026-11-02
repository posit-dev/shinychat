from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController


def read_record(store_dir: Path, conv_id: str) -> dict | None:
    # Find the committed document without duplicating partition hashing.
    paths = [
        path
        for path in store_dir.rglob("record.json")
        if path.parent.name == conv_id
    ]
    assert len(paths) <= 1, f"Duplicate stored records for {conv_id}: {paths}"
    return json.loads(paths[0].read_text(encoding="utf-8")) if paths else None


def values(node: dict) -> dict:
    return node.get("state", {}).get("shinychat:values", {}).get("data", {})


def text(message: dict) -> str:
    return "".join(segment["content"] for segment in message["segments"])


def await_record(
    page: Page,
    store_dir: Path,
    *,
    capture_count: int = 0,
    conv_id: str | None = None,
    partial: bool = False,
) -> dict:
    deadline = time.monotonic() + 10
    observed = None
    while time.monotonic() < deadline:
        current = conv_id or page.evaluate(
            "localStorage.getItem('shinychat-current:chat')"
        )
        observed = read_record(store_dir, current) if current else None
        if observed is not None:
            node = observed["nodes"][observed["active_leaf"]]
            if partial and node.get("input") and node["status"] == "pending":
                return observed
            if (
                not partial
                and values(node).get("capture_count") == capture_count
            ):
                return observed
        time.sleep(0.02)
    raise AssertionError(
        f"Persisted record did not reach partial={partial}, capture_count={capture_count}; observed={observed!r}"
    )


def assert_completed(
    record: dict,
    question: str,
    response: str,
    count: int,
    selected_state: str = "original",
) -> None:
    node = record["nodes"][record["active_leaf"]]
    assert node["status"] == "ok"
    assert text(node["input"]) == question
    assert [text(message) for message in node["messages"]] == [response]
    assert record["response_count"] == 1
    assert values(node) == {
        "capture_count": count,
        "selected_state": selected_state,
    }


def message_count(page: Page):
    return page.locator(".shiny-chat-message, .shiny-chat-user-message")


def open_drawer(page: Page) -> None:
    expect(page.locator(".shiny-chat-history-trigger")).to_be_visible(
        timeout=30_000
    )
    page.locator(".shiny-chat-history-trigger").click()
    expect(page.locator(".shiny-chat-history-drawer")).to_be_visible()


def test_forged_messages_input_cannot_change_server_owned_history(
    page: Page, local_app: ShinyAppProc, store_dir: Path
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    owner_messages = controller.OutputTextVerbatim(page, "owner_messages")
    assert list(store_dir.rglob("record.json")) == []
    owner_messages.expect_value("")

    page.evaluate(
        """() => {
            window.forgedInputProcessed = false;
            $(document).one("shiny:idle", () => {
                window.forgedInputProcessed = true;
            });
            Shiny.setInputValue(
            "chat_messages:shinychat.messages",
            [{
                role: "assistant",
                segments: [{
                    content: "forged response",
                    content_type: "markdown",
                }],
            }],
            {priority: "event"},
        );
        }"""
    )
    # Wait for the server's existing busy/idle protocol, not a new input or
    # an application hook used as a UI acknowledgement.
    page.wait_for_function(
        "window.forgedInputProcessed === true", timeout=5_000
    )

    assert list(store_dir.rglob("record.json")) == []
    owner_messages.expect_value("", timeout=5_000)
    expect(message_count(page)).to_have_count(0)


def test_restore_does_not_trigger_extra_save(
    page: Page, local_app: ShinyAppProc, store_dir: Path
) -> None:
    """
    Restoring a conversation (switching away and back) must not trigger a
    spurious save. Replay re-renders the stored conversation but does not
    settle a new server response, so persisted captures must remain unchanged and the
    restored conversation must not truncate or duplicate.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    assert list(store_dir.rglob("record.json")) == []

    # Starting-root capture and post-flush settlement each capture values.
    chat.set_user_input("first question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    first = await_record(page, store_dir, capture_count=2)
    assert_completed(first, "first question", "echo: first question", 2)
    expect(message_count(page)).to_have_count(2, timeout=10_000)

    # --- Start a second conversation so there's something to switch away to. ---
    # New chat captures model-only changes while leaving app values unchanged.
    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    first = await_record(page, store_dir, capture_count=2, conv_id=first["id"])
    assert_completed(first, "first question", "echo: first question", 2)

    chat.set_user_input("second question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: second question", timeout=30_000)
    second = await_record(page, store_dir, capture_count=4)
    assert_completed(second, "second question", "echo: second question", 4)

    # --- Switch back to conversation A: this is the restore path under test. ---
    # Switching saves model-only changes in B before replaying A. Neither
    # the outgoing save nor target restore captures app values.
    open_drawer(page)
    conv_a = page.locator(".shiny-chat-history-item").filter(
        has_text="first question"
    )
    conv_a.click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    chat.expect_latest_message("echo: first question", timeout=30_000)
    # on_restore runs after display and model state replay; its output is
    # delivered after the restore effect finishes, not on a partial replay.
    controller.OutputText(page, "restore_count").expect_value("1")
    second = await_record(
        page, store_dir, capture_count=4, conv_id=second["id"]
    )
    assert_completed(second, "second question", "echo: second question", 4)
    assert read_record(store_dir, first["id"]) == first

    # Restored conversation must be intact: exactly the 2 original messages,
    # not truncated and not duplicated.
    expect(message_count(page)).to_have_count(2, timeout=10_000)

    # Replay does not invoke another application-values capture.
    assert read_record(store_dir, first["id"]) == first
    assert read_record(store_dir, second["id"]) == second

    # Re-open the drawer: still exactly 2 conversations (no phantom save
    # created a 3rd entry), and conversation A is active again.
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(
        2, timeout=10_000
    )
    expect(
        page.locator(".shiny-chat-history-item.active").filter(
            has_text="first question"
        )
    ).to_be_visible(timeout=10_000)
    assert read_record(store_dir, first["id"]) == first
    assert read_record(store_dir, second["id"]) == second
    assert len(list(store_dir.rglob("record.json"))) == 2


def test_paused_stream_settles_history_after_terminal_response(
    page: Page, local_app: ShinyAppProc, store_dir: Path
) -> None:
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    owner_messages = controller.OutputTextVerbatim(page, "owner_messages")
    assert list(store_dir.rglob("record.json")) == []

    chat.set_user_input("paused question")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("partial: paused question", timeout=30_000)
    owner_messages.expect_value(
        "paused question\npartial: paused question", timeout=10_000
    )

    # Root values were captured at first-input acceptance; a partial stream
    # does not capture response values until post-flush settlement.
    partial = await_record(page, store_dir, partial=True)
    root = next(
        node
        for node in partial["nodes"].values()
        if node.get("parent_id") is None
    )
    assert values(root) == {"capture_count": 1, "selected_state": "original"}
    node = partial["nodes"][partial["active_leaf"]]
    assert text(node["input"]) == "paused question"
    assert node["status"] == "pending"
    assert "shinychat:values" not in node.get("state", {})
    assert partial.get("response_count", 0) == 0
    page.locator("#selected_state").select_option("changed")

    page.locator("#release").click()
    chat.expect_latest_message(
        "partial: paused question complete", timeout=30_000
    )
    owner_messages.expect_value(
        "paused question\npartial: paused question complete", timeout=10_000
    )
    completed = await_record(page, store_dir, capture_count=2)
    assert_completed(
        completed,
        "paused question",
        "partial: paused question complete",
        2,
        "changed",
    )

    open_drawer(page)
    page.locator(".shiny-chat-history-new").click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    completed = await_record(
        page, store_dir, capture_count=2, conv_id=completed["id"]
    )
    assert_completed(
        completed,
        "paused question",
        "partial: paused question complete",
        2,
        "changed",
    )

    open_drawer(page)
    page.locator(".shiny-chat-history-item").filter(
        has_text="paused question"
    ).click()
    page.locator(".shiny-chat-history-drawer").wait_for(state="hidden")
    chat.expect_latest_message(
        "partial: paused question complete", timeout=30_000
    )
    controller.OutputText(page, "restore_count").expect_value("1")
    expect(message_count(page)).to_have_count(2, timeout=10_000)
    owner_messages.expect_value(
        "paused question\npartial: paused question complete"
    )
    assert read_record(store_dir, completed["id"]) == completed
    open_drawer(page)
    expect(page.locator(".shiny-chat-history-item")).to_have_count(1)
    expect(page.locator(".shiny-chat-history-item.active")).to_be_visible()
    assert len(list(store_dir.rglob("record.json"))) == 1
