"""Playwright regression tests for the #459 edit hold.

Submitting an edit keeps the editor mounted and locked (draft text,
attachments, and its Cancel control) until the server responds: a
matching ``history_transition_rejected`` unlocks the editor with the
draft intact and a user-safe reason, and acceptance projects the
replacement as before. The fixture exercises the real ddxb invalid-root
refusal (a failed first-input on_save makes message 1 uneditable while
message 2 stays editable); ``app.py`` parks the edit server-side at an
out-of-band gate so the held state can be asserted without sleeps.
"""

from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, expect
from shiny.run import ShinyAppProc
from shinychat.playwright import ChatController

HERE = Path(__file__).parent

REFUSAL_REASON = (
    "This message cannot be resubmitted because its previous state "
    "checkpoint is unavailable."
)


def _make_request(page: Page, handler: str, args: list[Any]) -> Any:
    """Call a websocket message handler and await its response.

    Shiny dispatches tagged requests in their own tasks, outside the
    reactive cycle, so the awaited response confirms the call was applied
    even while a gated edit effect keeps its cycle busy.
    """
    return page.evaluate(
        """([handler, args]) => new Promise((resolve, reject) => {
            Shiny.shinyapp.makeRequest(handler, args, resolve, reject);
        })""",
        [handler, args],
    )


def _wait_gate_state(page: Page, state: str) -> None:
    """Wait for a gate transition the app pushes to the page."""
    page.wait_for_function(
        "s => window.__shinychatEditGate && window.__shinychatEditGate.state === s",
        arg=state,
        timeout=30_000,
    )


def _setup_conversation(page: Page, chat: ChatController) -> None:
    """Build the conversation used by both tests.

    Arm the one-shot on_save failure, then send the first input: the
    root_close capture fails, so the root finishes invalid (kata #ddxb)
    while message 1 is still admitted. Hard-check that record state before
    relying on it, then send a second message that settles on exchange 1's
    valid checkpoint: editing message 1 will be refused, editing message 2
    accepted.
    """
    page.get_by_role("button", name="Break first-input on_save").click()
    expect(page.locator("#onsave_status")).to_have_text("armed")

    chat.set_user_input("hello")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: hello", timeout=30_000)
    expect(page.locator("#onsave_status")).to_have_text(
        "first-input on_save failed"
    )

    probe = _make_request(page, "shinyChatFixtureProbe", [])
    assert probe["root_status"] == "ok", probe
    assert probe["root_checkpoint"] == "invalid", probe
    assert probe["user_inputs"] == ["hello"], probe

    chat.set_user_input("world")
    expect(chat.loc_input_button).to_be_enabled(timeout=30_000)
    chat.send_user_input(method="enter")
    chat.expect_latest_message("echo: world", timeout=30_000)
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 2"
    )


def _open_edit(page: Page, nth: int) -> tuple[Locator, Locator, Locator]:
    """Open the edit box on the nth user message."""
    user = page.locator(".shiny-chat-user-message").nth(nth)
    user.hover()
    edit_btn = user.locator(".shiny-chat-edit-btn")
    expect(edit_btn).to_be_visible(timeout=5_000)
    edit_btn.click()

    edit_box = user.locator(".shiny-chat-edit-box")
    editor = user.get_by_role("textbox", name="Chat message")
    expect(editor).to_be_visible(timeout=5_000)
    return user, edit_box, editor


def _stage_draft(
    edit_box: Locator, editor: Locator, draft: str, seed: str
) -> None:
    """Replace the seeded text with `draft` and stage one attachment."""
    expect(editor).to_have_text(seed)
    editor.click()
    editor.press("ControlOrMeta+a")
    editor.press_sequentially(draft)
    edit_box.locator("input[type=file]").set_input_files(
        str(HERE / "one_px.png")
    )
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)


def _expect_held(
    page: Page, user: Locator, edit_box: Locator, editor: Locator, draft: str
) -> None:
    """The #459 held state while the server has the edit request parked."""
    # The editor stays mounted with the draft text and attachment.
    expect(editor).to_be_visible()
    expect(editor).to_have_text(draft)
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)
    # Locked, mirroring #453's composer hold: readonly editor with Save
    # and Cancel disabled.
    expect(editor).to_have_attribute("aria-readonly", "true")
    expect(edit_box.locator(".shiny-chat-btn-send")).to_be_disabled()
    expect(user.locator(".shiny-chat-edit-cancel-outside")).to_be_disabled()
    expect(page.locator(".shiny-notification")).to_have_count(0)


def test_refused_edit_holds_draft_until_rejection_then_unlocks(
    page: Page, local_app: ShinyAppProc
) -> None:
    """A refused edit: hold -> refusal unlocks with the draft intact.

    Enter must not clear the held editor; the invalid-checkpoint refusal
    (message 1's parent is the invalid first-input root) arrives with its
    user-safe reason and unlocks the editor with the draft (text and
    attachment) intact; a retry from the unlocked editor is refused again;
    canceling leaves the conversation unchanged.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    _setup_conversation(page, chat)

    # Arm the gate: the next edit request parks before any validation.
    assert _make_request(page, "shinyChatEditGateControl", ["hold"])["holding"]

    user, edit_box, editor = _open_edit(page, 0)
    _stage_draft(edit_box, editor, "hello edited", "hello")

    # Submit with Enter; the edit box must stay open and locked until the
    # server accepts or refuses.
    editor.press("Enter")
    _wait_gate_state(page, "parked")
    _expect_held(page, user, edit_box, editor, "hello edited")

    # Enter inside the held editor must not clear or resubmit the draft.
    editor.press("Enter")
    expect(editor).to_have_text("hello edited")
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)
    expect(page.locator(".shiny-notification")).to_have_count(0)

    # Release the gate: the server refuses at the checkpoint gate.
    _make_request(page, "shinyChatEditGateControl", ["release"])

    # The refusal unlocks the editor with the draft intact and shows its
    # user-safe reason.
    toast = page.locator(".shiny-notification")
    expect(toast).to_be_visible(timeout=30_000)
    expect(toast).to_contain_text(REFUSAL_REASON)
    expect(editor).to_have_text("hello edited")
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)
    expect(editor).not_to_have_attribute("aria-readonly", "true")
    expect(edit_box.locator(".shiny-chat-btn-send")).to_be_enabled()
    expect(user.locator(".shiny-chat-edit-cancel-outside")).to_be_enabled()

    # The conversation is unchanged: no new response, no sibling branch,
    # and no provider dispatch for the refused edit.
    expect(chat.loc).not_to_contain_text("echo: hello edited")
    expect(page.locator(".shiny-chat-sibling-nav")).to_have_count(0)
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 2"
    )

    # Retry from the unlocked editor (the gate is one-shot, so this
    # refusal resolves immediately): refused again, draft still intact.
    toast.locator(".shiny-notification-close").click()
    expect(toast).to_have_count(0)
    editor.press("Enter")
    expect(toast).to_be_visible(timeout=30_000)
    expect(toast).to_contain_text(REFUSAL_REASON)
    expect(editor).to_have_text("hello edited")
    expect(edit_box.locator(".shiny-chat-input-thumbnail img")).to_have_count(1)

    # Canceling closes the editor; message 1 is still its original self.
    user.locator(".shiny-chat-edit-cancel-outside").click()
    expect(edit_box).to_have_count(0)
    expect(user).to_contain_text("hello")
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 2"
    )


def test_accepted_edit_holds_then_projection_replaces_message(
    page: Page, local_app: ShinyAppProc
) -> None:
    """An accepted edit: hold -> projection saves and closes.

    The editor is held and locked while the server awaits; the original
    message is replaced only when acceptance projects the replacement,
    which lands as a normal sibling branch with the draft's attachment.
    """
    page.goto(local_app.url)
    chat = ChatController(page, "chat")
    expect(chat.loc).to_be_visible(timeout=30_000)
    _setup_conversation(page, chat)

    assert _make_request(page, "shinyChatEditGateControl", ["hold"])["holding"]

    user, edit_box, editor = _open_edit(page, 1)
    _stage_draft(edit_box, editor, "world edited", "world")

    # Submit with the Save button (Enter is exercised in the refusal test).
    edit_box.locator(".shiny-chat-btn-send").click()
    _wait_gate_state(page, "parked")
    _expect_held(page, user, edit_box, editor, "world edited")

    # Release the gate: the server accepts the edit (message 2's parent is
    # exchange 1's valid checkpoint) and projects the replacement.
    _make_request(page, "shinyChatEditGateControl", ["release"])
    _wait_gate_state(page, "released")

    # The projection closes the editor, replaces the message with the
    # draft text and exactly one attachment, and regenerates the response.
    chat.expect_latest_message("echo: world edited", timeout=30_000)
    expect(edit_box).to_have_count(0)
    expect(user).to_contain_text("world edited")
    expect(user.locator(".shiny-chat-message-image")).to_have_count(1)
    expect(page.locator("#dispatch_count")).to_have_text(
        "Provider dispatches: 3"
    )

    # The accepted edit opened a sibling branch of the original message.
    sibling_nav = page.locator(".shiny-chat-sibling-nav")
    expect(sibling_nav).to_be_visible(timeout=10_000)
    expect(sibling_nav.locator("span")).to_have_text("2 / 2", timeout=5_000)
