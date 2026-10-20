"""System-prompt capture, restore, and rewind through production history paths."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from _history_test_helpers import replay_exchange_record
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._history_client import TurnsAdapter
from shinychat._history_controller import HistoryController
from shinychat._history_store import (
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_controller import _FakeChat, _sent, _stored_message, part


class _PromptClient:
    """Turn-level client with a chatlas-style `system_prompt` property.

    `set_turns()` rejects system turns like chatlas, so replaying a system
    turn into the client fails loudly. Setter calls are recorded in
    `calls` for restore-order and no-touch assertions.
    """

    def __init__(self, system_prompt: str | None = None) -> None:
        self._system_prompt = system_prompt
        self.turns: list[dict[str, Any]] = []
        self.calls: list[tuple[str, Any]] = []

    @property
    def system_prompt(self) -> str | None:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str | None) -> None:
        self._system_prompt = value
        self.calls.append(("prompt", value))

    def get_turns(self) -> list[dict[str, Any]]:
        return list(self.turns)

    def set_turns(self, turns: list[dict[str, Any]]) -> None:
        for turn in turns:
            if isinstance(turn, dict) and turn.get("role") == "system":
                raise ValueError("set_turns() does not accept system turns.")
        self.turns = [dict(turn) for turn in turns]
        self.calls.append(("turns", len(turns)))

    def prompt_calls(self) -> list[Any]:
        return [value for name, value in self.calls if name == "prompt"]

    def turns_calls(self) -> list[int]:
        return [value for name, value in self.calls if name == "turns"]


class _PlainClient:
    """A generic `ClientWithTurns` with no `system_prompt` property."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    def get_turns(self) -> list[dict[str, Any]]:
        return list(self.turns)

    def set_turns(self, turns: list[dict[str, Any]]) -> None:
        self.turns = [dict(turn) for turn in turns]


def _make_prompt_controller(
    *,
    store: ConversationStore | None = None,
    prompt: str | None = None,
    client: Any | None = None,
) -> tuple[HistoryController, Any]:
    """A controller on the real `TurnsAdapter` over a prompt-capable client."""
    resolved_client = client if client is not None else _PromptClient(prompt)
    controller = HistoryController(
        chat=_FakeChat(),  # type: ignore[arg-type]
        adapter=TurnsAdapter(resolved_client),
        store=store if store is not None else InMemoryConversationStore(),
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = part()
    return controller, resolved_client


def _make_transcript(recorder: Any) -> ChatTranscript:
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )


async def _drive_exchange(
    transcript: ChatTranscript,
    client: Any,
    user: str,
    assistant: str,
    *,
    stream_id: str,
    prompt_during: str | None = None,
) -> str:
    """One full exchange: an accepted input plus a streamed reply.

    `prompt_during` changes the client's prompt mid-stream, so this
    exchange's own stream-finish capture records the change.
    """
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", user)
    )
    client.turns.append({"role": "user", "content": user})
    await transcript.start_stream(
        stream_id=stream_id,
        entry=TranscriptEntry(message=_stored_message("assistant", assistant)),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    if prompt_during is not None:
        client.system_prompt = prompt_during
    client.turns.append({"role": "assistant", "content": assistant})
    await transcript.end_stream(
        stream_id=stream_id,
        status=None,
        error=None,
        send=_sent,
    )
    return exchange_id


def _prompt_entry(record: Any, node_id: str) -> StateEntry | None:
    return record.nodes[node_id].state.get(SYSTEM_PROMPT_STATE_KEY)


def _prompt_data(record: Any, node_id: str) -> Any:
    return record.nodes[node_id].state[SYSTEM_PROMPT_STATE_KEY].data


def _null_prompt_entry() -> StateEntry:
    """A valid prompt entry that inherits the previous recorded value."""
    return StateEntry(
        kind="system_prompt", version=1, mode="snapshot", data=None
    )


def _user_turn(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def _assistant_turn(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_system_prompt_captured_at_root_and_not_while_unchanged():
    controller, client = _make_prompt_controller(prompt="be precise")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)

    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )

    record = recorder.record
    assert record is not None
    root_entry = _prompt_entry(record, record.root_id)
    assert root_entry is not None
    assert root_entry.kind == "system_prompt"
    assert root_entry.version == 1
    assert root_entry.mode == "snapshot"
    assert root_entry.data == "be precise"
    # Unchanged descendants record nothing: the latest entry on the path
    # (here the root's) already covers them.
    assert _prompt_entry(record, first) is None
    assert _prompt_entry(record, second) is None
    # The prompt entry's hooks register before the turns hooks, so restore
    # applies the prompt before replaying turns.
    assert list(recorder.restore_hooks) == [
        SYSTEM_PROMPT_STATE_KEY,
        TURNS_STATE_KEY,
    ]
    assert list(recorder.rewind_hooks) == [
        SYSTEM_PROMPT_STATE_KEY,
        TURNS_STATE_KEY,
    ]
    # Captured turns never carry the prompt as a system turn.
    for node in record.nodes.values():
        turns_entry = node.state.get(TURNS_STATE_KEY)
        assert turns_entry is not None
        assert isinstance(turns_entry.data, list)
        assert all(
            isinstance(turn, dict) and turn.get("role") != "system"
            for turn in turns_entry.data
        )


@pytest.mark.anyio
async def test_system_prompt_records_path_changes_with_turn_deltas():
    """A -> B -> A records each change; unchanged nodes record nothing."""
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)

    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    client.system_prompt = "B"
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    client.system_prompt = "A"
    third = await _drive_exchange(
        transcript, client, "three", "answer three", stream_id="s3"
    )
    fourth = await _drive_exchange(
        transcript, client, "four", "answer four", stream_id="s4"
    )

    record = recorder.record
    assert record is not None
    # A prompt change is recorded on the node that closes while the new
    # value is live (here: the previous leaf, at the next input's
    # node-close). The nearest ancestor entry — not the root — is the
    # comparison point, so returning to A after B is a real change.
    assert _prompt_data(record, record.root_id) == "A"
    assert _prompt_data(record, first) == "B"
    assert _prompt_data(record, second) == "A"
    assert _prompt_entry(record, third) is None
    assert _prompt_entry(record, fourth) is None
    # Prompt-only changes never force a turns snapshot: each exchange's
    # turns stay a small delta extending the root's snapshot.
    root_turns = record.nodes[record.root_id].state[TURNS_STATE_KEY]
    assert root_turns.mode == "snapshot"
    for node_id, new_turns in [
        (first, [_user_turn("one"), _assistant_turn("answer one")]),
        (second, [_user_turn("two"), _assistant_turn("answer two")]),
        (third, [_user_turn("three"), _assistant_turn("answer three")]),
        (fourth, [_user_turn("four"), _assistant_turn("answer four")]),
    ]:
        entry = record.nodes[node_id].state[TURNS_STATE_KEY]
        assert entry.mode == "delta"
        assert entry.data == new_turns


@pytest.mark.anyio
@pytest.mark.parametrize("prompt", [None, ""], ids=["none", "empty-string"])
async def test_system_prompt_capture_and_restore_none_and_empty(
    prompt: str | None,
):
    """Raw None and "" both record as "" — the explicit clear value.

    Null/empty are no longer raw-value round trips: they are the same
    logical clear. Restoring a saved "" applies None (chatlas None
    removes the system turn; assigning "" would record a "[empty
    string]" turn), so the sentinel live prompt ends up cleared to None.
    """
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt=prompt)
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)

    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    await controller.on_response()

    record = recorder.record
    assert record is not None
    entry = _prompt_entry(record, record.root_id)
    assert entry is not None
    assert entry.mode == "snapshot"
    assert entry.data == ""

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(
        store=store, prompt="sentinel"
    )
    await replay_exchange_record(restored, stored)

    assert restored_client.system_prompt is None
    assert restored_client.prompt_calls() == [None]
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
    ]


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_system_prompt_restore_applies_prompt_before_turns():
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(
        store=store, prompt="be precise"
    )
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(store=store)
    await replay_exchange_record(restored, stored)

    # The prompt setter ran before the turns setter, and the strict
    # client's set_turns accepted the replayed turns (no system turn).
    call_names = [name for name, _ in restored_client.calls]
    assert "prompt" in call_names and "turns" in call_names
    assert call_names.index("prompt") < call_names.index("turns")
    assert restored_client.system_prompt == "be precise"
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
        _user_turn("two"),
        _assistant_turn("answer two"),
    ]


@pytest.mark.anyio
async def test_system_prompt_restore_uses_latest_entry_on_the_path():
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    client.system_prompt = "B"
    await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(store=store)
    await replay_exchange_record(restored, stored)

    # The leaf-side change wins over the root's earlier value.
    assert restored_client.system_prompt == "B"


@pytest.mark.anyio
async def test_system_prompt_restore_null_entry_falls_through_to_ancestor():
    """A saved null entry is inheritable absence, not a recorded clear.

    Restoring a path that carries a foreign null entry skips it and falls
    through to the earlier non-null prompt instead of clearing.
    """
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None
    assert _prompt_data(record, record.root_id) == "A"
    assert _prompt_entry(record, first) is None

    # A foreign null entry between the root's "A" and the leaf.
    record.nodes[first].state[SYSTEM_PROMPT_STATE_KEY] = _null_prompt_entry()

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(prompt="sentinel")
    await replay_exchange_record(restored, record)

    assert restored_client.system_prompt == "A"
    assert restored_client.prompt_calls() == ["A"]
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
        _user_turn("two"),
        _assistant_turn("answer two"),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "absence",
    ["root-null", "all-null", "missing-entry"],
)
async def test_system_prompt_restore_without_effective_value_is_noop(
    absence: str,
):
    """With no effective prompt on the path (only null entries, or none
    at all), restore leaves the live prompt entirely untouched."""
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    if absence == "root-null":
        record.nodes[record.root_id].state[SYSTEM_PROMPT_STATE_KEY] = (
            _null_prompt_entry()
        )
    elif absence == "all-null":
        record.nodes[record.root_id].state[SYSTEM_PROMPT_STATE_KEY] = (
            _null_prompt_entry()
        )
        record.nodes[first].state[SYSTEM_PROMPT_STATE_KEY] = (
            _null_prompt_entry()
        )
    else:
        del record.nodes[record.root_id].state[SYSTEM_PROMPT_STATE_KEY]
        assert _prompt_entry(record, first) is None

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(prompt="sentinel")
    await replay_exchange_record(restored, record)

    # The restore ran (turns replayed) but never touched the prompt.
    assert restored_client.system_prompt == "sentinel"
    assert restored_client.prompt_calls() == []
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("clear", ["", None], ids=["empty-string", "raw-none"])
async def test_system_prompt_recorded_clear_stops_inheritance(
    clear: str | None,
):
    """A recorded "" on the path blocks fall-through to the root's
    earlier prompt: restoring the leaf applies the clear as None.

    Both raw "" and raw None record the same explicit clear value "".
    """
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    client.system_prompt = clear
    await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.on_response()

    record = recorder.record
    assert record is not None
    assert _prompt_data(record, record.root_id) == "A"
    assert _prompt_data(record, first) == ""

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(
        store=store, prompt="sentinel"
    )
    await replay_exchange_record(restored, stored)

    assert restored_client.system_prompt is None
    assert restored_client.prompt_calls() == [None]
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
        _user_turn("two"),
        _assistant_turn("answer two"),
    ]


@pytest.mark.anyio
async def test_system_prompt_switch_away_and_back_restores_each_prompt():
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="first")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    assert recorder.record is not None
    first_id = recorder.record.id

    await controller.new_chat()
    client.system_prompt = "second"
    await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    assert recorder.record is not None
    second_id = recorder.record.id
    assert second_id != first_id

    await controller.switch_to(first_id)
    assert client.system_prompt == "first"
    assert client.turns == [_user_turn("one"), _assistant_turn("answer one")]

    await controller.switch_to(second_id)
    assert client.system_prompt == "second"
    assert client.turns == [_user_turn("two"), _assistant_turn("answer two")]

    await controller.switch_to(first_id)
    assert client.system_prompt == "first"


# ---------------------------------------------------------------------------
# Edit / regenerate / navigation (rewind hooks + preflight source path)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "regenerate"])
async def test_system_prompt_edit_and_regenerate_succeed(kind: str):
    """Same-prompt rewinds never touch the live prompt or feed it back
    as a turn; the strict client's set_turns accepts every replay."""
    controller, client = _make_prompt_controller(prompt="be precise")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    record = recorder.record
    assert record is not None

    client.calls.clear()
    replacement = (
        _stored_message("user", "two edited") if kind == "edit" else None
    )
    await controller.resubmit(
        second, replacement, kind=kind, request_id=f"r-{kind}", message_index=2
    )

    # Recorded source and target prompts are equal ("be precise"), so the
    # rewind leaves the client's prompt entirely alone.
    assert client.prompt_calls() == []
    assert client.system_prompt == "be precise"
    # Turns rewound to the parent prefix: root snapshot + first exchange.
    assert client.turns == [_user_turn("one"), _assistant_turn("answer one")]
    assert record.active_leaf == first

    submitted = "two edited" if kind == "edit" else "two"
    sibling = await transcript.record_accepted_input_and_notify(
        _stored_message("user", submitted)
    )
    assert record.nodes[sibling].parent_id == first
    assert record.children_of(first) == [second, sibling]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("target", "expected"),
    [(None, None), ("", None), ("A", "A")],
    ids=["none", "empty-string", "text"],
)
async def test_system_prompt_edit_across_recorded_change_applies_target(
    target: str | None,
    expected: str | None,
):
    """A recorded empty value clears while a nonempty target applies its text."""
    controller, client = _make_prompt_controller(prompt=target)
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript,
        client,
        "two",
        "answer two",
        stream_id="s2",
        prompt_during="B",
    )
    record = recorder.record
    assert record is not None
    assert _prompt_entry(record, first) is None
    assert _prompt_data(record, second) == "B"

    await controller.resubmit(
        second,
        _stored_message("user", "two edited"),
        kind="edit",
        request_id="r-edit",
        message_index=2,
    )

    assert client.system_prompt == expected
    assert client.prompt_calls()[-1] == expected


@pytest.mark.anyio
async def test_system_prompt_navigation_applies_sibling_prompts():
    """Sibling branches keep independent recorded prompts; navigating
    across a recorded change applies the target branch's value."""
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "first", "answer first", stream_id="s1"
    )
    original = await _drive_exchange(
        transcript,
        client,
        "original",
        "reply original",
        stream_id="s2",
        prompt_during="B",
    )

    # Branch a sibling under the first exchange via a production edit.
    # Rewinding across the recorded change (B -> A) applies the target.
    await controller.resubmit(
        original,
        _stored_message("user", "replacement"),
        kind="edit",
        request_id="r-edit",
        message_index=2,
    )
    assert client.system_prompt == "A"
    replacement = await _drive_exchange(
        transcript,
        client,
        "replacement",
        "reply replacement",
        stream_id="s3",
        prompt_during="C",
    )

    record = recorder.record
    assert record is not None
    assert _prompt_data(record, original) == "B"
    assert _prompt_data(record, replacement) == "C"

    # Navigate to the original branch: the recorded B applies.
    await controller.handle_navigate(2, "prev", request_id="nav-prev")
    assert client.system_prompt == "B"
    chat = controller.chat
    assert isinstance(chat, _FakeChat)
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == ["first", "answer first", "original", "reply original"]
    # Sibling independence: each branch's captures never touched the
    # other branch's nodes.
    assert _prompt_data(record, original) == "B"
    assert _prompt_data(record, replacement) == "C"

    # Navigate back: the replacement branch's recorded C applies.
    await controller.handle_navigate(2, "next", request_id="nav-next")
    assert client.system_prompt == "C"
    assert _prompt_data(record, original) == "B"
    assert _prompt_data(record, replacement) == "C"


# ---------------------------------------------------------------------------
# Live `on_restore` overrides
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_system_prompt_on_restore_override_survives_edit():
    """The documented recipe (`on_restore` sets today's prompt) wins over
    the recorded prompt on restore, and an equal-prompt edit never resets
    it — the rewind compares preflight snapshots taken before the
    node-close capture records the live override."""
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="P")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    restored, restored_client = _make_prompt_controller(store=store)

    def apply_current_prompt(_values: dict[str, Any]) -> None:
        restored_client.system_prompt = "OVERRIDE"

    restored._restore_callbacks.append(apply_current_prompt)
    await replay_exchange_record(restored, stored)

    # State entries apply first, then on_restore: the override wins.
    assert restored_client.prompt_calls() == ["P", "OVERRIDE"]

    restored_recorder = restored._exchange_recorder
    restored_transcript = _make_transcript(restored_recorder)
    restored_record = restored_recorder.record
    assert restored_record is not None
    restored_client.calls.clear()
    await restored.resubmit(
        second,
        _stored_message("user", "two edited"),
        kind="edit",
        request_id="r-edit",
        message_index=2,
    )

    # Equal recorded prompts (source == target == P): the live override is
    # not a reason to reset the prompt during this edit.
    assert restored_client.prompt_calls() == []
    assert restored_client.system_prompt == "OVERRIDE"
    # The node-close capture still recorded the override faithfully on the
    # abandoned leaf...
    assert _prompt_data(restored_record, second) == "OVERRIDE"
    # ...and the next capture on the shared parent records it too.
    first = restored_record.nodes[second].parent_id
    assert first is not None
    await restored_transcript.record_accepted_input_and_notify(
        _stored_message("user", "two edited")
    )
    assert _prompt_data(restored_record, first) == "OVERRIDE"


@pytest.mark.anyio
async def test_system_prompt_on_restore_override_survives_navigation():
    store = InMemoryConversationStore()
    controller, client = _make_prompt_controller(store=store, prompt="P")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "first", "answer first", stream_id="s1"
    )
    original = await _drive_exchange(
        transcript, client, "original", "reply original", stream_id="s2"
    )
    # One prompt everywhere: an equal-prompt navigation must not reset a
    # live override.
    await controller.resubmit(
        original,
        _stored_message("user", "replacement"),
        kind="edit",
        request_id="r-edit",
        message_index=2,
    )
    replacement = await _drive_exchange(
        transcript,
        client,
        "replacement",
        "reply replacement",
        stream_id="s3",
    )
    record = recorder.record
    assert record is not None
    assert _prompt_entry(record, replacement) is None

    client.system_prompt = "OVERRIDE"
    client.calls.clear()
    await controller.handle_navigate(2, "prev", request_id="nav-prev")

    assert client.prompt_calls() == []
    assert client.system_prompt == "OVERRIDE"
    # The node-close capture during navigation recorded the live override
    # on the abandoned leaf; the preflight snapshot kept that capture from
    # becoming a reason to reset the prompt in the same navigation.
    assert _prompt_data(record, replacement) == "OVERRIDE"


# ---------------------------------------------------------------------------
# Offline real chatlas client
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_system_prompt_real_chatlas_restore_and_regenerate():
    """chatlas.ChatOpenAI offline: restore and regenerate round-trip with
    a system prompt, never feeding a system turn back to set_turns()."""
    import chatlas

    client = chatlas.ChatOpenAI(system_prompt="be precise", api_key="test")
    adapter = TurnsAdapter(client)
    # The adapter omits the prompt from turns unless explicitly asked.
    assert adapter.get_turns_json() == []
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="seed"),
            chatlas.Turn(role="assistant", contents="seed reply"),
        ]
    )
    assert [t.get("role") for t in adapter.get_turns_json()] == [
        "user",
        "assistant",
    ]
    assert [
        t.get("role")
        for t in adapter.get_turns_json(include_system_prompt=True)
    ] == ["system", "user", "assistant"]

    store = InMemoryConversationStore()
    controller, _ = _make_prompt_controller(store=store, client=client)
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)

    first = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    await transcript.start_stream(
        stream_id="s1",
        entry=TranscriptEntry(
            message=_stored_message("assistant", "answer one")
        ),
        owner_task=None,
        exchange_id=first,
        send=_sent,
    )
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="one"),
            chatlas.Turn(role="assistant", contents="answer one"),
        ]
    )
    await transcript.end_stream(
        stream_id="s1", status=None, error=None, send=_sent
    )
    second = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    await transcript.start_stream(
        stream_id="s2",
        entry=TranscriptEntry(
            message=_stored_message("assistant", "answer two")
        ),
        owner_task=None,
        exchange_id=second,
        send=_sent,
    )
    client.set_turns(
        [
            chatlas.Turn(role="user", contents="one"),
            chatlas.Turn(role="assistant", contents="answer one"),
            chatlas.Turn(role="user", contents="two"),
            chatlas.Turn(role="assistant", contents="answer two"),
        ]
    )
    await transcript.end_stream(
        stream_id="s2", status=None, error=None, send=_sent
    )
    await controller.on_response()

    record = recorder.record
    assert record is not None
    root_entry = _prompt_entry(record, record.root_id)
    assert root_entry is not None and root_entry.data == "be precise"
    root_turns = record.nodes[record.root_id].state[TURNS_STATE_KEY]
    assert root_turns.kind == "chatlas"
    # No captured turn anywhere is the system prompt.
    assert '"role":"system"' not in record.model_dump_json()

    restored_client = chatlas.ChatOpenAI(api_key="test")
    assert restored_client.system_prompt is None
    restored, _ = _make_prompt_controller(store=store, client=restored_client)
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    await replay_exchange_record(restored, stored)

    assert restored_client.system_prompt == "be precise"
    assert [t.role for t in restored_client.get_turns()] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    # Regenerate round-trip on the restored conversation.
    restored_record = restored._exchange_recorder.record
    assert restored_record is not None
    await restored.resubmit(
        second, kind="regenerate", request_id="r-regen", message_index=2
    )
    assert restored_client.system_prompt == "be precise"
    assert [t.role for t in restored_client.get_turns()] == [
        "user",
        "assistant",
    ]
    restored_transcript = _make_transcript(restored._exchange_recorder)
    sibling = await restored_transcript.record_accepted_input_and_notify(
        _stored_message("user", "two")
    )
    assert restored_record.nodes[sibling].parent_id == first


# ---------------------------------------------------------------------------
# Generic clients without a system prompt
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_system_prompt_generic_client_without_prompt_unchanged():
    client = _PlainClient()
    controller, _ = _make_prompt_controller(client=client)
    adapter = controller.adapter
    assert isinstance(adapter, TurnsAdapter)
    assert not adapter.has_system_prompt()
    # Generic get_turns() is used verbatim, whatever it returns.
    client.turns = [_user_turn("seed")]
    assert adapter.get_turns_json() == [_user_turn("seed")]
    assert adapter.get_turns_json(include_system_prompt=True) == [
        _user_turn("seed")
    ]
    client.turns = []

    recorder = controller._exchange_recorder
    assert SYSTEM_PROMPT_STATE_KEY not in recorder.restore_hooks
    assert SYSTEM_PROMPT_STATE_KEY not in recorder.rewind_hooks

    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    record = recorder.record
    assert record is not None
    # State stays exactly the turns entry; no prompt key appears.
    for node in record.nodes.values():
        assert set(node.state) == {TURNS_STATE_KEY}

    restored, restored_client = _make_prompt_controller(client=_PlainClient())
    await replay_exchange_record(restored, record)
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
    ]


# ---------------------------------------------------------------------------
# File-store round trip (explicit clears are stored as empty strings)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("prompt", "saved", "expected"),
    [
        (None, "", None),
        ("", "", None),
        ("be precise", "be precise", "be precise"),
    ],
    ids=["none", "empty-string", "text"],
)
async def test_system_prompt_file_store_round_trip(
    tmp_path: Any,
    prompt: str | None,
    saved: str,
    expected: str | None,
):
    """Explicit clears round-trip through disk as empty-string values."""
    store = FileConversationStore(tmp_path)
    controller, client = _make_prompt_controller(store=store, prompt=prompt)
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    await controller.on_response()
    record = recorder.record
    assert record is not None

    record_file = next(tmp_path.rglob("record.json"))
    raw = json.loads(record_file.read_text(encoding="utf-8"))
    raw_entry = raw["nodes"][record.root_id]["state"][SYSTEM_PROMPT_STATE_KEY]
    assert "data" in raw_entry
    assert raw_entry == {
        "kind": "system_prompt",
        "version": 1,
        "mode": "snapshot",
        "data": saved,
    }

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    stored_entry = _prompt_entry(stored, record.root_id)
    assert stored_entry is not None
    assert stored_entry.data == saved

    restored, restored_client = _make_prompt_controller(
        store=store, prompt="sentinel"
    )
    await replay_exchange_record(restored, stored)
    assert restored_client.system_prompt == expected
    assert restored_client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
    ]


# ---------------------------------------------------------------------------
# Invalid entries
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "entry",
    [
        StateEntry(kind="prompt", version=1, mode="snapshot", data="x"),
        StateEntry(kind="system_prompt", version=2, mode="snapshot", data="x"),
        StateEntry(kind="system_prompt", version=1, mode="delta", data="x"),
        StateEntry(kind="system_prompt", version=1, mode="snapshot", data=123),
    ],
    ids=["kind", "version", "mode", "data"],
)
async def test_system_prompt_invalid_entry_rejected_before_restore(
    entry: StateEntry,
):
    record = new_conversation_record_v2(
        title="bad prompt entry",
        id="c_bad_prompt_entry",
        client_info={},
    )
    record.nodes[record.root_id].state[SYSTEM_PROMPT_STATE_KEY] = entry
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )

    controller, client = _make_prompt_controller(prompt="live")
    notifier = AsyncMock()
    controller._notify_restore_failure = notifier  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Unsupported shinychat:system_prompt"):
        await replay_exchange_record(controller, record)

    assert controller._exchange_recorder.record is None
    assert client.system_prompt == "live"
    assert client.calls == []
    notifier.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("edit_index", [0, 2], ids=["root", "exchange"])
@pytest.mark.parametrize("prompt", ["A", None], ids=["text", "null"])
async def test_system_prompt_shared_parent_change_preserves_existing_branch(
    edit_index: int,
    prompt: str | None,
):
    controller, client = _make_prompt_controller(prompt=prompt)
    transcript = _make_transcript(controller._exchange_recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    target = first if edit_index == 0 else second
    await controller.resubmit(
        target, kind="edit", request_id="edit", message_index=edit_index
    )

    client.system_prompt = "B"
    await _drive_exchange(
        transcript, client, "replacement", "new answer", stream_id="s3"
    )
    await controller.handle_navigate(edit_index, "prev", request_id="navigate")

    assert client.system_prompt == prompt
    assert client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
        _user_turn("two"),
        _assistant_turn("answer two"),
    ]


@pytest.mark.anyio
async def test_system_prompt_removing_parent_change_preserves_existing_branch():
    controller, client = _make_prompt_controller(prompt="A")
    transcript = _make_transcript(controller._exchange_recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    client.system_prompt = "B"
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.resubmit(
        second, kind="edit", request_id="edit", message_index=2
    )

    client.system_prompt = "A"
    await _drive_exchange(
        transcript, client, "replacement", "new answer", stream_id="s3"
    )
    await controller.handle_navigate(2, "prev", request_id="navigate")

    assert client.system_prompt == "B"


@pytest.mark.anyio
@pytest.mark.parametrize("bad_path", ["target", "source"])
@pytest.mark.parametrize(
    "entry",
    [
        StateEntry(kind="prompt", version=1, mode="snapshot", data="x"),
        StateEntry(kind="system_prompt", version=2, mode="snapshot", data="x"),
        StateEntry(kind="system_prompt", version=1, mode="delta", data="x"),
        StateEntry(kind="system_prompt", version=1, mode="snapshot", data=123),
    ],
    ids=["kind", "version", "mode", "data"],
)
async def test_system_prompt_invalid_navigation_leaves_live_state_untouched(
    bad_path: str,
    entry: StateEntry,
):
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    original = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.resubmit(
        original, kind="edit", request_id="edit", message_index=2
    )
    replacement = await _drive_exchange(
        transcript, client, "replacement", "new answer", stream_id="s3"
    )
    record = recorder.record
    assert record is not None
    bad_node = original if bad_path == "target" else replacement
    record.nodes[bad_node].state[SYSTEM_PROMPT_STATE_KEY] = entry
    before = record.model_dump()
    turns_before = list(client.turns)
    chat = controller.chat
    actions_before = list(chat.actions)  # type: ignore[attr-defined]
    client.calls.clear()

    with pytest.raises(ValueError, match="Unsupported shinychat:system_prompt"):
        await controller.handle_navigate(2, "prev", request_id="navigate")

    assert recorder.record is record
    assert record.model_dump() == before
    assert client.system_prompt == "A"
    assert client.turns == turns_before
    assert client.calls == []
    assert chat.actions == actions_before  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (
            {"exclude": {"data"}},
            {"kind": "system_prompt", "version": 1, "mode": "snapshot"},
        ),
        ({"include": {"kind"}}, {"kind": "system_prompt"}),
        ({"include": set()}, {}),
        ({"include": {"data"}}, {"data": None}),
    ],
)
@pytest.mark.parametrize("exclude_none", [False, True])
def test_null_state_data_respects_explicit_field_selection(
    selection: dict[str, Any],
    expected: dict[str, Any],
    exclude_none: bool,
):
    entry = StateEntry(
        kind="system_prompt", version=1, mode="snapshot", data=None
    )
    assert entry.model_dump(exclude_none=exclude_none, **selection) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("null_position", "expected", "calls"),
    [("root", "B", []), ("target", "A", ["A"])],
)
async def test_system_prompt_rewind_resolves_null_entries(
    null_position: str,
    expected: str,
    calls: list[str],
):
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript,
        client,
        "two",
        "answer two",
        stream_id="s2",
        prompt_during="B",
    )
    record = recorder.record
    assert record is not None
    node_id = record.root_id if null_position == "root" else first
    record.nodes[node_id].state[SYSTEM_PROMPT_STATE_KEY] = _null_prompt_entry()
    client.calls.clear()

    await controller.resubmit(
        second, kind="edit", request_id="edit", message_index=2
    )

    assert client.system_prompt == expected
    assert client.prompt_calls() == calls
    assert client.turns == [_user_turn("one"), _assistant_turn("answer one")]
    assert record.active_leaf == first


@pytest.mark.anyio
async def test_system_prompt_null_source_keeps_same_prompt_override_on_rewind():
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    second = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    record = recorder.record
    assert record is not None
    record.nodes[second].state[SYSTEM_PROMPT_STATE_KEY] = _null_prompt_entry()
    client.system_prompt = "override"
    client.calls.clear()

    await controller.resubmit(
        second, kind="edit", request_id="edit", message_index=2
    )

    assert client.system_prompt == "override"
    assert client.prompt_calls() == []
    assert _prompt_data(record, second) == "override"
    assert record.active_leaf == first


@pytest.mark.anyio
@pytest.mark.parametrize("null_position", ["child", "parent", "both"])
async def test_system_prompt_null_entries_preserve_inherited_branch_on_recapture(
    null_position: str,
):
    controller, client = _make_prompt_controller(prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    original = await _drive_exchange(
        transcript, client, "two", "answer two", stream_id="s2"
    )
    await controller.resubmit(
        original, kind="edit", request_id="edit", message_index=2
    )
    record = recorder.record
    assert record is not None
    if null_position in ("parent", "both"):
        record.nodes[first].state[SYSTEM_PROMPT_STATE_KEY] = (
            _null_prompt_entry()
        )
    if null_position in ("child", "both"):
        record.nodes[original].state[SYSTEM_PROMPT_STATE_KEY] = (
            _null_prompt_entry()
        )
    client.system_prompt = "B"

    await _drive_exchange(
        transcript, client, "replacement", "new answer", stream_id="s3"
    )

    assert _prompt_data(record, first) == "B"
    assert _prompt_data(record, original) == "A"
    await controller.handle_navigate(2, "prev", request_id="navigate")
    assert client.system_prompt == "A"
    assert client.turns == [
        _user_turn("one"),
        _assistant_turn("answer one"),
        _user_turn("two"),
        _assistant_turn("answer two"),
    ]


@pytest.mark.anyio
async def test_system_prompt_real_chatlas_saved_clear_removes_system_turn():
    import chatlas

    source_client = chatlas.ChatOpenAI(api_key="test")
    source, _ = _make_prompt_controller(client=source_client)
    recorder = source._exchange_recorder
    transcript = _make_transcript(recorder)
    exchange = await transcript.record_accepted_input_and_notify(
        _stored_message("user", "one")
    )
    await transcript.start_stream(
        stream_id="s1",
        entry=TranscriptEntry(
            message=_stored_message("assistant", "answer one")
        ),
        owner_task=None,
        exchange_id=exchange,
        send=_sent,
    )
    source_client.set_turns(
        [
            chatlas.Turn(role="user", contents="one"),
            chatlas.Turn(role="assistant", contents="answer one"),
        ]
    )
    await transcript.end_stream(
        stream_id="s1", status=None, error=None, send=_sent
    )
    record = recorder.record
    assert record is not None
    assert _prompt_data(record, record.root_id) == ""

    client = chatlas.ChatOpenAI(api_key="test", system_prompt="must be cleared")
    restored, _ = _make_prompt_controller(client=client)
    await replay_exchange_record(restored, record)

    assert client.system_prompt is None
    assert [
        turn.role for turn in client.get_turns(include_system_prompt=True)
    ] == ["user", "assistant"]


@pytest.mark.anyio
async def test_system_prompt_file_store_preserves_null_inheritance(
    tmp_path: Any,
):
    store = FileConversationStore(tmp_path)
    controller, client = _make_prompt_controller(store=store, prompt="A")
    recorder = controller._exchange_recorder
    transcript = _make_transcript(recorder)
    first = await _drive_exchange(
        transcript, client, "one", "answer one", stream_id="s1"
    )
    record = recorder.record
    assert record is not None
    record.nodes[first].state[SYSTEM_PROMPT_STATE_KEY] = _null_prompt_entry()
    await controller.on_response()

    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    assert _prompt_data(stored, first) is None
    restored, restored_client = _make_prompt_controller(
        store=store, prompt="sentinel"
    )
    await replay_exchange_record(restored, stored)

    assert restored_client.system_prompt == "A"
    assert restored_client.prompt_calls() == ["A"]
