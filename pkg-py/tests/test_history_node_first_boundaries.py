"""Node-first staged resubmission boundary regressions.

Every test here drives the production owners (real ``Chat`` +
``HistoryController`` + ``_ExchangeRecorder``) through the guarded staged
admission seam. No test re-implements admission, keeps an attempt ledger,
or bypasses the destructive-history guard: fault injection only replaces
the live model adapter, the conversation store, or the display transport,
each of which is a real fallible production dependency.

The boundaries pinned here come from the approved failed-attempt contract:

* One ordinary exchange node is recorded before any fallible preparation,
  so an outgoing model close-capture failure still leaves the attempted
  edit as a known terminal incomplete node while the original branch and
  its descendants stay intact.
* A failure before admission is a sanitized "message not sent" outcome; a
  storage failure *after* the shared transcript/tree commit is never
  relabeled "not sent", publishes no new accepted events beyond the
  baseline ordinary-input policy, and leaves the accepted exchange open.
* One staged submission is admitted exactly once: a replayed capability
  or a second capability for the same staged ID is rejected before any
  second capture, commit, or callback.
* A terminal persistence or display delivery failure retains the failed
  working node; the durable store never claims an outcome it did not save.
* The failed-node marker never bypasses source isolation, live-producer,
  or model-unavailable protections, and ``checkpoint=invalid`` or a
  terminal status alone never classifies a node as a stopped producer.
"""

import json
from typing import Any, Callable, cast
from unittest.mock import patch

import pytest
from shinychat._chat_transcript import StagedInputAdmission
from shinychat._chat_types import ChatMessage, StoredMessage, StoredSegment
from shinychat._history_controller import HistoryController
from shinychat._history_plan import canonical_values
from shinychat._history_recorder import _ModelCaptureError
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
)
from shinychat._history_types import (
    HISTORY_ERROR_NOT_SENT,
    PREPARATION_ENTRY_KIND,
    PREPARATION_ENTRY_VERSION,
    PREPARATION_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationRecordV1,
    ConversationRecordV2,
    ExchangeNode,
    StateEntry,
    is_valid_preparation_entry,
    node_is_terminal_incomplete,
)
from test_history_controller import (
    _FakeAdapter,
    _make_v2_resubmit_real_chat,
    _seed_resubmit_transcript,
    _spy_send_actions,
    _stored_message,
    _wire_resubmit_capture,
)

# The edited content and indices used by the fixture: message index 2 is
# the abandoned "second" input whose parent prefix is
# ["first", "reply one"].
EDIT_INDEX = 2
EDIT_CONTENT = "second edited"
PREFIX_CONTENTS = ["first", "reply one"]


def _preparation_envelope(app_values: str) -> StateEntry:
    """The exact durable preparation envelope for a failed submission."""
    return StateEntry(
        kind=PREPARATION_ENTRY_KIND,
        version=PREPARATION_ENTRY_VERSION,
        mode="snapshot",
        data={"terminal": True, "accepted": False, "app_values": app_values},
    )


class _PoisonableAdapter(_FakeAdapter):
    """A real fake adapter whose live model getter can fail on demand."""

    def __init__(self, *, turns: list[dict[str, Any]]) -> None:
        super().__init__()
        self.turns = turns
        self.system_turns = [{"role": "system", "content": "bootstrap"}, *turns]
        self.fault: BaseException | None = None
        self.consumed_fault = False

    def get_turns_json(
        self, *, include_system_prompt: bool = False
    ) -> list[dict[str, Any]]:
        if self.fault is not None:
            # Remember that the poisoned fault fired so a test can arm
            # later fault injection (e.g. display delivery) after it.
            self.consumed_fault = True
            raise self.fault
        return super().get_turns_json(
            include_system_prompt=include_system_prompt
        )


class _SnapshotStore(ConversationStore):
    """A real store that keeps every persisted snapshot, with fault arming.

    ``fail_when`` inspects each put's detached snapshot before the write;
    the one armed fault raises instead of persisting, so the durable state
    only ever contains snapshots that were actually accepted.
    """

    def __init__(self) -> None:
        self.snapshots: list[ConversationRecordV1 | ConversationRecordV2] = []
        self.fail_when: (
            Callable[[ConversationRecordV1 | ConversationRecordV2], bool] | None
        ) = None
        self.fault: BaseException | None = None
        self.failed_puts = 0

    async def list(self, partition: ConversationPartition) -> list[Any]:
        return []

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV1 | ConversationRecordV2 | None:
        return None

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        pass

    async def put(
        self,
        partition: ConversationPartition,
        record: ConversationRecordV1 | ConversationRecordV2,
    ) -> None:
        if self.fail_when is not None and self.fail_when(record):
            self.failed_puts += 1
            raise (
                self.fault if self.fault is not None else OSError("disk full")
            )
        self.snapshots.append(record)

    @property
    def last_snapshot(self) -> ConversationRecordV1 | ConversationRecordV2:
        assert self.snapshots, "no snapshot was persisted"
        return self.snapshots[-1]


def _count_accepted_publications(
    chat: Any,
) -> list[StoredMessage]:
    """Count accepted-input publications through the real signal seam."""
    published: list[StoredMessage] = []
    original = chat._latest_user_input.set

    def record_set(value: StoredMessage) -> None:
        published.append(value)
        original(value)

    chat._latest_user_input.set = record_set  # type: ignore[method-assign]
    return published


async def _make_editable_chat(
    request: pytest.FixtureRequest,
    *,
    chat_id: str,
    save_callbacks: list[Callable[[dict[str, Any]], None]] | None = None,
) -> tuple[
    HistoryController,
    Any,
    _PoisonableAdapter,
    _SnapshotStore,
    str,
    str,
]:
    """The resubmit fixture with a real Chat plus the fallible seams armed.

    The live model adapter is replaced before the edit so a test can
    poison the outgoing close capture or the admission capture; the store
    is replaced with one that keeps snapshots so durable honesty can be
    asserted. Seeding and capture wiring follow the production order used
    by the sibling fixtures.
    """
    controller, chat, adapter, _recording_store, first, target = (
        _make_v2_resubmit_real_chat(request, chat_id=chat_id)
    )
    poisonable = _PoisonableAdapter(turns=list(adapter.turns))
    controller.adapter = poisonable  # type: ignore[assignment]
    store = _SnapshotStore()
    controller.store = store  # type: ignore[assignment]
    for callback in save_callbacks or []:
        controller._save_callbacks.append(callback)
    await _seed_resubmit_transcript(chat, first, target)
    _wire_resubmit_capture(controller, chat)
    return controller, chat, poisonable, store, first, target


def _assert_failed_node(
    controller: HistoryController, *, parent_id: str, app_values: str
) -> str:
    """Assert the retained terminal incomplete node and return its id."""
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    assert record.active_leaf is not None
    node = record.nodes[record.active_leaf]
    assert node.parent_id == parent_id
    assert node.input is not None
    assert node.input.content == EDIT_CONTENT
    assert node.status == "error"
    assert node.error is not None
    assert node.error.message == HISTORY_ERROR_NOT_SENT
    assert node.checkpoint == "invalid"
    assert node.state[PREPARATION_STATE_KEY] == _preparation_envelope(
        app_values
    )
    assert is_valid_preparation_entry(node.state[PREPARATION_STATE_KEY])
    assert node_is_terminal_incomplete(node)
    # A known terminal incomplete leaf is an explicit display destination.
    assert record.checkpoint_leaf(record.active_leaf) == record.active_leaf
    return record.active_leaf


def _captured_contents(node: ExchangeNode) -> list[str]:
    """The text contents of a node's captured messages."""
    return [
        str(cast(StoredSegment, captured.segments[0]).content)
        for captured in node.messages
    ]


def _messages(chat: Any) -> list[str]:
    return [str(message["content"]) for message in chat.messages()]


# ---------------------------------------------------------------------------
# Success: one ordinary node, same staged ID committed exactly once
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_edit_success_stages_one_node_and_admits_same_id_once(
    request: pytest.FixtureRequest,
) -> None:
    """A successful edit records one ordinary node before fallible
    preparation and commits that same staged ID through the guarded
    admission seam exactly once, with the normal accepted signals."""
    (
        controller,
        chat,
        _adapter,
        store,
        first,
        target,
    ) = await _make_editable_chat(request, chat_id="node_first_success")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    original_ids = set(record.nodes)
    target_input = record.nodes[target].input
    assert target_input is not None
    original_target_input = target_input.model_copy(deep=True)
    # The settled pre-operation baseline of the abandoned target, as the
    # seeding captures left it (production settles an appended assistant
    # reply), rather than any hardcoded outcome.
    original_target_status = record.nodes[target].status
    original_target_messages = _captured_contents(record.nodes[target])
    publications = _count_accepted_publications(chat)
    sent = _spy_send_actions(chat)

    await controller.handle_edit(
        EDIT_INDEX,
        EDIT_CONTENT,
        [
            {
                "mime": "text/plain",
                "name": "notes.txt",
                "size": 5,
                "data_url": "data:text/plain;base64,aGVsbG8=",
            }
        ],
        request_id="edit-ok",
    )

    # Exactly one new node, under the original's valid parent.
    new_ids = set(record.nodes) - original_ids
    assert len(new_ids) == 1
    staged_id = new_ids.pop()
    assert record.active_leaf == staged_id
    node = record.nodes[staged_id]
    assert node.parent_id == first
    assert node.input is not None
    assert node.input.content == EDIT_CONTENT
    assert node.input.attachments[0].name == "notes.txt"
    # The accepted exchange stays an ordinary open node: no failure marker.
    assert node.status == "pending"
    assert node.checkpoint == "candidate"
    assert PREPARATION_STATE_KEY not in node.state
    assert not node_is_terminal_incomplete(node)

    # The original branch and its descendants are untouched.
    assert record.children_of(first) == [target, staged_id]
    assert record.nodes[target].input == original_target_input
    assert record.nodes[target].status == original_target_status
    assert _captured_contents(record.nodes[target]) == (
        original_target_messages
    )

    # The same staged ID was committed in the transcript, exactly once,
    # as an accepted open exchange, and the model sits at the parent.
    entries = [
        entry
        for entry in chat._transcript.read()
        if entry.exchange_id == staged_id
    ]
    assert len(entries) == 1
    assert chat._transcript.open_exchange_id == staged_id
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]
    assert _adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]

    # The normal accepted signals fired exactly once, and the client is
    # told the server already owns this submission (no echo round trip).
    assert [str(p.content) for p in publications] == [EDIT_CONTENT]
    projections = [
        action for action in sent if action["type"] == "history_edit_projection"
    ]
    assert len(projections) == 1
    assert projections[0]["requestId"] == "edit-ok"
    assert projections[0]["submission_mode"] == "server"
    assert projections[0]["exchange_id"] == staged_id
    assert projections[0]["attachments"][0]["name"] == "notes.txt"

    # The durable record keeps the accepted open exchange.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    assert snapshot.active_leaf == staged_id
    assert snapshot.nodes[staged_id].status == "pending"
    assert PREPARATION_STATE_KEY not in snapshot.nodes[staged_id].state


# ---------------------------------------------------------------------------
# Outgoing model close-capture failure still creates the failed node
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_outgoing_close_capture_failure_creates_failed_node(
    request: pytest.FixtureRequest,
) -> None:
    """The outgoing close capture runs *after* staging: when it throws, the
    edited input is already a retained terminal incomplete node, the
    original branch and its descendants are preserved, and no accepted
    input or provider work fires."""
    controller, chat, adapter, store, first, target = await _make_editable_chat(
        request, chat_id="node_first_outgoing_capture"
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    original_ids = set(record.nodes)
    original_target_status = record.nodes[target].status
    original_target_messages = _captured_contents(record.nodes[target])
    original_target_turns = record.nodes[target].state[TURNS_STATE_KEY]
    publications = _count_accepted_publications(chat)
    sent = _spy_send_actions(chat)
    adapter.fault = RuntimeError("the live model context is unavailable")

    with pytest.warns(UserWarning, match="recorded but not sent"):
        await controller.handle_edit(
            EDIT_INDEX, EDIT_CONTENT, request_id="edit-outgoing"
        )

    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )
    assert set(record.nodes) - original_ids == {failed_id}

    # The failed node keeps the one whole app snapshot: with no on_save
    # callbacks the captured values are the empty snapshot, not absent.
    assert record.nodes[failed_id].state[VALUES_STATE_KEY].data == {}

    # The original branch is fully preserved, including the recorded
    # context the failed capture could not rewrite.
    assert record.children_of(first) == [target, failed_id]
    target_node = record.nodes[target]
    assert target_node.input is not None
    assert target_node.input.content == "second"
    assert target_node.status == original_target_status
    assert target_node.state[TURNS_STATE_KEY] == original_target_turns
    assert _captured_contents(target_node) == original_target_messages

    # The failed row stays visible as a terminal display entry: never an
    # accepted exchange, never an open one, and the edit never rolled back
    # to the original branch.
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]
    assert chat._transcript.open_exchange_id is None
    assert publications == []

    # The model was never rewound past the failed capture, so no invented
    # provider or restore state exists.
    assert adapter.consumed_fault
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]

    # The selected position is read-only as a known terminal incomplete
    # submission, which an explicit Retry/Edit may revalidate.
    assert recorder.read_only
    assert recorder.read_only_reason == "terminal_incomplete"
    assert controller._can_resubmit_active()

    # The client metadata distinguishes "not sent" from a provider error.
    metadata_actions = [
        action
        for action in sent
        if action["type"] == "update_exchange_metadata"
    ]
    assert metadata_actions
    failed_metadata = metadata_actions[-1]["data"][EDIT_INDEX]
    assert failed_metadata["preparation_failed"] is True
    assert failed_metadata["error_message"] == HISTORY_ERROR_NOT_SENT
    assert failed_metadata["retryable"] is True

    # The terminal outcome is durable, so a reload keeps the failed node.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    failed_snapshot = snapshot.nodes[failed_id]
    assert failed_snapshot.status == "error"
    assert failed_snapshot.checkpoint == "invalid"
    assert failed_snapshot.state[PREPARATION_STATE_KEY] == (
        _preparation_envelope("complete")
    )


# ---------------------------------------------------------------------------
# Edit-time on_restore failure attaches to the same staged node
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_restore_callback_failure_attaches_to_staged_node(
    request: pytest.FixtureRequest,
) -> None:
    """An on_restore callback that mutates app state then throws leaves the
    edited input as the failed node, keeps whatever app facts the normal
    capture role observed, and rewinds only the model to the parent."""
    live: dict[str, str] = {"filter": "all"}
    capture_calls: list[dict[str, Any]] = []

    def save_live_filter(values: dict[str, Any]) -> None:
        values["filter"] = live["filter"]
        capture_calls.append(dict(values))

    controller, chat, adapter, store, first, target = await _make_editable_chat(
        request,
        chat_id="node_first_restore_throw",
        save_callbacks=[save_live_filter],
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)

    def mutate_then_throw(values: dict[str, Any]) -> None:
        live["filter"] = "restored"
        raise ValueError("app restore exploded")

    controller._restore_callbacks.append(mutate_then_throw)

    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_edit(
            EDIT_INDEX, EDIT_CONTENT, request_id="edit-restore"
        )

    # The single failed node carries a complete snapshot of the mutated
    # live app facts: a restore failure never blocks the one on_save role.
    assert live["filter"] == "restored"
    assert capture_calls == [{"filter": "restored"}]
    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )
    node = record.nodes[failed_id]
    assert node.state[VALUES_STATE_KEY].data == {"filter": "restored"}

    # The conversation is view-only because the app restore failed; that
    # restriction is one an explicit resubmit may revalidate.
    assert recorder.read_only
    assert recorder.read_only_reason == "app_restore_failed"
    assert controller._can_resubmit_active()

    # The model and transcript sit at the parent prefix with the failed
    # row retained, and nothing accepted the input.
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]
    assert chat._transcript.open_exchange_id is None
    assert publications == []

    # Original descendants preserved.
    assert record.children_of(first) == [target, failed_id]

    # Durable terminal outcome.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    assert snapshot.nodes[failed_id].state[PREPARATION_STATE_KEY] == (
        _preparation_envelope("complete")
    )


# ---------------------------------------------------------------------------
# Complete vs unavailable whole app snapshots at the failed position
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case",
    ["complete-canonical", "callback-throws", "unserializable-value"],
)
async def test_failed_node_app_values_whole_snapshot_policy(
    request: pytest.FixtureRequest,
    case: str,
) -> None:
    """The failed node records either one complete canonical-JSON snapshot
    or nothing at all: a snapshot is complete only when every callback
    finished and the whole snapshot serialized, and the ordinary capture
    role runs exactly once either way."""

    def fill(values: dict[Any, Any]) -> None:
        values[2] = "two"
        values["tab"] = "all"

    def throw(_values: dict[str, Any]) -> None:
        raise ValueError("on_save exploded")

    def nan(values: dict[str, Any]) -> None:
        values["bad"] = float("nan")

    fill_calls: list[int] = []

    def counting_fill(values: dict[str, Any]) -> None:
        fill_calls.append(1)
        fill(values)

    save_callbacks: list[Callable[[dict[str, Any]], None]]
    if case == "complete-canonical":
        save_callbacks = [counting_fill]
    elif case == "callback-throws":
        save_callbacks = [counting_fill, throw]
    else:
        save_callbacks = [counting_fill, nan]

    (
        controller,
        chat,
        adapter,
        _store,
        first,
        _target,
    ) = await _make_editable_chat(
        request,
        chat_id=f"node_first_values_{case.replace('-', '_')}",
        save_callbacks=save_callbacks,
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    adapter.fault = RuntimeError("model capture unavailable")

    with pytest.warns(UserWarning, match="recorded but not sent"):
        await controller.handle_edit(
            EDIT_INDEX, EDIT_CONTENT, request_id=f"edit-{case}"
        )

    assert record.active_leaf is not None
    node = record.nodes[record.active_leaf]
    assert publications == []
    # The capture role ran exactly once.
    assert len(fill_calls) == 1

    if case == "complete-canonical":
        # Whole snapshot, canonical JSON encoding (author-owned
        # round-trip semantics, no stricter whitelist).
        expected = canonical_values({2: "two", "tab": "all"})
        assert expected == {"2": "two", "tab": "all"}
        assert node.state[PREPARATION_STATE_KEY] == _preparation_envelope(
            "complete"
        )
        assert node.state[VALUES_STATE_KEY].data == expected
        json.dumps(node.state[VALUES_STATE_KEY].data)
    else:
        # Incomplete: unavailable, with no partial fragment tree.
        assert node.state[PREPARATION_STATE_KEY] == _preparation_envelope(
            "unavailable"
        )
        assert VALUES_STATE_KEY not in node.state
        assert is_valid_preparation_entry(node.state[PREPARATION_STATE_KEY])


# ---------------------------------------------------------------------------
# Storage boundaries: before admission vs after the shared commit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_staging_persist_failure_keeps_attempt_without_admission(
    request: pytest.FixtureRequest,
) -> None:
    """A store failure at the staged node's first durable put is a
    pre-admission failure handled like any other preparation failure: the
    attempted edit stays recorded in the working record, ends as the same
    failed node, is never admitted or published, and the durable store
    never claims an outcome it did not save."""
    (
        controller,
        chat,
        _adapter,
        store,
        first,
        target,
    ) = await _make_editable_chat(request, chat_id="node_first_staging_put")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    original_ids = set(record.nodes)
    publications = _count_accepted_publications(chat)
    store.fail_when = lambda _snapshot: True

    # The staged node's first durable put fails, and so does the
    # failed-outcome put. Automatic preparation never propagates the raw
    # OSError: the put error is caught, warned to the developer, and the
    # retained failed display settles instead.
    with pytest.warns(UserWarning, match="recorded but not sent"):
        with pytest.warns(UserWarning, match="could not save"):
            await controller.handle_edit(
                EDIT_INDEX, EDIT_CONTENT, request_id="edit-staging"
            )

    # The validated submission was recorded in the working record first
    # and finished as the same failed node.
    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )
    assert set(record.nodes) - original_ids == {failed_id}

    # Never admitted, and the visible failed row is retained: the failed
    # tail is a terminal display entry, never an open accepted exchange.
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]
    assert chat._transcript.open_exchange_id is None
    assert publications == []

    # Honest durability: nothing was saved, so nothing claims the edit
    # was sent, accepted, or terminally failed on disk.
    assert store.snapshots == []
    assert store.failed_puts >= 1


@pytest.mark.anyio
async def test_post_commit_store_failure_never_relabeled_not_sent(
    request: pytest.FixtureRequest,
) -> None:
    """A store failure after the shared transcript/tree commit keeps the
    accepted exchange: the error is a storage failure of an input that was
    already sent, never a "not sent" marker, and the thrown await
    publishes no accepted events beyond the baseline ordinary-input
    policy."""
    controller, chat, adapter, store, first, target = await _make_editable_chat(
        request, chat_id="node_first_post_commit_put"
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    original_ids = set(record.nodes)
    original_target_status = record.nodes[target].status
    publications = _count_accepted_publications(chat)
    armed: dict[str, str | None] = {"staged": None}

    def fail_once_committed(
        snapshot: ConversationRecordV1 | ConversationRecordV2,
    ) -> bool:
        staged = armed["staged"]
        if staged is None:
            if not isinstance(snapshot, ConversationRecordV2):
                return False
            new_ids = set(snapshot.nodes) - original_ids
            if len(new_ids) != 1:
                return False
            staged = armed["staged"] = new_ids.pop()
        return any(
            entry.exchange_id == staged for entry in chat._transcript.read()
        )

    # The fault fires only on the put after the accepted-input commit.
    store.fail_when = fail_once_committed
    store.fault = OSError("disk full after commit")

    with pytest.raises(OSError, match="disk full after commit"):
        await controller.handle_edit(
            EDIT_INDEX, EDIT_CONTENT, request_id="edit-post-commit"
        )

    new_ids = set(record.nodes) - original_ids
    assert len(new_ids) == 1
    staged_id = new_ids.pop()
    assert armed["staged"] == staged_id
    node = record.nodes[staged_id]
    assert record.active_leaf == staged_id
    assert node.parent_id == first

    # The input was accepted and committed: the transcript holds it as
    # the open exchange under the staged ID.
    entries = [
        entry
        for entry in chat._transcript.read()
        if entry.exchange_id == staged_id
    ]
    assert len(entries) == 1
    assert chat._transcript.open_exchange_id == staged_id
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]

    # Never relabeled: no terminal outcome, no "not sent" claim anywhere.
    assert node.status == "pending"
    assert node.error is None
    assert node.checkpoint == "candidate"
    for some_node in record.nodes.values():
        assert PREPARATION_STATE_KEY not in some_node.state
        assert not (
            some_node.error is not None
            and some_node.error.message == HISTORY_ERROR_NOT_SENT
        )
    assert not node_is_terminal_incomplete(node)
    assert not recorder.read_only
    assert recorder.read_only_reason is None

    # Baseline callback policy on the thrown post-commit await: the
    # publication (and its on_user_submit dispatch) never ran.
    assert publications == []

    # The last durable snapshot is the honest staged one: the store never
    # received the accepted outcome it failed to write.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    assert snapshot.nodes[staged_id].status == "pending"
    assert PREPARATION_STATE_KEY not in snapshot.nodes[staged_id].state
    assert store.failed_puts == 1

    # The original branch is preserved against its pre-operation
    # baseline.
    assert record.children_of(first) == [target, staged_id]
    assert record.nodes[target].status == original_target_status


# ---------------------------------------------------------------------------
# Terminal persistence and display delivery failures
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_terminal_persist_failure_retains_failed_node_honestly(
    request: pytest.FixtureRequest,
) -> None:
    """When the terminal failed outcome itself cannot be persisted, the
    failed working node is retained in the record and stays visible, the
    put error is warned to the developer and settled rather than thrown,
    and the durable store keeps only what it actually saved (never a
    terminal claim)."""
    (
        controller,
        chat,
        adapter,
        store,
        first,
        _target,
    ) = await _make_editable_chat(request, chat_id="node_first_terminal_put")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    adapter.fault = RuntimeError("model capture unavailable")

    def fail_when_terminal(
        snapshot: ConversationRecordV1 | ConversationRecordV2,
    ) -> bool:
        assert isinstance(snapshot, ConversationRecordV2)
        return any(
            node_is_terminal_incomplete(node)
            for node in snapshot.nodes.values()
        )

    store.fail_when = fail_when_terminal

    # The terminal put fails after the staging put succeeded: the raw
    # OSError is caught and warned, and the retained failed display
    # settles without throwing for this automatic preparation failure.
    with pytest.warns(UserWarning, match="recorded but not sent"):
        with pytest.warns(UserWarning, match="could not save"):
            await controller.handle_edit(
                EDIT_INDEX, EDIT_CONTENT, request_id="edit-terminal-put"
            )

    # The failed working node is fully retained in memory.
    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )

    # The durable store only ever received the staged (pending) snapshot:
    # it honestly claims neither acceptance nor a terminal outcome.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    staged_snapshot = snapshot.nodes[failed_id]
    assert staged_snapshot.status == "pending"
    assert staged_snapshot.checkpoint == "candidate"
    assert PREPARATION_STATE_KEY not in staged_snapshot.state
    assert store.failed_puts == 1

    # No accepted input was published for the unsent attempt, and the
    # visible failed row is retained as a terminal display entry.
    assert publications == []
    assert chat._transcript.open_exchange_id is None
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]


@pytest.mark.anyio
async def test_persist_failure_notifies_user_edit_not_saved(
    request: pytest.FixtureRequest,
) -> None:
    """A retained failed edit whose outcome could not reach storage gets
    one sanitized user-facing notification: honest "not sent / could not
    be saved" wording, never the raw storage fault."""
    (
        controller,
        chat,
        _adapter,
        store,
        first,
        _target,
    ) = await _make_editable_chat(
        request, chat_id="node_first_not_saved_notification"
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    store.fail_when = lambda _snapshot: True

    with patch("shiny.ui.notification_show") as notify_spy:
        with pytest.warns(UserWarning, match="recorded but not sent"):
            with pytest.warns(UserWarning, match="could not save"):
                await controller.handle_edit(
                    EDIT_INDEX, EDIT_CONTENT, request_id="edit-notify"
                )

        # Exactly one sanitized user notification: the developer keeps the
        # raw cause in the warning, the person keeps honest wording.
        notify_spy.assert_called_once()
        user_message = str(notify_spy.call_args.args[0])
        assert "not sent" in user_message
        assert "saved" in user_message
        assert "disk full" not in user_message

        # The retained failed working node and honest no-saved store are
        # the same policy as the persistence-failure test.
        failed_id = _assert_failed_node(
            controller, parent_id=first, app_values="complete"
        )
        assert record.nodes[failed_id].input is not None
        assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]
        assert store.snapshots == []


@pytest.mark.anyio
async def test_display_delivery_failure_retains_persisted_failed_node(
    request: pytest.FixtureRequest,
) -> None:
    """A display delivery failure after the terminal outcome was persisted
    cannot undo or relabel the failed working node: the record and the
    durable store keep it, and the failure surfaces to the caller."""
    (
        controller,
        chat,
        adapter,
        store,
        first,
        _target,
    ) = await _make_editable_chat(
        request, chat_id="node_first_display_delivery"
    )
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    adapter.fault = RuntimeError("model capture unavailable")

    # The display transport fails from the first delivery after the
    # poisoned capture fired (the pending-row projection was already
    # delivered before preparation started).
    delivery = {"armed": False}
    original_send = chat._send_action

    async def failing_send_action(
        action: Any, *args: Any, **kwargs: Any
    ) -> None:
        if delivery["armed"]:
            raise RuntimeError("display delivery failed")
        if adapter.consumed_fault:
            delivery["armed"] = True
        await original_send(action, *args, **kwargs)

    chat._send_action = failing_send_action  # type: ignore[method-assign]

    with pytest.warns(UserWarning, match="recorded but not sent"):
        with pytest.raises(RuntimeError, match="display delivery failed"):
            await controller.handle_edit(
                EDIT_INDEX, EDIT_CONTENT, request_id="edit-display"
            )

    # The failed working node is retained, selected, and unchanged by the
    # delivery failure.
    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )

    # The terminal outcome was already durable, so a reload keeps the
    # failed node: an honest saved guarantee, unlike the persistence
    # failure case.
    snapshot = store.last_snapshot
    assert isinstance(snapshot, ConversationRecordV2)
    failed_snapshot = snapshot.nodes[failed_id]
    assert failed_snapshot.status == "error"
    assert failed_snapshot.state[PREPARATION_STATE_KEY] == (
        _preparation_envelope("complete")
    )

    # Nothing was accepted and the failed row was retained in the
    # transcript before the delivery failed.
    assert publications == []
    assert chat._transcript.open_exchange_id is None
    assert _messages(chat) == [*PREFIX_CONTENTS, EDIT_CONTENT]


# ---------------------------------------------------------------------------
# Exactly-once admission of one staged submission
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_duplicate_staged_admission_rejected_before_second_commit(
    request: pytest.FixtureRequest,
) -> None:
    """One staged submission is admitted exactly once: both a replayed
    capability and a fresh capability for the consumed staged ID are
    rejected before any second capture, commit, or accepted signal, and
    the recorder independently rejects the recorded node ID."""
    (
        controller,
        chat,
        _adapter,
        _store,
        first,
        _target,
    ) = await _make_editable_chat(request, chat_id="node_first_duplicate")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    observer_calls: list[str] = []
    original_observer = recorder.accepted_input

    async def counting_observer(
        exchange_id: str, message: StoredMessage, commit: Callable[[], None]
    ) -> None:
        observer_calls.append(exchange_id)
        await original_observer(exchange_id, message, commit)

    chat._transcript.set_capture_callbacks(
        on_accepted_input=counting_observer,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )

    staged_id = "staged-duplicate"
    async with controller._exchange_mutation():
        recorder.stage_input_locked(
            staged_id, first, _stored_message("user", "dup input")
        )
    assert record.active_leaf == staged_id

    token = StagedInputAdmission(staged_id)
    async with chat._destructive_history_mutation(block_input=True) as txn:
        await chat._record_accepted_user_input_with_capture(
            ChatMessage(content="dup input", role="user"),
            staged_admission=token,
            transaction=txn,
        )

    # One normal admission: one commit, one accepted signal.
    assert observer_calls == [staged_id]
    assert [str(p.content) for p in publications] == ["dup input"]
    committed = [
        entry
        for entry in chat._transcript.read()
        if entry.exchange_id == staged_id
    ]
    assert len(committed) == 1
    assert chat._transcript.open_exchange_id == staged_id
    assert token.committed is True

    message = ChatMessage(content="dup input again", role="user")

    # A replayed capability is rejected before any second work.
    async with chat._destructive_history_mutation(block_input=True) as txn:
        with pytest.raises(RuntimeError, match="was already admitted"):
            await chat._record_accepted_user_input_with_capture(
                message, staged_admission=token, transaction=txn
            )

    # A fresh capability for the consumed staged ID is rejected too.
    async with chat._destructive_history_mutation(block_input=True) as txn:
        with pytest.raises(RuntimeError, match="was already admitted"):
            await chat._record_accepted_user_input_with_capture(
                message,
                staged_admission=StagedInputAdmission(staged_id),
                transaction=txn,
            )

    # The recorder layer rejects the recorded node ID before capture or
    # commit as well.
    with pytest.raises(RuntimeError, match="was already admitted"):
        await recorder.accepted_input(
            staged_id, _stored_message("user", "x"), lambda: None
        )

    # No second commit, callback, or accepted signal happened.
    assert observer_calls == [staged_id]
    committed = [
        entry
        for entry in chat._transcript.read()
        if entry.exchange_id == staged_id
    ]
    assert len(committed) == 1
    assert [str(p.content) for p in publications] == ["dup input"]
    node = record.nodes[staged_id]
    assert node.status == "pending"
    assert PREPARATION_STATE_KEY not in node.state


# ---------------------------------------------------------------------------
# Per-admission committed classification with one reused fault instance
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reused_fault_instance_keeps_per_admission_classification(
    request: pytest.FixtureRequest,
) -> None:
    """The committed classification is per admission call, not per
    exception: the very same fault instance raised after one admission's
    commit (a storage failure of an accepted input) and again before
    another admission's commit (a model capture failure) must classify
    each call independently."""
    (
        controller,
        chat,
        adapter,
        store,
        first,
        _target,
    ) = await _make_editable_chat(request, chat_id="node_first_reused_fault")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    shared_fault = RuntimeError("reused storage fault")
    armed: dict[str, str | None] = {"staged": None}

    def fail_once_committed(
        snapshot: ConversationRecordV1 | ConversationRecordV2,
    ) -> bool:
        staged = armed["staged"]
        if staged is None:
            if not isinstance(snapshot, ConversationRecordV2):
                return False
            if snapshot.active_leaf not in (
                "staged-reused-1",
                "staged-reused-2",
            ):
                return False
            staged = armed["staged"] = snapshot.active_leaf
        return any(
            entry.exchange_id == staged for entry in chat._transcript.read()
        )

    store.fail_when = fail_once_committed
    store.fault = shared_fault

    first_id = "staged-reused-1"
    async with controller._exchange_mutation():
        recorder.stage_input_locked(
            first_id, first, _stored_message("user", "first attempt")
        )
    token_one = StagedInputAdmission(first_id)
    async with chat._destructive_history_mutation(block_input=True) as txn:
        with pytest.raises(
            RuntimeError, match="reused storage fault"
        ) as caught_one:
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="first attempt", role="user"),
                staged_admission=token_one,
                transaction=txn,
            )

    # The first failure happened after the shared commit: the very fault
    # instance was raised by the store, and the input stays accepted.
    assert caught_one.value is shared_fault
    assert token_one.committed is True
    assert chat._transcript.open_exchange_id == first_id
    first_node = record.nodes[first_id]
    assert first_node.status == "pending"
    assert PREPARATION_STATE_KEY not in first_node.state
    assert publications == []

    # Disarm the one-shot store fault: the next staging persist must
    # succeed so the second admission reaches its own capture.
    store.fail_when = None
    store.fault = None

    # The same fault instance now poisons the model capture of a second
    # submission, before its commit.
    adapter.fault = shared_fault
    second_id = "staged-reused-2"
    async with controller._exchange_mutation():
        recorder.stage_input_locked(
            second_id, first, _stored_message("user", "second attempt")
        )
    token_two = StagedInputAdmission(second_id)
    async with chat._destructive_history_mutation(block_input=True) as txn:
        with pytest.raises(_ModelCaptureError) as caught_two:
            await chat._record_accepted_user_input_with_capture(
                ChatMessage(content="second attempt", role="user"),
                staged_admission=token_two,
                transaction=txn,
            )

    # The pre-commit failure raised the same reused instance (as the
    # wrapped capture cause) and must classify as not committed: the
    # per-call outcome did not carry over from the committed call.
    assert caught_two.value.__cause__ is shared_fault
    assert token_two.committed is False
    assert all(
        entry.exchange_id != second_id for entry in chat._transcript.read()
    )
    assert chat._transcript.open_exchange_id == first_id
    second_node = record.nodes[second_id]
    assert second_node.status == "pending"
    assert PREPARATION_STATE_KEY not in second_node.state
    assert token_one.committed is True
    assert publications == []


# ---------------------------------------------------------------------------
# Failed-node marker never bypasses the existing protections
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_failed_node_marker_does_not_bypass_protections(
    request: pytest.FixtureRequest,
) -> None:
    """Source isolation, live producers, and model-unavailable
    restrictions are not bypassed by a terminal incomplete marker: the
    read-only resubmit guard refuses, the client is not offered
    resubmission, and only the restrictions an explicit resubmit can
    revalidate advertise it. A pending producer or a bare invalid
    checkpoint is never classified as a stopped producer."""
    (
        controller,
        chat,
        adapter,
        _store,
        first,
        _target,
    ) = await _make_editable_chat(request, chat_id="node_first_protections")
    recorder = controller._exchange_recorder
    assert recorder is not None
    record = recorder.record
    assert record is not None
    publications = _count_accepted_publications(chat)
    sent = _spy_send_actions(chat)
    adapter.fault = RuntimeError("model capture unavailable")

    with pytest.warns(UserWarning, match="recorded but not sent"):
        await controller.handle_edit(
            EDIT_INDEX, EDIT_CONTENT, request_id="edit-protections"
        )
    failed_id = _assert_failed_node(
        controller, parent_id=first, app_values="complete"
    )
    assert publications == []

    def last_history_update() -> dict[str, Any]:
        updates = [
            action for action in sent if action["type"] == "history_update"
        ]
        assert updates
        return updates[-1]

    # Restricted loaded states whose protections must hold even though
    # the selected leaf carries the terminal incomplete marker.
    for reason, isolated in (
        ("interrupted", True),
        ("model_unavailable", False),
    ):
        record.set_active_leaf(failed_id)
        recorder.install_restored_record(
            record,
            read_only=True,
            source_isolated=isolated,
            read_only_reason=reason,  # type: ignore[arg-type]
        )
        await controller.send_history_update()
        assert controller._can_resubmit_active() is False
        assert "active_can_resubmit" not in last_history_update()
        node_count = len(record.nodes)
        with pytest.raises(RuntimeError, match="read-only conversation"):
            await controller.resubmit(
                failed_id,
                kind="retry",
                request_id=f"retry-{reason}",
                message_index=EDIT_INDEX,
            )
        assert len(record.nodes) == node_count
        assert recorder._staged_input is None

    # The restriction an explicit resubmit may revalidate is the only
    # one advertised, because the failed node's valid parent can be
    # restored without close-capturing poisoned state.
    record.set_active_leaf(failed_id)
    recorder.install_restored_record(
        record,
        read_only=True,
        source_isolated=False,
        read_only_reason="terminal_incomplete",
    )
    await controller.send_history_update()
    assert controller._can_resubmit_active() is True
    assert last_history_update()["active_can_resubmit"] is True

    # A genuinely pending staged producer is not a browsable terminal
    # position, and source isolation still refuses to resubmit it.
    pending_id = "staged-live-producer"
    async with controller._exchange_mutation():
        recorder.stage_input_locked(
            pending_id, first, _stored_message("user", "still producing")
        )
    assert not node_is_terminal_incomplete(record.nodes[pending_id])
    assert record.checkpoint_leaf(pending_id) is None
    assert controller._can_resubmit_active() is False
    recorder.install_restored_record(
        record,
        read_only=True,
        source_isolated=True,
        read_only_reason="interrupted",
    )
    await controller.send_history_update()
    assert controller._can_resubmit_active() is False
    assert "active_can_resubmit" not in last_history_update()
    with pytest.raises(RuntimeError, match="read-only conversation"):
        await controller.resubmit(
            pending_id,
            kind="retry",
            request_id="retry-live",
            message_index=EDIT_INDEX,
        )

    # Classification guards: neither a bare terminal status, a bare
    # invalid checkpoint, a missing envelope, nor a malformed envelope
    # makes a node a known stopped producer.
    legacy = record.nodes[failed_id].model_copy(deep=True)
    assert node_is_terminal_incomplete(legacy)
    del legacy.state[PREPARATION_STATE_KEY]
    assert not node_is_terminal_incomplete(legacy)
    malformed = record.nodes[failed_id].model_copy(deep=True)
    malformed.state[PREPARATION_STATE_KEY] = StateEntry(
        kind=PREPARATION_ENTRY_KIND,
        version=PREPARATION_ENTRY_VERSION,
        mode="snapshot",
        # An "accepted" preparation outcome is not a failed submission.
        data={"terminal": True, "accepted": True, "app_values": "complete"},
    )
    assert not is_valid_preparation_entry(
        malformed.state[PREPARATION_STATE_KEY]
    )
    assert not node_is_terminal_incomplete(malformed)
    pending_invalid = record.nodes[pending_id].model_copy(deep=True)
    pending_invalid.checkpoint = "invalid"
    assert not node_is_terminal_incomplete(pending_invalid)
