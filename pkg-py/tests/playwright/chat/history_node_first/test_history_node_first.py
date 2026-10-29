"""Browser tests for the node-first failed-edit contract (shinychat#zcv8).

Coverage through the real guarded Chat path, a real file store and a real
browser (run focused: ``make py-check-playwright FILTER=history_node_first``):

* ``test_history_node_first_success_control`` -- the unchanged healthy edit
  path: exactly one accepted submission (each independent counter moves
  3 -> 4), a real recorded branch node with attachment byte fidelity, and the
  file store surviving a page reload.
* ``test_history_node_first_restore_failure_retains_edit`` and
  ``test_history_node_first_capture_failure_retains_edit`` -- an edit-time
  ``on_restore`` that mutates the live app+model then throws, and a normal
  return that first stages a distinctive captured-at-failure app value and
  then poisons the model so the required capture fails. In both cases B'
  must be displayed inside the actual server fault window, stay displayed
  with no transient removal or rollback, trigger zero provider or
  accepted-input callbacks, run the automatic capture role exactly once
  (proven by the independent ``#save_count``), and be recorded as its own
  terminal-incomplete node with an explicit invalid checkpoint and the
  preparation envelope -- ``app_values: "unavailable"`` when the fixture's
  on_save raised mid-capture, ``app_values: "complete"`` when it finished
  -- while the original branch is retained.
* ``test_history_node_first_failed_edit_survives_reload`` -- a failed real
  file reload, parameterized across both app-values outcomes: the failed
  node reloads selected and displayed with its failure affordances, the
  stored node is unchanged, and loading it dispatches nothing. An
  unavailable snapshot must not invoke ``on_restore`` at all; a complete
  snapshot restores the failed node's own distinctive saved values (not
  inherited parent values) exactly once.
* ``test_history_node_first_browse_and_retry_recovers`` -- original <-> failed
  navigation with the callback still broken, then fixing the app and an
  explicit Retry while the live model getter is still poisoned: the valid
  parent is restored without close-capturing the poisoned live model and a
  new sibling succeeds exactly once, preserving the failed node, the
  original branch, the selection, the model context and the composer draft.
* ``test_history_node_first_retry_failure_creates_new_sibling`` -- an
  intentional Retry with the fault still active fails again, yet creates a
  new failed sibling; the earlier failed node is not rewritten.

The five failure-facing tests are contract regressions: they must fail
against pre-feature production, which never retains a failed edit.
``app.py`` documents the fixture's fault model, counters, the deterministic
unavailable/complete snapshot split, and the ``#model_poisoned`` and
``#save_count`` observations.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent
ATTACHMENT_BYTES = (HERE / "notes-b.txt").read_bytes()

MSG_A = "alpha seed"
MSG_B = "bravo seed"
MSG_C = "charlie seed"
MSG_B_PRIME = "bravo prime edit"
ATTACHMENT_NAME = "notes-b.txt"
DRAFT_TEXT = "delta draft"
# The distinctive app value the capture_poison fault stages before the
# required capture fails: a complete failed-position snapshot must contain
# exactly this value (deliberately different from any inherited parent
# value, which is "all"), and reloading it must restore it rather than the
# parent's.
FILTER_AT_FAILURE = "captured-at-failure"
# The agreed durable failure metadata: an explicit invalid checkpoint plus
# the shinychat:preparation/input_preparation envelope
# {terminal: true, accepted: false, app_values: unavailable | complete}.
PREPARATION_KEY = "shinychat:preparation"
# Coordinator Inbox evidence capture (best effort, never asserted).
SCREENSHOT_PATH = os.environ.get(
    "SHINYCHAT_ZCV8_FAILURE_SCREENSHOT", "/tmp/zcv8-node-first-failure.png"
)
# Contract: during edit-time on_restore, chat.messages() shows the restored
# parent's accepted transcript prefix, and the model is rewound to the parent
# at the same point.
PARENT_PREFIX = [
    {"role": "user", "content": MSG_A},
    {"role": "assistant", "content": f"Echo: {MSG_A}"},
]
# The failed position's outgoing view -- the parent prefix plus the failed
# input with no response. Loads and the outgoing browse callback see this
# same view (ordinary browse semantics retain the outgoing transcript until
# the replay installs the target display).
FAILED_POSITION_PREFIX = [
    {"role": "user", "content": MSG_A},
    {"role": "assistant", "content": f"Echo: {MSG_A}"},
    {"role": "user", "content": MSG_B_PRIME},
]
# The original branch's remembered C destination: browsing to B's version
# displays its descendant's full accepted branch on screen. Read-only
# display-only navigation deliberately never applies that context to the
# live model (asserted on the browse trace entry instead).
B_BRANCH_PREFIX = [
    {"role": "user", "content": MSG_A},
    {"role": "assistant", "content": f"Echo: {MSG_A}"},
    {"role": "user", "content": MSG_B},
    {"role": "assistant", "content": f"Echo: {MSG_B}"},
    {"role": "user", "content": MSG_C},
    {"role": "assistant", "content": f"Echo: {MSG_C}"},
]

SAMPLER_JS = """() => {
  const container = document.querySelector(".shiny-chat-messages-content");
  if (!container) throw new Error("messages container not found");
  window.__hnfSamples = [];
  const sample = () => {
    // An inline editor is not a submitted row. Observe rendered message
    // bodies only, so typing B' before Save cannot start the retention clock.
    const texts = Array.from(
      container.querySelectorAll(".shiny-chat-user-message .shiny-chat-message-body")
    ).map((el) => (el.innerText || "").trim());
    // The inline edit editor (.shiny-chat-edit-wrap) renders inside the
    // edited .shiny-chat-user-message row, so text being composed there
    // must not be mistaken for a displayed submission. Record whether any
    // editor is open so assertions can anchor on the first real display.
    const editing = !!container.querySelector(".shiny-chat-edit-wrap");
    window.__hnfSamples.push({ at: Date.now(), texts, editing });
  };
  const observer = new MutationObserver(() => sample());
  observer.observe(container, {subtree: true, childList: true, characterData: true});
  // Heartbeat: samples must land inside the server-side fault window even
  // when the DOM is quiet (the server event loop is blocked during it).
  // 50 ms stays well inside app.py's FAULT_WINDOW_SECONDS window.
  const heartbeat = setInterval(sample, 50);
  window.__hnfDisconnect = () => {
    clearInterval(heartbeat);
    observer.disconnect();
  };
  sample();
}"""


def send_and_expect(chat: ChatController, text: str) -> None:
    chat.set_user_input(text)
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message(f"Echo: {text}", timeout=30_000)


def seed_conversation(
    page: Page, chat: ChatController, *, filter_value: str | None = None
) -> None:
    """Seed A, B (with the text attachment), C; counters must read 3/3/3."""
    if filter_value is not None:
        page.locator("#region_filter").fill(filter_value)
    send_and_expect(chat, MSG_A)
    page.set_input_files("input[type=file]", str(HERE / ATTACHMENT_NAME))
    expect(
        chat.loc_input_container.locator(".shiny-chat-text-preview-name")
    ).to_have_text(ATTACHMENT_NAME, timeout=10_000)
    send_and_expect(chat, MSG_B)
    bubble_b = page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    expect(bubble_b).to_have_count(1, timeout=10_000)
    expect(bubble_b.locator(".shiny-chat-text-preview-name")).to_have_text(
        ATTACHMENT_NAME, timeout=10_000
    )
    send_and_expect(chat, MSG_C)
    expect(page.locator("#provider_calls")).to_have_text("3", timeout=10_000)
    expect(page.locator("#submit_count")).to_have_text("3", timeout=10_000)
    expect(page.locator("#user_input_count")).to_have_text("3", timeout=10_000)
    expect(page.locator("#user_input_text")).to_have_text(MSG_C, timeout=10_000)
    expect(page.locator("#restore_count")).to_have_text("0", timeout=10_000)


def edit_user_message(page: Page, index: int, new_text: str) -> None:
    user = page.locator(".shiny-chat-user-message").nth(index)
    user.hover()
    edit_btn = user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()
    editor = user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially(new_text)
    user.locator(".shiny-chat-btn-send").click()


def install_sampler(page: Page) -> None:
    """Sample user-message texts (with Date.now() timestamps) on every DOM
    mutation, so visibility is comparable against server trace windows."""
    page.evaluate(SAMPLER_JS)


def peek_samples(page: Page) -> list[dict[str, Any]]:
    """Current samples without disconnecting the sampler, so a test can mark
    stage boundaries (browse, retry) in the sample timeline."""
    raw = page.evaluate("() => window.__hnfSamples || []")
    assert isinstance(raw, list)
    return [
        {
            "at": float(s["at"]),
            "texts": [str(t) for t in s["texts"]],
            "editing": bool(s.get("editing", False)),
        }
        for s in raw
    ]


def collect_samples(page: Page) -> list[dict[str, Any]]:
    page.evaluate("() => window.__hnfDisconnect && window.__hnfDisconnect()")
    raw = page.evaluate("() => window.__hnfSamples")
    assert isinstance(raw, list)
    return [
        {
            "at": float(s["at"]),
            "texts": [str(t) for t in s["texts"]],
            "editing": bool(s.get("editing", False)),
        }
        for s in raw
    ]


def read_trace(page: Page) -> list[dict[str, Any]]:
    store_dir = Path(page.locator("#store_dir").inner_text().strip())
    return [
        json.loads(line)
        for line in (store_dir / "restore_trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def restore_enter_entries(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in trace if e["event"] == "restore_enter"]


def fault_window(trace: list[dict[str, Any]]) -> tuple[float, float]:
    """The [start, end] ms wall-clock bounds of the server-side synchronous
    restore fault window (restore_throw mode only)."""
    start_ms = next(
        (float(e["t_ms"]) for e in trace if e["event"] == "fault_window_start"),
        None,
    )
    end_ms = next(
        (float(e["t_ms"]) for e in trace if e["event"] == "fault_window_end"),
        None,
    )
    assert start_ms is not None and end_ms is not None, (
        "no fault_window markers in the restore trace; the restore_throw "
        "fault mode never ran"
    )
    return start_ms, end_ms


def read_record(page: Page) -> dict[str, Any]:
    """The current on-disk record.json for the active conversation."""
    store_dir = Path(page.locator("#store_dir").inner_text().strip())
    for path in sorted(store_dir.glob("**/record.json")):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    raise AssertionError(f"no readable record.json under {store_dir}")


def wait_for_record(
    page: Page, text: str, timeout_s: float = 15.0
) -> dict[str, Any]:
    """Poll real record.json until a node with input ``text`` exists; return
    the last readable record on timeout so the structural assertion fails."""
    return wait_for_record_where(
        page,
        lambda record: bool(_node_ids_with_input(record, text)),
        description=f"a node recording the input {text!r}",
        timeout_s=timeout_s,
    )


def wait_for_record_where(
    page: Page,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    description: str,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """Poll real record.json until ``predicate`` holds; return the last
    readable record on timeout so the structural assertion fails."""
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    store_dir = Path(page.locator("#store_dir").inner_text().strip())
    while time.monotonic() < deadline:
        for path in sorted(store_dir.glob("**/record.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if _node_ids_with_input(record, MSG_A):
                last = record
                if predicate(record):
                    return record
                break
        page.wait_for_timeout(250)
    assert last is not None, f"no readable record.json under {store_dir}"
    return last


def wait_for_failure_settled(page: Page) -> None:
    """Deterministic failure completion: the contract promises the failed
    edit stays visible with a not-sent outcome, shown either as the shipped
    read-only bar or an error notification. No silent fallback."""
    expect(
        page.locator(".shiny-chat-readonly, .shiny-notification-error").first
    ).to_be_visible(timeout=30_000)


def _begin_failing_edit(
    page: Page,
    chat: ChatController,
    fault_mode: str,
    *,
    draft: str | None = None,
) -> int:
    """Seed, optionally stage a composer draft, start the visibility
    sampler, then edit B into a preparation failure. The sampler stays
    running so callers can mark later stage boundaries. Returns the
    ``#save_count`` reading right before the edit, so callers can prove the
    pre-admission capture ran exactly once (ordinary saves count too, hence
    the delta)."""
    seed_conversation(page, chat)
    if draft is not None:
        # A composer draft typed before the failing edit must survive the
        # whole failure/browse/retry cycle (the composer is only hidden).
        chat.set_user_input(draft)
    install_sampler(page)
    page.locator("#fault_mode").select_option(fault_mode)
    expect(page.locator("#save_count")).not_to_be_empty(timeout=10_000)
    saves_before = int(page.locator("#save_count").inner_text().strip())
    edit_user_message(page, 1, MSG_B_PRIME)
    expect(page.locator("#restore_count")).to_have_text("1", timeout=30_000)
    wait_for_failure_settled(page)
    return saves_before


def _seed_edit_and_fail(
    page: Page, chat: ChatController, fault_mode: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    saves_before = _begin_failing_edit(page, chat, fault_mode)
    return collect_samples(page), read_trace(page), saves_before


def assert_save_count(page: Page, expected: int) -> None:
    """The independent on_save counter: proves the automatic capture role
    ran exactly once per preparation failure (ordinary saves are part of
    the baseline the caller read before the edit)."""
    expect(page.locator("#save_count")).to_have_text(
        str(expected), timeout=10_000
    )


def maybe_save_failure_screenshot(page: Page) -> None:
    """Best-effort, non-asserted evidence capture for the Inbox handoff: the
    retained failed node with its not-sent read-only bar, Retry/Edit
    affordances and sibling navigation, straight from the real fixture page
    (no mock, no UI polish). Must never fail the test."""
    try:
        failed_row = page.locator(".shiny-chat-user-message").filter(
            has_text=MSG_B_PRIME
        )
        # Reveal the hover-only affordances for the capture.
        failed_row.hover()
        page.screenshot(path=SCREENSHOT_PATH, full_page=True)
    except Exception:
        # Evidence capture must never fail the contract test.
        pass


def _segments_text(msg: dict[str, Any]) -> str:
    return "".join(
        str(seg.get("content", ""))
        for seg in msg.get("segments") or []
        if isinstance(seg, dict)
    )


def _node_ids_with_input(record: dict[str, Any], text: str) -> list[str]:
    return [
        node_id
        for node_id, node in record.get("nodes", {}).items()
        if text in _segments_text(node.get("input") or {})
    ]


def _ok_node_ids(record: dict[str, Any], text: str) -> list[str]:
    return [
        node_id
        for node_id in _node_ids_with_input(record, text)
        if record["nodes"][node_id].get("status") == "ok"
    ]


def _find_fixture_attachment(
    record: dict[str, Any], node_id: str
) -> dict[str, Any]:
    atts = (record["nodes"][node_id].get("input") or {}).get("attachments")
    for att in atts if isinstance(atts, list) else []:
        if att.get("name") == ATTACHMENT_NAME:
            return att
    raise AssertionError(
        f"node {node_id} has no attachment named {ATTACHMENT_NAME!r}: {atts}"
    )


def assert_attachment_fidelity(record: dict[str, Any], node_id: str) -> None:
    att = _find_fixture_attachment(record, node_id)
    assert att.get("mime") == "text/plain", f"wrong mime: {att.get('mime')!r}"
    data_url = str(att.get("data_url", ""))
    assert data_url.startswith("data:"), f"no data URL on {att.get('name')!r}"
    assert base64.b64decode(data_url.split(",", 1)[1]) == ATTACHMENT_BYTES, (
        f"attachment data URL for {ATTACHMENT_NAME!r} does not decode to the "
        "fixture file bytes"
    )


def assert_original_branch_retained(record: dict[str, Any]) -> None:
    ids_b = _node_ids_with_input(record, MSG_B)
    ids_c = _node_ids_with_input(record, MSG_C)
    assert len(ids_b) == 1, f"original B node missing: {ids_b}"
    assert len(ids_c) == 1, f"original C node missing: {ids_c}"
    assert record["nodes"][ids_c[0]]["parent_id"] == ids_b[0], (
        "original descendant C is no longer a child of original B"
    )
    assert_attachment_fidelity(record, ids_b[0])


def assert_preparation_envelope(
    record: dict[str, Any], node_id: str, *, app_values: str
) -> None:
    """The durable failed-attempt marker in the versioned StateEntry
    envelope, on the failed node only. ``app_values`` is the fixture's
    deterministic outcome: "unavailable" when the on_save callback raised
    mid-capture (restore_throw), "complete" when it finished and the full
    snapshot serialized (capture_poison)."""
    state = record["nodes"][node_id].get("state") or {}
    entry = state.get(PREPARATION_KEY)
    assert isinstance(entry, dict), (
        f"node {node_id} is missing the {PREPARATION_KEY!r} preparation "
        f"envelope; state keys: {sorted(state)}"
    )
    assert entry.get("kind") == "input_preparation", (
        f"unexpected envelope kind {entry.get('kind')!r} on {PREPARATION_KEY}"
    )
    assert entry.get("version") == 1, f"unexpected envelope version {entry!r}"
    assert entry.get("mode") == "snapshot", (
        f"unexpected envelope mode {entry!r}"
    )
    data = entry.get("data") or {}
    assert data.get("terminal") is True, (
        f"failed node {node_id} must be marked terminal, got {data!r}"
    )
    assert data.get("accepted") is False, (
        f"failed node {node_id} must be marked not accepted, got {data!r}"
    )
    assert data.get("app_values") == app_values, (
        f"failed node {node_id} must record app_values={app_values!r} "
        f"(the fixture's on_save outcome), got {data!r}"
    )


def assert_failed_node(
    record: dict[str, Any], node_id: str, *, app_values: str
) -> None:
    """One retained failed attempt: explicit invalid checkpoint, an ordinary
    not-sent error, and the preparation envelope with the fixture's
    deterministic app_values outcome."""
    node = record["nodes"][node_id]
    assert node.get("checkpoint") == "invalid", (
        f"failed node {node_id} must record checkpoint='invalid', "
        f"got {node.get('checkpoint')!r}"
    )
    assert node.get("status") == "error", (
        f"failed node {node_id} must carry an ordinary error status, "
        f"got {node.get('status')!r}"
    )
    error = node.get("error") or {}
    assert "not sent" in str(error.get("message", "")).lower(), (
        f"failed node {node_id} must say the message was not sent, "
        f"got {error!r}"
    )
    assert_preparation_envelope(record, node_id, app_values=app_values)


def assert_failed_edit_recorded(
    record: dict[str, Any], *, app_values: str
) -> str:
    """The single failed edit node: recorded under B's valid parent, still
    selected, with attachment fidelity and the failed-node markers."""
    ids_a = _node_ids_with_input(record, MSG_A)
    ids_bp = _node_ids_with_input(record, MSG_B_PRIME)
    assert len(ids_a) == 1, f"expected exactly one A node, found {ids_a}"
    assert len(ids_bp) == 1, (
        "shinychat#zcv8 node-first contract: the failed edit must be recorded "
        "as its own node under B's valid parent. Old production behavior "
        f"records no node for the attempted edit {MSG_B_PRIME!r}; found {ids_bp}"
    )
    bp_id = ids_bp[0]
    node = record["nodes"][bp_id]
    assert node["parent_id"] == ids_a[0], (
        "failed edit node must be a child of A"
    )
    assert_failed_node(record, bp_id, app_values=app_values)
    assert record.get("active_leaf") == bp_id, (
        "failed edit node must remain the selected position; "
        f"active_leaf={record.get('active_leaf')!r}"
    )
    assert_attachment_fidelity(record, bp_id)
    return bp_id


def assert_b_prime_displayed(page: Page) -> None:
    b_prime = page.locator(".shiny-chat-user-message").filter(
        has_text=MSG_B_PRIME
    )
    expect(b_prime).to_have_count(1, timeout=10_000)
    expect(b_prime.locator(".shiny-chat-text-preview-name")).to_have_text(
        ATTACHMENT_NAME, timeout=10_000
    )


def assert_failed_node_affordances(page: Page, chat: ChatController) -> None:
    """The safe failed node stays read-only for ordinary follow-ups but
    offers explicit recovery: history_update active_can_resubmit keeps the
    shipped read-only bar (not-sent wording) while the failed row keeps its
    Retry/Edit affordances and the composer is only hidden (draft intact)."""
    bar = chat.loc.locator(".shiny-chat-readonly")
    expect(bar).to_be_visible(timeout=10_000)
    status = bar.get_by_role("status")
    expect(status).to_contain_text("not sent", timeout=10_000)
    expect(status).to_contain_text("Retry", timeout=10_000)
    retry_btn = chat.loc.get_by_role("button", name="Retry message")
    expect(retry_btn).to_have_count(1)
    expect(retry_btn).to_be_enabled()
    failed_row = page.locator(".shiny-chat-user-message").filter(
        has_text=MSG_B_PRIME
    )
    expect(failed_row.locator(".shiny-chat-edit-btn")).to_have_count(1)
    notice = chat.loc.locator(".shiny-chat-message-not-sent")
    expect(notice).to_have_text("This message was not sent.")
    expect(notice).to_be_visible()
    expect(failed_row.locator(".shiny-chat-retry-error")).to_have_count(0)
    assert notice.evaluate("el => getComputedStyle(el).fontStyle") == "italic"
    bubble_box = failed_row.bounding_box()
    notice_box = notice.bounding_box()
    assert bubble_box is not None and notice_box is not None
    assert notice_box["y"] >= bubble_box["y"] + bubble_box["height"], (
        "The preparation failure notice must be below the user bubble."
    )
    # Ordinary follow-ups stay prohibited; the composer stays mounted but
    # hidden so a draft is never erased.
    expect(chat.loc_input).to_be_hidden()


def assert_no_extra_callbacks(page: Page) -> None:
    expect(page.locator("#provider_calls")).to_have_text("3", timeout=10_000)
    expect(page.locator("#submit_count")).to_have_text("3", timeout=10_000)
    expect(page.locator("#user_input_count")).to_have_text("3", timeout=10_000)


def assert_no_rollback(samples: list[dict[str, Any]]) -> None:
    """After B' is first *displayed*, it never disappears and the original B
    is never re-displayed.

    Display means the submitted pending edit rendered in the message list,
    not text being composed in the inline edit editor. The editor renders
    inside a .shiny-chat-user-message row, and on "Save and resend" it
    closes while the row briefly shows the original message until the
    server's pending projection installs B' -- the fault-window assertions
    prove that projection arrived before the fallible restore ran. Editor
    typing is composition, so it must not anchor the no-rollback invariant.
    """
    first = next(
        (
            i
            for i, s in enumerate(samples)
            if not s["editing"] and any(MSG_B_PRIME in t for t in s["texts"])
        ),
        None,
    )
    assert first is not None, (
        "shinychat#zcv8 node-first contract: the pending edited message B' "
        f"({MSG_B_PRIME!r}) was never displayed (its text only ever appeared "
        "inside the open edit editor). Old production behavior "
        "never shows the submitted edit and rolls back to the original "
        f"message B. Samples: {[s['texts'] for s in samples]}"
    )
    for i in range(first, len(samples)):
        assert any(MSG_B_PRIME in t for t in samples[i]["texts"]), (
            f"transient rollback of B' at sample {i}: {samples[i]}"
        )
        assert not any(MSG_B in t for t in samples[i]["texts"]), (
            f"original B re-displayed after B' appeared at sample {i}: {samples[i]}"
        )


def assert_stable_presence(
    samples: list[dict[str, Any]],
    from_index: int,
    *,
    must_text: str,
    forbidden_text: str,
) -> None:
    """From ``from_index`` onward, ``must_text`` never disappears (no
    transient removal or rollback) and ``forbidden_text`` never appears."""
    assert 0 <= from_index < len(samples), (
        f"no samples recorded after index {from_index} (have {len(samples)})"
    )
    for i in range(from_index, len(samples)):
        assert any(must_text in t for t in samples[i]["texts"]), (
            f"transient removal of {must_text!r} at sample {i}: {samples[i]}"
        )
        assert not any(forbidden_text in t for t in samples[i]["texts"]), (
            f"{forbidden_text!r} re-displayed at sample {i}: {samples[i]}"
        )


def assert_edit_time_parent_prefix_entry(entry: dict[str, Any]) -> None:
    """Contract: during edit-time on_restore, chat.messages() shows the
    restored parent's accepted transcript prefix and the model is rewound
    to the parent at the same point -- not the outgoing full branch."""
    assert entry["chat_messages"] == PARENT_PREFIX, (
        "edit-time on_restore must observe the parent-prefix transcript: "
        f"got {entry['chat_messages']}"
    )
    assert entry["client_turns"] == PARENT_PREFIX, (
        "the live model must be rewound to the parent at edit-time restore: "
        f"got {entry['client_turns']}"
    )


def assert_parent_prefix_callback_observation(
    trace: list[dict[str, Any]],
) -> None:
    entries = restore_enter_entries(trace)
    assert entries, "no on_restore trace event was recorded"
    assert_edit_time_parent_prefix_entry(entries[-1])


def test_history_node_first_success_control(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Healthy edit of B: exactly one submission, a real recorded branch with
    attachment byte fidelity, and the file store surviving a page reload."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    seed_conversation(page, chat, filter_value="north")
    edit_user_message(page, 1, MSG_B_PRIME)
    chat.expect_latest_message(f"Echo: {MSG_B_PRIME}", timeout=30_000)

    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)

    # Exactly one normal submission: each independent counter moves 3 -> 4.
    expect(page.locator("#provider_calls")).to_have_text("4", timeout=10_000)
    expect(page.locator("#submit_count")).to_have_text("4", timeout=10_000)
    expect(page.locator("#user_input_count")).to_have_text("4", timeout=10_000)
    expect(page.locator("#user_input_text")).to_have_text(
        MSG_B_PRIME, timeout=10_000
    )
    expect(page.locator("#restore_count")).to_have_text("1", timeout=10_000)
    expect(page.locator("#model_poisoned")).to_have_text(
        "false", timeout=10_000
    )
    assert_b_prime_displayed(page)

    # The instrument captured the edit-time restore callback observation.
    # (The parent-prefix content of chat.messages() during edit-time restore
    # is asserted by main's test_history_app_restore_lifecycle.py regression.)
    trace = read_trace(page)
    entries = restore_enter_entries(trace)
    assert entries, "no on_restore trace event was recorded for the edit"
    assert "chat_messages" in entries[-1] and "client_turns" in entries[-1]

    record = wait_for_record(page, MSG_B_PRIME)
    ids_a = _node_ids_with_input(record, MSG_A)
    ids_bp = _node_ids_with_input(record, MSG_B_PRIME)
    assert len(ids_a) == 1 and len(ids_bp) == 1
    bp = record["nodes"][ids_bp[0]]
    assert bp["parent_id"] == ids_a[0], "B' must be a child of A"
    assert bp["status"] == "ok", f"unexpected B' status {bp['status']!r}"
    responses = [
        m
        for m in bp.get("messages") or []
        if isinstance(m, dict) and m.get("role") == "assistant"
    ]
    assert len(responses) == 1, (
        f"expected one response message, got {responses}"
    )
    assert f"Echo: {MSG_B_PRIME}" in _segments_text(responses[0])
    assert_attachment_fidelity(record, ids_bp[0])
    assert_original_branch_retained(record)
    assert record["active_leaf"] == ids_bp[0], "edited node must be selected"

    # The file store persists across a page reload.
    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_A)
    ).to_have_count(1, timeout=30_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B_PRIME)
    ).to_have_count(1, timeout=10_000)
    # The off-path original branch is retained in the record, not displayed.
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    ).to_have_count(0, timeout=10_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_C)
    ).to_have_count(0, timeout=10_000)
    chat.expect_latest_message(f"Echo: {MSG_B_PRIME}", timeout=30_000)
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
    expect(page.locator("#region_filter")).to_have_value(
        "north", timeout=10_000
    )
    expect(page.locator("#current_filter")).to_have_text(
        "north", timeout=10_000
    )
    expect(page.locator("#restore_count")).to_have_text("1", timeout=10_000)


def test_history_node_first_restore_failure_retains_edit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Contract regression: edit B to B' while the edit-time on_restore
    mutates live app and model state, then throws. B' must be displayed
    inside the restore fault window, stay displayed with no transient
    rollback, trigger zero provider or accepted-input callbacks, and be
    recorded as its own terminal-incomplete node with an invalid checkpoint
    and the preparation envelope while the original branch is retained."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    samples, trace, saves_before = _seed_edit_and_fail(
        page, chat, "restore_throw"
    )
    expect(page.locator("#current_filter")).to_have_text(
        "mutated-by-restore", timeout=10_000
    )
    assert_b_prime_displayed(page)

    # B' was visible inside the actual server fault window (ms timestamps):
    # the server must have pushed the pending projection before blocking in
    # the fallible restore. First prove the instrument sampled the window at
    # all, then that B' is what was visible in it.
    start_ms, end_ms = fault_window(trace)
    in_window = [s for s in samples if start_ms <= s["at"] <= end_ms]
    assert in_window, (
        "sampler instrument fault: no browser samples landed inside the "
        f"server fault window [{start_ms:.0f}..{end_ms:.0f}] ms; heartbeat "
        "or clock assumptions are broken"
    )
    in_window_b_prime = [
        s for s in in_window if any(MSG_B_PRIME in t for t in s["texts"])
    ]
    assert in_window_b_prime, (
        "shinychat#zcv8 node-first contract: the pending edited message B' "
        "must be displayed inside the edit-time restore fault window "
        f"[{start_ms:.0f}..{end_ms:.0f}] ms. Samples inside the window: "
        f"{[s['texts'] for s in in_window]}"
    )

    assert_no_rollback(samples)
    assert_no_extra_callbacks(page)
    # The failed edit is not an accepted input: user_input() still names C.
    expect(page.locator("#user_input_text")).to_have_text(MSG_C, timeout=10_000)
    # The live model getter stays poisoned until a saved parent is applied.
    expect(page.locator("#model_poisoned")).to_have_text("true", timeout=10_000)
    # The automatic capture role ran exactly once for the failed node; the
    # fixture's on_save raised mid-capture after a serializable fragment, so
    # the node must record the snapshot as unavailable, not a partial tree.
    assert_save_count(page, saves_before + 1)
    record = wait_for_record(page, MSG_B_PRIME)
    assert_failed_edit_recorded(record, app_values="unavailable")
    assert_original_branch_retained(record)
    assert_parent_prefix_callback_observation(trace)
    # Read-only for ordinary follow-ups, but explicit Retry/Edit remain,
    # with sibling navigation between the failed node and the original.
    assert_failed_node_affordances(page, chat)
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
    # Inbox evidence capture (best effort, never asserted).
    maybe_save_failure_screenshot(page)


def test_history_node_first_capture_failure_retains_edit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Contract regression: edit B to B' while on_restore mutates the live
    filter to a distinctive captured-at-failure value, then returns normally
    after poisoning the model, so the required capture of the edited
    exchange fails. B' must stay displayed with no transient removal or
    rollback, trigger zero provider or accepted-input callbacks, and be
    recorded as its own terminal-incomplete node with an invalid checkpoint
    and the preparation envelope recording a complete snapshot while the
    original branch is retained."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    samples, trace, saves_before = _seed_edit_and_fail(
        page, chat, "capture_poison"
    )
    assert_b_prime_displayed(page)
    # The fault mutated the live app state to the distinctive value before
    # the required capture failed.
    expect(page.locator("#current_filter")).to_have_text(
        FILTER_AT_FAILURE, timeout=10_000
    )
    assert_no_rollback(samples)
    assert_no_extra_callbacks(page)
    expect(page.locator("#user_input_text")).to_have_text(MSG_C, timeout=10_000)
    expect(page.locator("#model_poisoned")).to_have_text("true", timeout=10_000)
    # The automatic capture role ran exactly once for the failed node, and
    # this time it finished and serialized: the node must record the
    # snapshot as complete.
    assert_save_count(page, saves_before + 1)
    record = wait_for_record(page, MSG_B_PRIME)
    assert_failed_edit_recorded(record, app_values="complete")
    assert_original_branch_retained(record)
    assert_parent_prefix_callback_observation(trace)
    assert_failed_node_affordances(page, chat)


@pytest.mark.parametrize("fault_mode", ["restore_throw", "capture_poison"])
def test_history_node_first_failed_edit_survives_reload(
    page: Page, local_app: ShinyAppProc, fault_mode: str
) -> None:
    """Contract regression: a failed real file reload, parameterized across
    the two app-values outcomes. The terminal failed node reloads as the
    selected displayed position with its failure affordances and sibling
    navigation intact, and the on-disk node (input, attachment, invalid
    checkpoint, not-sent error, preparation envelope) is unchanged by the
    load. Loading dispatches no model work and accepts no input. When the
    snapshot is unavailable (restore_throw's on_save raised mid-capture),
    loading must not invoke on_restore at all -- never with inherited parent
    values. When the snapshot is complete (capture_poison), loading restores
    the failed node's own distinctive saved values, not inherited ones."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    _begin_failing_edit(page, chat, fault_mode)
    assert_b_prime_displayed(page)
    record = wait_for_record(page, MSG_B_PRIME)
    app_values = "unavailable" if fault_mode == "restore_throw" else "complete"
    bp_id = assert_failed_edit_recorded(record, app_values=app_values)
    assert_failed_node_affordances(page, chat)

    tracked_fields = (
        "parent_id",
        "checkpoint",
        "status",
        "error",
        "input",
        "state",
    )
    pre_node = {k: record["nodes"][bp_id].get(k) for k in tracked_fields}
    entries_before = restore_enter_entries(read_trace(page))
    assert len(entries_before) == 1, (
        "expected exactly one on_restore before the reload (the edit-time "
        f"failure); found {len(entries_before)}"
    )

    page.reload()
    expect(chat.loc).to_be_visible(timeout=30_000)
    assert_b_prime_displayed(page)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_A)
    ).to_have_count(1, timeout=30_000)
    # The off-path original branch stays off-path.
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    ).to_have_count(0, timeout=10_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_C)
    ).to_have_count(0, timeout=10_000)
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
    assert_failed_node_affordances(page, chat)

    # The reload of a terminal failed position dispatches no model work
    # and accepts no input.
    expect(page.locator("#provider_calls")).to_have_text("0", timeout=10_000)
    expect(page.locator("#submit_count")).to_have_text("0", timeout=10_000)
    expect(page.locator("#user_input_count")).to_have_text("0", timeout=10_000)
    entries_after = restore_enter_entries(read_trace(page))
    if fault_mode == "restore_throw":
        # Unavailable snapshot: loading must not run on_restore at all --
        # never with the failed position's inherited parent values.
        expect(page.locator("#restore_count")).to_have_text("0", timeout=10_000)
        assert len(entries_after) == 1, (
            "loading an unavailable failed position must not add restore "
            f"trace entries; found {len(entries_after) - 1} new ones"
        )
        # No app values were applied on load.
        expect(page.locator("#current_filter")).to_have_text(
            "all", timeout=10_000
        )
    else:
        # Complete snapshot: loading restores the failed node's own values
        # exactly once, and the callback sees the actual distinctive
        # captured-at-failure value, not the inherited parent value.
        expect(page.locator("#restore_count")).to_have_text("1", timeout=10_000)
        expect(page.locator("#region_filter")).to_have_value(
            FILTER_AT_FAILURE, timeout=10_000
        )
        expect(page.locator("#current_filter")).to_have_text(
            FILTER_AT_FAILURE, timeout=10_000
        )
        assert len(entries_after) == 2, (
            "loading a complete failed position must run on_restore exactly "
            f"once; found {len(entries_after) - 1} reload entries"
        )
        assert entries_after[-1]["values"].get("filter") == FILTER_AT_FAILURE, (
            "the reload callback must see the failed node's actual saved "
            "values, not inherited parent values: "
            f"{entries_after[-1]['values']}"
        )
    # The capture poison is a live-model fault, not persisted state.
    expect(page.locator("#model_poisoned")).to_have_text(
        "false", timeout=10_000
    )

    reloaded = read_record(page)
    post_node = {k: reloaded["nodes"][bp_id].get(k) for k in tracked_fields}
    assert post_node == pre_node, "reloading rewrote the failed node"
    assert reloaded.get("active_leaf") == bp_id, (
        "reloading moved the selection away from the failed node; "
        f"active_leaf={reloaded.get('active_leaf')!r}"
    )
    assert_failed_edit_recorded(reloaded, app_values=app_values)
    assert_original_branch_retained(reloaded)


def test_history_node_first_browse_and_retry_recovers(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Contract regression: with the app callback still broken, browse the
    original B, return to the failed B', fix the app selector, then click
    Retry while the live model getter is still poisoned. The valid parent
    must be restored without close-capturing B's poisoned live model, and a
    new sibling must succeed exactly once -- preserving the failed node, the
    original descendants, the selection, the parent-prefix model context and
    the composer draft."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    saves_before = _begin_failing_edit(
        page, chat, "restore_throw", draft=DRAFT_TEXT
    )
    assert_b_prime_displayed(page)
    record = wait_for_record(page, MSG_B_PRIME)
    bp_id = assert_failed_edit_recorded(record, app_values="unavailable")
    # The automatic capture ran exactly once and its on_save raised
    # mid-capture, so the failed node's snapshot is explicitly unavailable.
    assert_save_count(page, saves_before + 1)
    assert_failed_node_affordances(page, chat)

    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
    # The server transcript after failure settlement already shows the
    # failed position (A, Echo A, B' with no response) -- the same outgoing
    # view that a fresh load and the browse callback below must see. A lag
    # here means the terminal display was not installed after the failure:
    # an explicit production gap, not a test expectation to weaken.
    expect(page.locator("#chat_messages")).to_have_text(
        json.dumps(FAILED_POSITION_PREFIX), timeout=10_000
    )

    # --- Original <-> failed navigation with the callback still broken. ---
    browse_index = len(peek_samples(page))
    sibling_nav.get_by_role("button", name="Previous version").click()
    # Browsing the original shows its own branch; the failed edit is off-path.
    # The display replay installs the browsed target's full remembered
    # branch -- B_BRANCH_PREFIX, through the remembered descendant C -- so
    # every accepted input and echo of the original branch is on screen
    # (the live model deliberately keeps the edit-time parent context
    # instead; asserted on the trace below).
    for expected in B_BRANCH_PREFIX:
        role_class = (
            ".shiny-chat-user-message"
            if expected["role"] == "user"
            else ".shiny-chat-message"
        )
        expect(
            page.locator(role_class).filter(has_text=expected["content"])
        ).to_have_count(1, timeout=30_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    ).to_have_count(1, timeout=30_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_C)
    ).to_have_count(1, timeout=10_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B_PRIME)
    ).to_have_count(0, timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("1 / 2", timeout=5_000)
    # The broken browse: the ordinary app-restore failure read-only bar, and
    # no Retry/Edit affordance on the valid original.
    bar = chat.loc.locator(".shiny-chat-readonly")
    expect(bar).to_be_visible(timeout=30_000)
    expect(bar.get_by_role("status")).to_contain_text(
        "couldn't be restored", timeout=10_000
    )
    expect(chat.loc.get_by_role("button", name="Retry message")).to_have_count(
        0
    )
    expect(chat.loc.get_by_role("button", name="Edit message")).to_have_count(0)
    # Ordinary browsing still runs on_restore for the browsed position.
    expect(page.locator("#restore_count")).to_have_text("2", timeout=30_000)

    # Return to the failed node while still broken: restoring the failed
    # position must not invoke on_restore with inherited parent values.
    sibling_nav.get_by_role("button", name="Next version").click()
    assert_b_prime_displayed(page)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    ).to_have_count(0, timeout=10_000)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_C)
    ).to_have_count(0, timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
    expect(page.locator("#restore_count")).to_have_text("2", timeout=10_000)
    assert_failed_node_affordances(page, chat)
    record = wait_for_record_where(
        page,
        lambda r: r.get("active_leaf") == bp_id,
        description="the selection returned to the failed node",
    )
    assert record.get("active_leaf") == bp_id, (
        "returning from the original must re-select the failed node; "
        f"active_leaf={record.get('active_leaf')!r}"
    )
    assert_failed_node(record, bp_id, app_values="unavailable")

    # --- Fix the app; the live model getter is still poisoned. ---
    page.locator("#fault_mode").select_option("none")
    expect(page.locator("#model_poisoned")).to_have_text("true", timeout=10_000)

    # --- Explicit Retry while the live model is still poisoned. ---
    retry_index = len(peek_samples(page))
    chat.loc.get_by_role("button", name="Retry message").click()
    chat.expect_latest_message(f"Echo: {MSG_B_PRIME}", timeout=30_000)

    # Exactly one normal submission for the new sibling: 3 -> 4 everywhere.
    expect(page.locator("#provider_calls")).to_have_text("4", timeout=10_000)
    expect(page.locator("#submit_count")).to_have_text("4", timeout=10_000)
    expect(page.locator("#user_input_count")).to_have_text("4", timeout=10_000)
    expect(page.locator("#user_input_text")).to_have_text(
        MSG_B_PRIME, timeout=10_000
    )
    # The retry's parent restore ran the fixed callback once.
    expect(page.locator("#restore_count")).to_have_text("3", timeout=10_000)
    # The parent's app values were applied by the fixed callback.
    expect(page.locator("#region_filter")).to_have_value("all", timeout=10_000)
    expect(page.locator("#current_filter")).to_have_text("all", timeout=10_000)
    # The parent apply rewound the model and cleared the capture fault.
    expect(page.locator("#model_poisoned")).to_have_text(
        "false", timeout=10_000
    )

    # Read-only cleared: the composer is back with the preserved draft.
    expect(chat.loc.locator(".shiny-chat-readonly")).to_have_count(
        0, timeout=10_000
    )
    expect(chat.loc_input).to_be_visible(timeout=10_000)
    expect(chat.loc_input).to_have_text(DRAFT_TEXT, timeout=10_000)

    # The new sibling is displayed (same input text as B'), selected as 3 / 3.
    assert_b_prime_displayed(page)
    expect(
        page.locator(".shiny-chat-user-message").filter(has_text=MSG_B)
    ).to_have_count(0, timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("3 / 3", timeout=5_000)

    # No transient removal or rollback: before the browse, and across the
    # retry, the edited input never disappears and the original never
    # reappears.
    samples = collect_samples(page)
    assert_no_rollback(samples[:browse_index])
    assert_stable_presence(
        samples, retry_index, must_text=MSG_B_PRIME, forbidden_text=MSG_B
    )

    # --- Record: a new successful sibling; the failed node is not rewritten.
    record = wait_for_record_where(
        page,
        lambda r: len(_ok_node_ids(r, MSG_B_PRIME)) == 1,
        description="the retry's new sibling recorded with an ok outcome",
        timeout_s=20.0,
    )
    ids_a = _node_ids_with_input(record, MSG_A)
    ids_bp = _node_ids_with_input(record, MSG_B_PRIME)
    assert len(ids_a) == 1, f"expected exactly one A node, found {ids_a}"
    assert len(ids_bp) == 2, (
        f"expected the failed B' plus its retry sibling, found {ids_bp}"
    )
    b2_id = _ok_node_ids(record, MSG_B_PRIME)[0]
    assert b2_id != bp_id, "the retry must create a new node, not reuse B'"
    b2 = record["nodes"][b2_id]
    assert b2["parent_id"] == ids_a[0], "the retry sibling must be a child of A"
    assert b2.get("checkpoint") != "invalid", (
        f"the retry sibling must not inherit the failed checkpoint: {b2!r}"
    )
    responses = [
        m
        for m in b2.get("messages") or []
        if isinstance(m, dict) and m.get("role") == "assistant"
    ]
    assert len(responses) == 1, (
        f"expected one response message, got {responses}"
    )
    assert f"Echo: {MSG_B_PRIME}" in _segments_text(responses[0])
    assert_attachment_fidelity(record, b2_id)
    assert record.get("active_leaf") == b2_id, (
        "the retry sibling must be the selected position; "
        f"active_leaf={record.get('active_leaf')!r}"
    )
    # The failed B' node was not rewritten by the recovery.
    assert_failed_node(record, bp_id, app_values="unavailable")
    assert_original_branch_retained(record)

    # --- Model context: each on_restore observation, separately. ---
    entries = restore_enter_entries(read_trace(page))
    assert len(entries) == 3, (
        "expected exactly three on_restore invocations (edit-time failure, "
        f"broken browse of the original, retry parent restore); got {len(entries)}"
    )
    # 1. The edit-time failure observed the parent prefix.
    assert_edit_time_parent_prefix_entry(entries[0])
    # 2. Ordinary browse semantics are deliberately unchanged by the
    #    node-first contract: the callback retains the OUTGOING transcript
    #    until the replay installs the target view (loads and browses see
    #    the same view), receives the TARGET's recorded values, and --
    #    because read-only display-only navigation never invokes the
    #    builtin model rewind hooks (pre-existing production behavior the
    #    contract preserves) -- the live model still holds the edit-time
    #    parent context, still poisoned. The browsed target's full
    #    remembered branch (B_BRANCH_PREFIX) is installed on screen
    #    (asserted on the displayed rows above), never applied to the live
    #    model: the trace must prove the browse did not touch it.
    browse_entry = entries[1]
    assert browse_entry["chat_messages"] == FAILED_POSITION_PREFIX, (
        "the browse callback must observe the outgoing failed-position "
        "transcript (loads and browses see the same view), not the new "
        f"target's display; got {browse_entry['chat_messages']}"
    )
    assert browse_entry["client_turns"] == PARENT_PREFIX, (
        "the browse callback's live model must still hold the edit-time "
        "parent context: read-only display-only navigation deliberately "
        "never rewinds the live model, so the target's remembered branch "
        f"must not be applied at browse time; got {browse_entry['client_turns']}"
    )
    assert browse_entry["values"].get("filter") == "all", (
        f"the browsed original's app values were wrong: {browse_entry['values']}"
    )
    # 3. The retry's parent restore observed the parent prefix with the model
    #    already rewound: the fixture's poison only clears when a saved
    #    parent is applied, so this proves the retry restored the valid
    #    parent instead of close-capturing B's poisoned live model.
    retry_entry = entries[2]
    assert_edit_time_parent_prefix_entry(retry_entry)
    assert retry_entry["values"].get("filter") == "all", (
        "the retry must restore the valid parent's app values; got "
        f"{retry_entry['values']}"
    )


def test_history_node_first_retry_failure_creates_new_sibling(
    page: Page, local_app: ShinyAppProc
) -> None:
    """Contract regression: an intentional Retry with the capture fault still
    active fails again, and that failure must be preserved as a NEW failed
    sibling -- never a rewrite of the original failed node -- with no model
    dispatch, no accepted input, and no transient removal of the displayed
    edit."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)

    saves_before = _begin_failing_edit(page, chat, "capture_poison")
    assert_b_prime_displayed(page)
    record = wait_for_record(page, MSG_B_PRIME)
    bp_id = assert_failed_edit_recorded(record, app_values="complete")
    # The automatic capture ran exactly once and serialized, so the
    # failed node's snapshot is explicitly complete (with the distinctive
    # captured-at-failure value).
    assert_save_count(page, saves_before + 1)
    assert_failed_node_affordances(page, chat)
    expect(page.locator("#model_poisoned")).to_have_text("true", timeout=10_000)
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)

    tracked_fields = (
        "parent_id",
        "checkpoint",
        "status",
        "error",
        "input",
        "state",
    )
    pre_node = {k: record["nodes"][bp_id].get(k) for k in tracked_fields}

    retry_index = len(peek_samples(page))
    chat.loc.get_by_role("button", name="Retry message").click()
    # The retry's parent restore ran the still-broken callback once more.
    expect(page.locator("#restore_count")).to_have_text("2", timeout=30_000)
    # The new failed sibling is displayed and selected as 3 / 3.
    expect(sibling_nav.locator("span")).to_have_text("3 / 3", timeout=30_000)
    assert_b_prime_displayed(page)
    assert_failed_node_affordances(page, chat)
    # The second failure dispatched and accepted nothing, again.
    assert_no_extra_callbacks(page)
    expect(page.locator("#user_input_text")).to_have_text(MSG_C, timeout=10_000)
    # The still-active fault re-poisoned the model after the parent apply.
    expect(page.locator("#model_poisoned")).to_have_text("true", timeout=10_000)
    # Each of the two pre-admission failures ran the automatic capture
    # exactly once: one more invocation since the first failure settled.
    assert_save_count(page, saves_before + 2)

    # No transient removal or rollback across the failed retry.
    samples = collect_samples(page)
    assert_stable_presence(
        samples, retry_index, must_text=MSG_B_PRIME, forbidden_text=MSG_B
    )

    # --- Record: a new failed sibling; the original failed node is intact.
    record = wait_for_record_where(
        page,
        lambda r: len(_node_ids_with_input(r, MSG_B_PRIME)) == 2,
        description="the intentional retry recorded a new failed sibling",
        timeout_s=20.0,
    )
    ids_a = _node_ids_with_input(record, MSG_A)
    ids_bp = _node_ids_with_input(record, MSG_B_PRIME)
    assert len(ids_a) == 1, f"expected exactly one A node, found {ids_a}"
    assert len(ids_bp) == 2, f"expected two failed siblings, found {ids_bp}"
    new_id = next(i for i in ids_bp if i != bp_id)
    assert record.get("active_leaf") == new_id, (
        "the newly failed sibling must be the selected position, not the "
        f"original failed node; active_leaf={record.get('active_leaf')!r}"
    )
    for node_id in ids_bp:
        node = record["nodes"][node_id]
        assert node["parent_id"] == ids_a[0], (
            f"failed sibling {node_id} must be a child of A"
        )
        assert_failed_node(record, node_id, app_values="complete")
        assert_attachment_fidelity(record, node_id)
    # The original failed node was not rewritten by the failed retry.
    post_node = {k: record["nodes"][bp_id].get(k) for k in tracked_fields}
    assert post_node == pre_node, (
        "the failed retry rewrote the original failed node"
    )
    assert_original_branch_retained(record)

    # --- Model context: the retry's edit-time restore observed the parent
    #     prefix with the model already rewound (the fixture's poison only
    #     clears on parent apply). ---
    entries = restore_enter_entries(read_trace(page))
    assert len(entries) == 2, (
        "expected exactly two on_restore invocations (edit-time failure and "
        f"the retry parent restore); got {len(entries)}"
    )
    assert_edit_time_parent_prefix_entry(entries[1])
    assert entries[1]["values"].get("filter") == "all", (
        f"the retry must restore the parent's app values: {entries[1]['values']}"
    )


def test_history_node_first_healthy_branch_writable_after_failed_visit(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A display-only failed visit must not lock a healthy branch permanently."""
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    _begin_failing_edit(page, chat, "capture_poison", draft=DRAFT_TEXT)
    assert_b_prime_displayed(page)
    assert_failed_node_affordances(page, chat)
    page.locator("#fault_mode").select_option("none")
    expect(page.locator("#model_poisoned")).to_have_text("true")
    chat.loc.get_by_role("button", name="Retry message").click()
    chat.expect_latest_message(f"Echo: {MSG_B_PRIME}", timeout=30_000)
    expect(chat.loc_input).to_be_visible()
    expect(page.locator("#provider_calls")).to_have_text("4")
    healthy = wait_for_record_where(
        page,
        lambda r: (
            len(_node_ids_with_input(r, MSG_B_PRIME)) == 2
            and r["nodes"][r["active_leaf"]]["status"] == "ok"
        ),
        description="the healthy retry checkpoint",
    )
    healthy_id = healthy["active_leaf"]
    nav = page.locator(".shiny-chat-sibling-nav")
    expect(nav.locator("span")).to_have_text("3 / 3")

    nav.get_by_role("button", name="Previous version").click()
    expect(nav.locator("span")).to_have_text("2 / 3")
    assert_failed_node_affordances(page, chat)
    nav.get_by_role("button", name="Next version").click()
    expect(nav.locator("span")).to_have_text("3 / 3")
    chat.expect_latest_message(f"Echo: {MSG_B_PRIME}")
    expect(chat.loc.locator(".shiny-chat-readonly")).to_have_count(0)
    expect(chat.loc_input).to_be_visible()
    expect(chat.loc_input).to_have_text(DRAFT_TEXT)
    expect(chat.loc_input_button).to_be_enabled()
    expect(page.locator("#current_filter")).to_have_text("all")
    expect(page.locator("#model_poisoned")).to_have_text("false")
    expect(page.locator("#provider_calls")).to_have_text("4")
    expect(page.locator("#submit_count")).to_have_text("4")
    expect(page.locator("#user_input_count")).to_have_text("4")
    selected = wait_for_record_where(
        page,
        lambda r: r["active_leaf"] == healthy_id,
        description="the healthy branch selected after a failed visit",
    )
    assert_original_branch_retained(selected)
    collect_samples(page)
