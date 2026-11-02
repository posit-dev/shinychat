"""Acceptance regressions for exact-prefix model checkpoint deltas.

New captures store only the suffix when the parent node's effective
recorded context on the same branch is an exact prefix of the live turns
(canonical JSON per turn), an empty delta when nothing changed, and a
full snapshot on any rewrite, truncation, compaction, or missing /
incompatible baseline. Recaptures preserve the effective contexts of
existing descendants. Every test exercises production capture/restore
paths (recorder, transcript, controller, store), never test-only
bypasses.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from _history_test_helpers import replay_exchange_record
from pydantic import JsonValue
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._history_client import TurnsAdapter
from shinychat._history_store import InMemoryConversationStore
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_controller import (
    _FakeAdapter,
    _make_controller,
    _sent,
    _stored_message,
    part,
)

SEED = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "hi there"},
]


def _transcript(recorder: Any) -> ChatTranscript:
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_message_committed=recorder.message_committed,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )


async def _drive_exchange(
    transcript: ChatTranscript,
    adapter: _FakeAdapter,
    text: str,
    *,
    stream_id: str,
) -> str:
    exchange_id = await transcript.record_accepted_input_and_notify(
        _stored_message("user", text)
    )
    await transcript.start_stream(
        stream_id=stream_id,
        entry=TranscriptEntry(
            message=_stored_message("assistant", f"answer {text}")
        ),
        owner_task=None,
        exchange_id=exchange_id,
        send=_sent,
    )
    adapter.turns.append({"role": "user", "content": text})
    adapter.turns.append({"role": "assistant", "content": f"answer {text}"})
    await transcript.end_stream(
        stream_id=stream_id, status=None, error=None, send=_sent
    )
    return exchange_id


def _turn_entry(record: ConversationRecordV2, node_id: str) -> StateEntry:
    return record.nodes[node_id].state[TURNS_STATE_KEY]


def _own_turns(*texts: str) -> list[dict[str, Any]]:
    return [
        turn
        for text in texts
        for turn in (
            {"role": "user", "content": text},
            {"role": "assistant", "content": f"answer {text}"},
        )
    ]


async def _restore_turns(
    store: InMemoryConversationStore, conv_id: str
) -> list[dict[str, Any]]:
    viewer, _ = _make_controller(store=store, adapter=_FakeAdapter())
    await viewer.switch_to(conv_id)
    return cast(list[dict[str, Any]], viewer.adapter.get_turns_json())


async def _point_and_restore(
    store: InMemoryConversationStore, conv_id: str, leaf: str
) -> list[dict[str, Any]]:
    stored = await store.get(part(), conv_id)
    assert isinstance(stored, ConversationRecordV2)
    stored.set_active_leaf(leaf)
    await store.put(part(), stored)
    return await _restore_turns(store, conv_id)


@pytest.mark.anyio
async def test_append_only_growth_stores_suffix_deltas_and_restores_exactly():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)

    exchange_ids = [
        await _drive_exchange(transcript, adapter, text, stream_id=f"s{i}")
        for i, text in enumerate(("one", "two", "three"))
    ]

    record = recorder.record
    assert record is not None
    root_entry = _turn_entry(record, record.root_id)
    assert root_entry.mode == "snapshot"
    assert root_entry.data == SEED
    for node_id, text in zip(exchange_ids, ("one", "two", "three")):
        entry = _turn_entry(record, node_id)
        assert entry.mode == "delta"
        assert entry.data == _own_turns(text)

    conv_id = record.id
    # A fresh controller on the same store restores the full context.
    assert await _restore_turns(store, conv_id) == adapter.get_turns_json()
    # The branch baseline is each node's own path, not the latest capture:
    # pointing at the mid-chain leaf restores exactly its prefix.
    assert await _point_and_restore(store, conv_id, exchange_ids[1]) == [
        *SEED,
        *_own_turns("one", "two"),
    ]
    assert await _point_and_restore(store, conv_id, record.root_id) == SEED


@pytest.mark.anyio
async def test_unchanged_capture_stores_empty_delta_and_restores_exactly():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    await _drive_exchange(transcript, adapter, "one", stream_id="s1")

    # An inputless append adds no model turns: the capture at its node is
    # exactly the parent's effective context, stored as an empty delta
    # rather than another full copy.
    await recorder.message_committed(
        None, TranscriptEntry(message=_stored_message("assistant", "note"))
    )
    record = recorder.record
    assert record is not None
    leaf = record.active_leaf
    assert leaf is not None
    entry = _turn_entry(record, leaf)
    assert entry.mode == "delta"
    assert entry.data == []

    assert await _restore_turns(store, record.id) == adapter.get_turns_json()


@pytest.mark.anyio
async def test_truncation_falls_back_to_snapshot_then_resumes_deltas():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    await _drive_exchange(transcript, adapter, "one", stream_id="s1")
    second = await _drive_exchange(transcript, adapter, "two", stream_id="s2")

    adapter.turns[:] = adapter.turns[:3]
    truncated = list(adapter.turns)
    assert await recorder.flush_pending()
    record = recorder.record
    assert record is not None
    entry = _turn_entry(record, second)
    assert entry.mode == "snapshot"
    assert entry.data == truncated

    # Append-only growth after the snapshot fallback anchors at the new
    # snapshot instead of copying the whole list again.
    third = await _drive_exchange(transcript, adapter, "three", stream_id="s3")
    entry = _turn_entry(record, third)
    assert entry.mode == "delta"
    assert entry.data == _own_turns("three")

    assert await _restore_turns(store, record.id) == [
        *truncated,
        *_own_turns("three"),
    ]


@pytest.mark.anyio
async def test_compaction_falls_back_to_snapshot_then_append_resumes_deltas():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    await _drive_exchange(transcript, adapter, "one", stream_id="s1")
    second = await _drive_exchange(transcript, adapter, "two", stream_id="s2")

    compacted = [
        {"role": "system", "content": "summary of the conversation so far"},
        *_own_turns("two"),
    ]
    adapter.turns[:] = compacted
    assert await recorder.flush_pending()
    record = recorder.record
    assert record is not None
    entry = _turn_entry(record, second)
    assert entry.mode == "snapshot"
    assert entry.data == compacted

    third = await _drive_exchange(transcript, adapter, "three", stream_id="s3")
    entry = _turn_entry(record, third)
    assert entry.mode == "delta"
    assert entry.data == _own_turns("three")

    assert await _restore_turns(store, record.id) == [
        *compacted,
        *_own_turns("three"),
    ]


async def _one_exchange() -> tuple[Any, _FakeAdapter, Any, str]:
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    exchange_id = await _drive_exchange(
        transcript, adapter, "one", stream_id="s1"
    )
    return recorder, adapter, transcript, exchange_id


@pytest.mark.anyio
@pytest.mark.parametrize("replacement", [True, 1.0], ids=["bool", "float"])
async def test_scalar_type_change_is_not_an_exact_prefix(replacement):
    adapter = _FakeAdapter()
    adapter.turns[0]["n"] = 1
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    exchange_id = await _drive_exchange(
        transcript, adapter, "one", stream_id="s1"
    )
    # The saved parent contains the same key with integer 1, so Python
    # equality would hide this type-only change in the inherited prefix.
    record = recorder.record
    assert record is not None
    baseline = cast(
        list[dict[str, Any]], _turn_entry(record, record.root_id).data
    )
    assert type(baseline[0]["n"]) is int
    assert baseline[0]["n"] == 1
    adapter.turns[0]["n"] = replacement
    assert adapter.turns[0]["n"] == 1
    assert await recorder.flush_pending()
    record = recorder.record
    assert record is not None
    entry = _turn_entry(record, exchange_id)
    assert entry.mode == "snapshot"
    assert entry.data == adapter.turns


@pytest.mark.anyio
async def test_key_order_still_counts_as_exact_prefix():
    recorder, adapter, _, exchange_id = await _one_exchange()
    before = _turn_entry(recorder.record, exchange_id).model_copy(deep=True)  # type: ignore[union-attr]
    adapter.turns[0] = {"content": "hello", "role": "user"}
    assert await recorder.flush_pending()
    record = recorder.record
    assert record is not None
    entry = _turn_entry(record, exchange_id)
    assert entry.mode == "delta"
    assert entry == before


@pytest.mark.anyio
async def test_repeated_same_node_recapture_keeps_delta_and_converts_no_child():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)
    first = await _drive_exchange(transcript, adapter, "one", stream_id="s1")
    second = await _drive_exchange(transcript, adapter, "two", stream_id="s2")
    record = recorder.record
    assert record is not None
    before_first = _turn_entry(record, first).model_copy(deep=True)
    before_second = _turn_entry(record, second).model_copy(deep=True)
    assert before_first.mode == "delta"
    assert before_second.mode == "delta"

    # Recapture with the node's own recorded context live is idempotent
    # and converts no delta child; the baseline is always the parent
    # branch, so the same delta is rewritten byte for byte.
    adapter.turns = [*SEED, *_own_turns("one")]
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            first, "node_close", model_only=True
        )
        assert await recorder.capture_state_locked(
            first, "node_close", model_only=True
        )
    assert _turn_entry(record, first) == before_first
    assert _turn_entry(record, second) == before_second

    # Recapture at the leaf with the full live context is idempotent too.
    adapter.turns = [*SEED, *_own_turns("one", "two")]
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            second, "node_close", model_only=True
        )
    assert _turn_entry(record, first) == before_first
    assert _turn_entry(record, second) == before_second


@pytest.mark.anyio
async def test_parent_recapture_preserves_mixed_children_and_descendants():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="mixed", id="c_mixed", client_info={}
    )
    root_entry = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(JsonValue, [{"role": "system", "content": "s"}]),
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = root_entry

    def add_child(
        node_id: str, entry: StateEntry | None, *, finish: bool = True
    ) -> str:
        record.open_exchange(node_id, _stored_message("user", node_id))
        if entry is not None:
            record.nodes[node_id].state[TURNS_STATE_KEY] = entry
        if finish:
            record.finish_exchange(node_id, "ok", None)
            record.nodes[node_id].checkpoint = "valid"
        return node_id

    def delta(*contents: str) -> StateEntry:
        return StateEntry(
            kind="turns",
            version=1,
            mode="delta",
            data=cast(
                JsonValue,
                [{"role": "user", "content": content} for content in contents],
            ),
        )

    node_a = add_child("ex_a", delta("a"))
    c_delta = add_child("ex_c_delta", delta("c1"))
    c_snap = add_child(
        "ex_c_snap",
        StateEntry(
            kind="turns",
            version=1,
            mode="snapshot",
            data=cast(JsonValue, [{"role": "user", "content": "x"}]),
        ),
    )
    record.set_active_leaf(node_a)
    c_inherit = add_child("ex_c_inherit", None)
    grandchild = add_child("ex_g", delta("g1"))
    record.set_active_leaf(node_a)
    c_pending = add_child("ex_c_pending", None, finish=False)

    recorder.record = record
    controller._active_id.set(record.id)

    # Rewrite the parent's own suffix: still an extension of the root
    # baseline, but a change to what existing descendants inherit.
    adapter.turns = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a rewritten"},
    ]
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            node_a, "node_close", model_only=True
        )

    assert _turn_entry(record, node_a) == delta("a rewritten")
    # Delta and inheritance-only children are pinned to their pre-capture
    # materialized contexts; the deeper delta descendant folds from its
    # pinned parent and stays untouched.
    assert _turn_entry(record, c_delta) == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(
            JsonValue,
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "a"},
                {"role": "user", "content": "c1"},
            ],
        ),
    )
    assert _turn_entry(record, c_inherit) == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(
            JsonValue,
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "a"},
            ],
        ),
    )
    assert _turn_entry(record, grandchild) == delta("g1")
    # Snapshot-holding children and unresolved pending children are not
    # touched; a pending node never gains invented model state.
    assert _turn_entry(record, c_snap).data == [
        {"role": "user", "content": "x"}
    ]
    assert TURNS_STATE_KEY not in record.nodes[c_pending].state

    # Every dependent branch still restores exactly its pre-recapture
    # context through the production restore path.
    store = InMemoryConversationStore()
    await store.put(part(), record)
    conv_id = record.id
    assert await _point_and_restore(store, conv_id, c_delta) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "c1"},
    ]
    assert await _point_and_restore(store, conv_id, grandchild) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "g1"},
    ]
    assert await _point_and_restore(store, conv_id, c_snap) == [
        {"role": "user", "content": "x"}
    ]
    assert await _point_and_restore(store, conv_id, node_a) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a rewritten"},
    ]


@pytest.mark.anyio
async def test_missing_baseline_falls_back_to_snapshot():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="no baseline", id="c_no_baseline", client_info={}
    )
    # Programmatic content before the starting checkpoint: no recorded
    # turn entry exists anywhere on the branch.
    child = record.open_inputless_exchange()
    recorder.record = record
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            child, "node_close", model_only=True
        )
    entry = _turn_entry(record, child)
    assert entry.mode == "snapshot"
    assert entry.data == SEED


@pytest.mark.anyio
async def test_incompatible_baseline_falls_back_to_snapshot():
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="incompatible", id="c_incompatible", client_info={}
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="chatlas",
        version=1,
        mode="snapshot",
        data=cast(JsonValue, [{"role": "user", "content": "other client"}]),
    )
    child = record.open_inputless_exchange()
    recorder.record = record
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            child, "node_close", model_only=True
        )
    # The recorded chatlas baseline cannot be compared against the generic
    # client, so the complete current list is stored.
    entry = _turn_entry(record, child)
    assert entry.mode == "snapshot"
    assert entry.data == SEED


@pytest.mark.anyio
async def test_mixed_legacy_and_new_delta_chain_restores_exactly():
    store = InMemoryConversationStore()
    adapter = _FakeAdapter()
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="mixed chain", id="c_mixed_chain", client_info={}
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=cast(JsonValue, SEED)
    )
    record.open_exchange("legacy", _stored_message("user", "legacy"))
    record.nodes["legacy"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=cast(JsonValue, _own_turns("legacy")),
    )
    record.finish_exchange("legacy", "ok", None)
    record.nodes["legacy"].checkpoint = "valid"
    recorder.record = record
    controller._active_id.set(record.id)
    adapter.turns = [*SEED, *_own_turns("legacy")]

    # New captures extend the imported legacy chain as deltas.
    transcript = _transcript(recorder)
    new_exchange = await _drive_exchange(
        transcript, adapter, "new", stream_id="s1"
    )
    entry = _turn_entry(record, new_exchange)
    assert entry.mode == "delta"
    assert entry.data == _own_turns("new")

    assert await _restore_turns(store, record.id) == [
        *SEED,
        *_own_turns("legacy"),
        *_own_turns("new"),
    ]


@pytest.mark.anyio
async def test_chatlas_tool_result_deltas_and_prompt_only_change_round_trip():
    """Offline real chatlas: tool-result turns ride in deltas, a prompt-only
    change records no turn copy, and a fresh client restores exactly."""
    chatlas = pytest.importorskip("chatlas")
    from chatlas.types import ContentToolRequest, ContentToolResult

    client = chatlas.ChatOpenAI(system_prompt="be precise", api_key="test")
    seed_turns = [
        chatlas.Turn(role="user", contents="seed"),
        chatlas.Turn(role="assistant", contents="seed reply"),
    ]
    client.set_turns(seed_turns)
    store = InMemoryConversationStore()
    controller, _ = _make_controller(
        store=store,
        adapter=TurnsAdapter(client),  # type: ignore[arg-type]
    )
    recorder = controller._exchange_recorder
    transcript = _transcript(recorder)

    async def drive(text: str, new_turns: list[Any], *, stream_id: str) -> str:
        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", text)
        )
        await transcript.start_stream(
            stream_id=stream_id,
            entry=TranscriptEntry(
                message=_stored_message("assistant", f"answer {text}")
            ),
            owner_task=None,
            exchange_id=exchange_id,
            send=_sent,
        )
        client.set_turns([*client.get_turns(), *new_turns])
        await transcript.end_stream(
            stream_id=stream_id, status=None, error=None, send=_sent
        )
        return exchange_id

    request = ContentToolRequest(
        id="call_1", name="get_weather", arguments={"city": "Paris"}
    )
    first = await drive(
        "one",
        [
            chatlas.Turn(role="user", contents="one"),
            chatlas.Turn(role="assistant", contents=[request]),
            chatlas.Turn(
                role="user",
                contents=[
                    ContentToolResult(value="sunny, 20C", request=request)
                ],
            ),
            chatlas.Turn(role="assistant", contents="answer one"),
        ],
        stream_id="s1",
    )

    record = recorder.record
    assert record is not None
    root_entry = _turn_entry(record, record.root_id)
    assert root_entry.kind == "chatlas"
    assert root_entry.mode == "snapshot"
    first_entry = _turn_entry(record, first)
    assert first_entry.mode == "delta"
    first_data = cast(list[dict[str, Any]], first_entry.data)
    assert [turn["role"] for turn in first_data] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    tool_result = cast(dict[str, Any], first_data[2]["contents"][0])
    assert tool_result["value"] == "sunny, 20C"
    # The system prompt never leaks into captured turns.
    assert '"role":"system"' not in record.model_dump_json()

    # A prompt-only change is captured sparsely on its own namespace; the
    # node-close recapture of the exchange keeps its unchanged delta.
    client.system_prompt = "be terse"
    before_first = first_entry.model_copy(deep=True)
    second = await drive(
        "two",
        [
            chatlas.Turn(role="user", contents="two"),
            chatlas.Turn(role="assistant", contents="answer two"),
        ],
        stream_id="s2",
    )
    assert _turn_entry(record, first) == before_first
    assert record.nodes[first].state[SYSTEM_PROMPT_STATE_KEY].data == "be terse"
    second_entry = _turn_entry(record, second)
    assert second_entry.mode == "delta"
    assert len(cast(list[Any], second_entry.data)) == 2

    # A fresh client restores the prompt and the exact turn list,
    # tool-result turns included, through the production replay path.
    restored_client = chatlas.ChatOpenAI(api_key="test")
    restored, _ = _make_controller(
        store=store,
        adapter=TurnsAdapter(restored_client),  # type: ignore[arg-type]
    )
    stored = await store.get(part(), record.id)
    assert isinstance(stored, ConversationRecordV2)
    await replay_exchange_record(restored, stored)

    assert restored_client.system_prompt == "be terse"
    assert [t.role for t in restored_client.get_turns()] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    restored_turns = restored_client.get_turns()
    assert restored_turns[2].contents[0].text == "one"  # type: ignore[attr-defined]
    restored_result = restored_turns[4].contents[0]
    assert isinstance(restored_result, ContentToolResult)
    assert restored_result.value == "sunny, 20C"


@pytest.mark.anyio
@pytest.mark.parametrize("intermediate", [None, "ok", "pending"])
async def test_entryless_ancestor_recapture_preserves_legacy_delta_child(
    intermediate,
):
    """An ancestor without recorded entries still must not rewrite a legacy
    delta child's saved context, while entryless children keep the
    first-capture inheritance semantic."""
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="entryless", id="c_entryless", client_info={}
    )
    if intermediate is not None:
        record.open_exchange("ex_middle", _stored_message("user", "middle"))
        if intermediate == "ok":
            record.finish_exchange("ex_middle", "ok", None)
            record.nodes["ex_middle"].checkpoint = "valid"
    legacy = "ex_legacy"
    record.open_exchange(legacy, _stored_message("user", "legacy"))
    record.nodes[legacy].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=cast(JsonValue, [{"role": "user", "content": "saved"}]),
    )
    record.finish_exchange(legacy, "ok", None)
    record.nodes[legacy].checkpoint = "valid"
    record.set_active_leaf(record.root_id)
    inheriting = "ex_inheriting"
    record.open_exchange(inheriting, _stored_message("user", "inheriting"))
    record.finish_exchange(inheriting, "ok", None)
    record.nodes[inheriting].checkpoint = "valid"
    recorder.record = record
    controller._active_id.set(record.id)

    async with recorder.lock:
        assert await recorder.capture_state_locked(
            record.root_id, "root_close", model_only=True
        )

    root_entry = _turn_entry(record, record.root_id)
    assert root_entry.mode == "snapshot"
    assert root_entry.data == SEED
    # The legacy child's saved context is pinned, not extended by SEED.
    assert _turn_entry(record, legacy) == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(JsonValue, [{"role": "user", "content": "saved"}]),
    )
    # The entryless child had no saved context: it simply inherits the
    # newly established one (no invented pin).
    assert TURNS_STATE_KEY not in record.nodes[inheriting].state
    if intermediate is not None:
        assert TURNS_STATE_KEY not in record.nodes["ex_middle"].state
        assert record.nodes["ex_middle"].status == intermediate

    store = InMemoryConversationStore()
    await store.put(part(), record)
    assert await _point_and_restore(store, record.id, legacy) == [
        {"role": "user", "content": "saved"}
    ]
    assert await _point_and_restore(store, record.id, inheriting) == SEED


@pytest.mark.anyio
async def test_pending_intermediate_traversal_preserves_captured_descendant():
    """A pending entryless intermediate gains no state, but its captured
    descendants keep their exact saved context across a parent rewrite."""
    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="pending intermediate", id="c_pending_mid", client_info={}
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(JsonValue, [{"role": "system", "content": "s"}]),
    )
    node_a = "ex_a"
    record.open_exchange(node_a, _stored_message("user", "a"))
    record.nodes[node_a].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=cast(JsonValue, [{"role": "user", "content": "a"}]),
    )
    record.finish_exchange(node_a, "ok", None)
    record.nodes[node_a].checkpoint = "valid"
    # A still-pending exchange with a newer input accepted beneath it, the
    # newer one already finished (the late-finish shape).
    pending = "ex_pending"
    record.open_exchange(pending, _stored_message("user", "pending"))
    grandchild = "ex_grandchild"
    record.open_exchange(grandchild, _stored_message("user", "g"))
    record.nodes[grandchild].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=cast(JsonValue, [{"role": "assistant", "content": "g answer"}]),
    )
    record.finish_exchange(grandchild, "ok", None)
    record.nodes[grandchild].checkpoint = "valid"
    recorder.record = record
    controller._active_id.set(record.id)

    adapter.turns = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a rewritten"},
    ]
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            node_a, "node_close", model_only=True
        )

    assert _turn_entry(record, node_a).mode == "delta"
    # The pending intermediate is untouched.
    assert TURNS_STATE_KEY not in record.nodes[pending].state
    assert record.nodes[pending].status == "pending"
    # The captured descendant under it is pinned to its saved context.
    assert _turn_entry(record, grandchild) == StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=cast(
            JsonValue,
            [
                {"role": "system", "content": "s"},
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "g answer"},
            ],
        ),
    )

    store = InMemoryConversationStore()
    await store.put(part(), record)
    assert await _point_and_restore(store, record.id, grandchild) == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "g answer"},
    ]


@pytest.mark.anyio
async def test_unpreservable_inherited_child_fails_capture_without_mutation():
    """When a dependent child's saved context cannot be materialized for
    preservation, capture fails loudly and commits nothing."""
    from shinychat._history_recorder import _ModelCaptureError

    adapter = _FakeAdapter()
    controller, _ = _make_controller(adapter=adapter)
    recorder = controller._exchange_recorder
    record = new_conversation_record_v2(
        title="unpreservable", id="c_unpreservable", client_info={}
    )
    incompatible = StateEntry(
        kind="chatlas",
        version=1,
        mode="snapshot",
        data=cast(JsonValue, [{"role": "user", "content": "other client"}]),
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = incompatible
    record.nodes[record.root_id].checkpoint = "valid"
    child = "ex_child"
    record.open_exchange(child, _stored_message("user", "child"))
    record.finish_exchange(child, "ok", None)
    record.nodes[child].checkpoint = "valid"
    recorder.record = record
    controller._active_id.set(record.id)
    before = record.model_dump(mode="json")

    async with recorder.lock:
        with pytest.raises(_ModelCaptureError):
            await recorder.capture_state_locked(
                record.root_id, "root_close", model_only=True
            )

    # Nothing staged was committed: entries and checkpoints are unchanged.
    assert record.model_dump(mode="json") == before
    assert record.nodes[record.root_id].checkpoint == "valid"
    assert TURNS_STATE_KEY not in record.nodes[child].state
