"""Regressions from the approved checkpoint-validity review resolution."""

from copy import deepcopy
from typing import Any, cast

import pytest
from _history_test_helpers import replay_exchange_record
from pydantic import JsonValue
from shinychat._history_plan import canonical_values
from shinychat._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    CapturedMessage,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_checkpoint_models import _complete_append, _prompt_adapter
from test_history_controller import (
    _FakeChat,
    _make_controller,
    _make_v2_resubmit_controller,
    _stored_message,
    part,
)
from test_history_stream_persistence import (
    _assistant_message,
    _Backend,
    _chunk,
    _end_stream,
    _open_stream,
    _saved,
    _start_stream,
    _text,
    _wire,
)
from test_history_stream_persistence import backend as _backend_fixture

backend = _backend_fixture


def _recoverable_tree() -> ConversationRecordV2:
    record = new_conversation_record_v2(
        title="recoverable branches", id="c_recovery", client_info={}
    )
    record.nodes[record.root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    for key in ("valid", "invalid"):
        record.set_active_leaf(record.root_id)
        record.open_exchange(key, _stored_message("user", key))
        record.append_message(
            key,
            CapturedMessage.from_stored_message(
                _stored_message("assistant", key + " answer"), icon=None
            ),
        )
        record.nodes[key].state[TURNS_STATE_KEY] = StateEntry(
            kind="turns",
            version=1,
            mode="snapshot",
            data=[{"role": "assistant", "content": key + " answer"}],
        )
        record.nodes[key].state[VALUES_STATE_KEY] = StateEntry(
            kind="values", version=1, mode="snapshot", data={"branch": key}
        )
        record.nodes[key].checkpoint = "valid" if key == "valid" else "invalid"
    record.set_active_leaf("valid")
    return record


@pytest.mark.anyio
@pytest.mark.parametrize("model_unavailable", [False, True])
async def test_nonisolated_restore_retains_recoverable_branch_across_writes(
    backend: _Backend,
    model_unavailable: bool,
) -> None:
    source = _recoverable_tree()
    if model_unavailable:
        source.nodes["valid"].state[TURNS_STATE_KEY].version = 2
        source.nodes["invalid"].status = "pending"
    await backend.store.put(part(), source)
    frozen_source = source.model_dump_json()
    invalid = source.nodes["invalid"].model_dump_json()
    viewer, _ = _make_controller(store=backend.reader)
    if model_unavailable:
        with pytest.warns(UserWarning, match="model context is unavailable"):
            await viewer.switch_to(source.id)
    else:
        await viewer.switch_to(source.id)
    recorder = viewer._exchange_recorder
    assert not recorder.source_isolated
    assert recorder.read_only is model_unavailable
    assert recorder.record is not None
    assert recorder.record.nodes["invalid"].model_dump_json() == invalid
    assert recorder.record.checkpoint_siblings("valid") == ["valid"]
    if model_unavailable:
        await viewer.rename(source.id, "metadata remains writable")
    else:
        async with recorder.lock:
            await recorder.persist_active_leaf_locked(recorder.record, "valid")
        assert (await _saved(backend, source.id)).nodes[
            "invalid"
        ].model_dump_json() == invalid
        assert await viewer.save()
        assert (await _saved(backend, source.id)).nodes[
            "invalid"
        ].model_dump_json() == invalid
        await recorder.accepted_input(
            "next", _stored_message("user", "next input"), lambda: None
        )
    saved = await _saved(backend, source.id)
    assert saved.nodes["invalid"].model_dump_json() == invalid
    assert source.model_dump_json() == frozen_source


@pytest.mark.anyio
async def test_isolated_prefix_retains_ended_answer_but_not_its_checkpoint(
    backend: _Backend,
) -> None:
    source = _recoverable_tree()
    source.nodes["valid"].checkpoint = "invalid"
    source.set_active_leaf("valid")
    source.open_exchange("child", _stored_message("user", "followup"))
    source.append_message(
        "child",
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "child answer"), icon=None
        ),
    )
    sdk_prefix: list[JsonValue] = [
        {"role": "user", "content": "valid"},
        {"role": "assistant", "content": "valid answer"},
        {"role": "user", "content": "followup"},
        {"role": "assistant", "content": "child answer"},
    ]
    source.nodes["child"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=sdk_prefix
    )
    source.nodes["child"].checkpoint = "valid"
    source.open_exchange("pending", _stored_message("user", "unfinished"))
    source.nodes["pending"].messages.append(
        CapturedMessage.from_stored_message(
            _stored_message("assistant", "unfinished fragment"), icon=None
        )
    )
    await backend.store.put(part(), source)
    frozen = source.model_dump_json()
    viewer, _ = _make_controller(store=backend.reader)
    chat = cast(_FakeChat, viewer.chat)
    await viewer.switch_to(source.id)
    recorder = viewer._exchange_recorder
    assert recorder.source_isolated and recorder.read_only
    local = recorder.record
    assert local is not None
    assert set(local.nodes) == {source.root_id, "valid", "child"}
    assert [
        message["segments"][0]["content"] for message in chat.restored_messages
    ] == ["valid", "valid answer", "followup", "child answer"]
    assert viewer.adapter.get_turns_json() == sdk_prefix
    assert local.nodes["valid"].checkpoint_state == "invalid"
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        local.require_checkpoint("valid")
    assert local.checkpoint_leaf("valid") == "child"
    assert local.checkpoint_siblings("child") == ["child"]
    assert not await recorder.flush_pending()
    assert source.model_dump_json() == frozen
    assert (await _saved(backend, source.id)).model_dump_json() == frozen


def test_deep_checkpoint_metadata_and_selected_branch_ordering() -> None:
    record = new_conversation_record_v2(title="deep", client_info={})
    parent = record.root_id
    for _ in range(1250):
        parent = record.open_inputless_exchange()
        record.finish_exchange(parent, "ok", None)
        record.nodes[parent].checkpoint = "valid"
    record.set_active_leaf(parent)
    first = record.open_inputless_exchange()
    record.finish_exchange(first, "ok", None)
    record.nodes[first].checkpoint = "valid"
    record.set_active_leaf(parent)
    second = record.open_inputless_exchange()
    record.finish_exchange(second, "ok", None)
    record.nodes[second].checkpoint = "valid"
    assert record.path_sibling_metadata() == {second: (1, 2)}
    record.nodes[parent].selected_child = first
    assert record.checkpoint_leaf(record.root_id) == first
    record.nodes[parent].selected_child = "removed"
    assert record.checkpoint_leaf(record.root_id) == second
    record.nodes[second].checkpoint = "invalid"
    assert record.checkpoint_leaf(record.root_id) == first
    assert record.checkpoint_siblings(first) == [first]


@pytest.mark.parametrize("malformation", ["cycle", "dangling"])
def test_checkpoint_traversal_rejects_malformed_children(
    malformation: str,
) -> None:
    record = _recoverable_tree()
    record.nodes["valid"].children = [
        record.root_id if malformation == "cycle" else "missing"
    ]
    with pytest.raises(ValueError, match="Cycle|Unknown exchange"):
        record.checkpoint_leaf(record.root_id)
    with pytest.raises(ValueError, match="Cycle|Unknown exchange"):
        record.path_sibling_metadata()


@pytest.mark.anyio
async def test_state_staging_preserves_all_sparse_pins_and_avoids_payload_copies(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {"value": "old"}
    writer, _ = _make_controller(
        store=backend.store,
        adapter=_prompt_adapter(),
        save_callbacks=[lambda out: out.update(values)],
    )
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    assert await recorder.response_settled()
    record = recorder.record
    assert record is not None
    child = record.open_inputless_exchange()
    record.nodes[child].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "assistant", "content": "delta child"}],
    )
    record.set_active_leaf(node_id)
    unrelated = record.nodes[record.root_id].state[TURNS_STATE_KEY].data
    original_dicts = {key: node.state for key, node in record.nodes.items()}
    frozen = record.model_dump_json()
    values["value"] = "new"
    writer.adapter.set_system_prompt("new prompt")
    writer.adapter.set_turns_json(
        [{"role": "assistant", "content": "new SDK frame"}]
    )

    async def fail_after_all_builtin_pins(context: Any) -> StateEntry | None:
        assert recorder.record is record
        raise RuntimeError("last hook failed")

    recorder._register_capture_hook("app:last", fail_after_all_builtin_pins)
    original_copy = ConversationRecordV2.model_copy
    deep_copies: list[bool] = []

    def spy_copy(
        self: ConversationRecordV2, *, update: Any = None, deep: bool = False
    ) -> ConversationRecordV2:
        deep_copies.append(deep)
        return original_copy(self, update=update, deep=deep)

    monkeypatch.setattr(ConversationRecordV2, "model_copy", spy_copy)
    with pytest.raises(RuntimeError, match="last hook failed"):
        async with recorder.lock:
            await recorder.capture_state_locked(node_id, "node_close")
    assert deep_copies and not any(deep_copies)
    assert record.model_dump_json() == frozen
    assert all(
        record.nodes[key].state is state
        for key, state in original_dicts.items()
    )
    assert VALUES_STATE_KEY not in record.nodes[child].state
    assert SYSTEM_PROMPT_STATE_KEY not in record.nodes[child].state
    assert record.nodes[child].state[TURNS_STATE_KEY].mode == "delta"

    external = StateEntry(
        kind="custom", version=1, mode="snapshot", data={"list": [1]}
    )
    recorder._register_capture_hook("app:last", lambda context: external)
    async with recorder.lock:
        assert await recorder.capture_state_locked(node_id, "node_close")
    assert not any(deep_copies)
    assert record.nodes[record.root_id].state[TURNS_STATE_KEY].data is unrelated
    assert record.nodes[child].state[TURNS_STATE_KEY].mode == "snapshot"
    assert (
        record.nodes[child].state[SYSTEM_PROMPT_STATE_KEY].data == "live prompt"
    )
    assert record.nodes[child].state[VALUES_STATE_KEY].data == {"value": "old"}
    saved_custom = deepcopy(record.nodes[node_id].state["app:last"].data)
    assert isinstance(external.data, dict)
    local = external.data["list"]
    assert isinstance(local, list)
    local.append(2)
    assert (
        record.nodes[node_id].state["app:last"].data
        == saved_custom
        == {"list": [1]}
    )


@pytest.mark.anyio
@pytest.mark.parametrize("previously_saved", [False, True])
async def test_first_input_captures_the_current_starting_pair_once(
    backend: _Backend,
    previously_saved: bool,
) -> None:
    live = {"dataset": "West"}
    captures: list[dict[str, Any]] = []

    def capture(values: dict[str, Any]) -> None:
        values.update(live)
        captures.append(dict(values))

    adapter = _prompt_adapter()
    writer, _ = _make_controller(
        store=backend.store, adapter=adapter, save_callbacks=[capture]
    )
    recorder = writer._exchange_recorder
    assert recorder.record is None
    assert not await writer.save()
    assert captures == []
    assert await backend.reader.list(part()) == []

    adapter.set_turns_json([{"role": "assistant", "content": "West context"}])
    adapter.set_system_prompt("West prompt")
    if previously_saved:
        recorder.record = new_conversation_record_v2(
            title="explicit starting point", client_info={}
        )
        assert await recorder.save_current()
        assert captures == [{"dataset": "West"}]
        captures.clear()

    live["dataset"] = "East"
    starting_turns = [{"role": "assistant", "content": "East context"}]
    adapter.set_turns_json(starting_turns)
    adapter.set_system_prompt("East prompt")
    transcript, first = await _open_stream(writer)
    record = recorder.record
    assert record is not None
    root = record.root_id
    assert captures == [{"dataset": "East"}]
    assert record.nodes[root].state[TURNS_STATE_KEY].data == starting_turns
    assert (
        record.nodes[root].state[SYSTEM_PROMPT_STATE_KEY].data == "East prompt"
    )
    assert record.nodes[root].state[VALUES_STATE_KEY].data == {
        "dataset": "East"
    }
    assert VALUES_STATE_KEY not in record.nodes[first].state
    saved_root = (await _saved(backend, record.id)).nodes[root]
    assert saved_root.state == record.nodes[root].state

    # Completing the first response records its changed values on the child,
    # leaving the first-input pair available for an edit/retry rewind.
    live["dataset"] = "response"
    adapter.set_turns_json(
        [*starting_turns, {"role": "assistant", "content": "answer"}]
    )
    await _end_stream(transcript)
    await writer.on_response()
    assert captures == [{"dataset": "East"}, {"dataset": "response"}]
    assert record.nodes[root].state == saved_root.state
    assert record.nodes[first].state[VALUES_STATE_KEY].data == {
        "dataset": "response"
    }

    restored: list[dict[str, Any]] = []
    viewer, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    viewer._restore_callbacks.append(
        lambda values: restored.append(dict(values))
    )
    starting_record = await _saved(backend, record.id)
    starting_record.set_active_leaf(root)
    await replay_exchange_record(viewer, starting_record)
    assert restored == [{"dataset": "East"}]
    assert viewer.adapter.get_turns_json() == starting_turns
    assert viewer.adapter.get_system_prompt() == "East prompt"
    assert not viewer._exchange_recorder.read_only


@pytest.mark.anyio
async def test_failed_root_recapture_keeps_the_previously_valid_starting_base(
    backend: _Backend,
) -> None:
    failing = False

    def capture(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("root recapture failed")
        values["base"] = "known valid"

    writer, _ = _make_controller(store=backend.store, save_callbacks=[capture])
    recorder = writer._exchange_recorder
    recorder.record = new_conversation_record_v2(
        title="manual starting base", client_info={}
    )
    writer.adapter.set_turns_json(
        [{"role": "assistant", "content": "saved SDK base"}]
    )
    assert await recorder.save_current()
    root = recorder.record.root_id
    previous = recorder.record.nodes[root].model_dump_json(
        exclude={"children", "selected_child"}
    )
    failing = True
    writer.adapter.set_turns_json(
        [{"role": "assistant", "content": "later client change"}]
    )
    with pytest.warns(UserWarning, match="root recapture failed"):
        await recorder.accepted_input(
            "first", _stored_message("user", "first input"), lambda: None
        )
    assert (
        recorder.record.nodes[root].model_dump_json(
            exclude={"children", "selected_child"}
        )
        == previous
    )
    assert recorder.record.nodes[root].children == ["first"]
    assert recorder.record.nodes[root].selected_child == "first"
    assert (await _saved(backend, recorder.record.id)).nodes[
        root
    ].model_dump_json(exclude={"children", "selected_child"}) == previous
    assert recorder.record.nodes["first"].checkpoint_state == "candidate"


@pytest.mark.anyio
@pytest.mark.parametrize("seeded", [False, True])
async def test_first_input_onsave_failure_invalidates_the_fresh_root(
    backend: _Backend,
    seeded: bool,
) -> None:
    """A first-input ``on_save`` failure finishes the stateless root invalid.

    The root holds no previously saved frame, so its empty state can never
    serve as a rewind destination: finishing it ``valid`` would let a later
    edit/retry of the first message silently reset the SDK client to ``[]``.
    Atomic staging still holds -- no model-only commit and no partial frame
    -- whether or not the client was seeded with few-shot turns. The first
    exchange keeps its own full model snapshot, so later branches restore
    the seeded client instead of an empty one.
    """
    failing = True

    def capture(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("first-input on_save failed")
        values["dataset"] = "recovered"

    adapter = _prompt_adapter()
    writer, _ = _make_controller(
        store=backend.store, adapter=adapter, save_callbacks=[capture]
    )
    recorder = writer._exchange_recorder
    seed_turns: list[dict[str, Any]] = []
    if seeded:
        seed_turns = [{"role": "assistant", "content": "seeded few-shot turn"}]
        adapter.set_turns_json(seed_turns)
        adapter.set_system_prompt("seeded prompt")

    with pytest.warns(UserWarning, match="first-input on_save failed"):
        transcript, first = await _open_stream(writer)
    record = recorder.record
    assert record is not None
    root = record.root_id
    assert record.nodes[root].status == "ok"
    assert record.nodes[root].checkpoint == "invalid"
    assert record.nodes[root].state == {}
    saved_root = (await _saved(backend, record.id)).nodes[root]
    assert saved_root.status == "ok"
    assert saved_root.checkpoint == "invalid"
    assert saved_root.state == {}

    # Recovery at settlement keeps the first exchange a valid checkpoint
    # holding the full client snapshot (seed turns + question + answer).
    failing = False
    settled_turns = [
        *seed_turns,
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "first answer"},
    ]
    adapter.set_turns_json(settled_turns)
    await _end_stream(transcript)
    await writer.on_response()
    assert record.nodes[first].checkpoint == "valid"
    first_turns = record.nodes[first].state[TURNS_STATE_KEY]
    assert first_turns.mode == "snapshot"
    assert first_turns.data == settled_turns
    assert record.nodes[first].state[VALUES_STATE_KEY].data == {
        "dataset": "recovered"
    }
    # The invalidated root never silently reverts to valid.
    assert (await _saved(backend, record.id)).nodes[root].checkpoint == (
        "invalid"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "stream_status"),
    [("edit", "ok"), ("regenerate", "ok"), ("retry", "cancelled")],
)
async def test_first_input_onsave_failure_refuses_first_message_resubmit(
    backend: _Backend,
    kind: str,
    stream_status: str,
) -> None:
    """The invalid root is no rewind destination for the first message.

    Whatever the first outcome's status, message 1 is not retryable and an
    explicit edit/retry/regenerate is refused server-side at the checkpoint
    gate, before any mutation of the record or the live client turns.
    """
    failing = True

    def capture(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("first-input on_save failed")
        values["dataset"] = "recovered"

    adapter = _prompt_adapter()
    writer, _ = _make_controller(
        store=backend.store, adapter=adapter, save_callbacks=[capture]
    )
    seed_turns = [{"role": "assistant", "content": "seeded few-shot turn"}]
    adapter.set_turns_json(seed_turns)
    adapter.set_system_prompt("seeded prompt")
    with pytest.warns(UserWarning, match="first-input on_save failed"):
        transcript, first = await _open_stream(writer)
    failing = False
    settled_turns = [
        *seed_turns,
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "first answer"},
    ]
    adapter.set_turns_json(settled_turns)
    await _end_stream(transcript, status=stream_status)
    chat = cast(_FakeChat, writer.chat)
    chat.actions.clear()
    await writer.on_response()
    record = writer._exchange_recorder.record
    assert record is not None
    assert record.nodes[first].checkpoint == "valid"
    metadata = [
        action
        for action in chat.actions
        if action["type"] == "update_exchange_metadata"
    ]
    assert metadata[-1]["data"][0] == {
        "status": stream_status,
        "retryable": False,
        "parent_editable": False,
    }
    live_turns = adapter.get_turns_json()
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        await writer.resubmit(
            first, kind=kind, request_id=kind, message_index=0
        )
    # Refusal happened before any rewind or admission: the live client
    # turns are untouched and no input was published to the transcript.
    assert adapter.get_turns_json() == live_turns
    assert chat.published_inputs == []
    assert record.nodes[first].checkpoint == "valid"


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "regenerate"])
async def test_first_input_onsave_failure_branches_message_two_from_the_snapshot(
    backend: _Backend,
    kind: str,
) -> None:
    """Later exchanges still branch from the recovered first snapshot.

    Editing or regenerating message 2 rewinds to exchange 1, restoring the
    seeded client from its full snapshot, and the conversation continues
    from the branched position.
    """
    failing = True

    def capture(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("first-input on_save failed")
        values["dataset"] = "recovered"

    adapter = _prompt_adapter()
    writer, _ = _make_controller(
        store=backend.store, adapter=adapter, save_callbacks=[capture]
    )
    seed_turns = [{"role": "assistant", "content": "seeded few-shot turn"}]
    adapter.set_turns_json(seed_turns)
    adapter.set_system_prompt("seeded prompt")
    with pytest.warns(UserWarning, match="first-input on_save failed"):
        transcript, first = await _open_stream(writer)
    failing = False
    first_turns = [
        *seed_turns,
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "first answer"},
    ]
    adapter.set_turns_json(first_turns)
    await _end_stream(transcript)
    await writer.on_response()
    record = writer._exchange_recorder.record
    assert record is not None
    assert record.nodes[first].checkpoint == "valid"

    # A second exchange settles on the recovered first checkpoint.
    transcript, second = await _open_stream(writer)
    second_turns = [
        *first_turns,
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
    ]
    adapter.set_turns_json(second_turns)
    await _end_stream(transcript)
    await writer.on_response()
    assert record.nodes[second].checkpoint == "valid"

    replacement = (
        _stored_message("user", "edited second question")
        if kind == "edit"
        else None
    )
    await writer.resubmit(
        second, replacement, kind=kind, request_id=kind, message_index=1
    )
    sibling = record.active_leaf
    assert sibling is not None and sibling not in (first, second)
    assert record.nodes[sibling].parent_id == first
    # The rewind restored the seeded client from exchange 1's snapshot,
    # not an empty reset of the SDK client.
    assert adapter.get_turns_json() == first_turns
    assert writer.adapter.get_system_prompt() == "seeded prompt"

    # The branched exchange settles and the conversation continues.
    branched = _wire(writer)
    await _start_stream(branched, sibling)
    await _chunk(branched, _assistant_message(_text("branched answer")))
    await _end_stream(branched)
    await writer.on_response()
    assert record.nodes[sibling].checkpoint == "valid"
    transcript, third = await _open_stream(writer)
    assert record.nodes[third].parent_id == sibling
    adapter.set_turns_json(
        [
            *first_turns,
            {"role": "user", "content": "edited second question"},
            {"role": "assistant", "content": "branched answer"},
            {"role": "user", "content": "third question"},
        ]
    )
    await _end_stream(transcript)
    await writer.on_response()
    assert record.nodes[third].checkpoint == "valid"


@pytest.mark.anyio
@pytest.mark.parametrize("always_failing", [False, True])
async def test_first_input_onsave_failure_reopen_semantics(
    backend: _Backend,
    always_failing: bool,
) -> None:
    """Reopening a first-input ``on_save`` failure stays browsable.

    When only the first capture failed, the recovered first exchange is
    the writable landing position. When every capture fails, the
    unresolved leaf keeps the reopen read-only with reason ``interrupted``.
    """
    captures = 0

    def capture(values: dict[str, Any]) -> None:
        nonlocal captures
        captures += 1
        if always_failing or captures == 1:
            raise RuntimeError("first-input on_save failed")
        values["dataset"] = "recovered"

    adapter = _prompt_adapter()
    writer, _ = _make_controller(
        store=backend.store, adapter=adapter, save_callbacks=[capture]
    )
    seed_turns = [{"role": "assistant", "content": "seeded few-shot turn"}]
    adapter.set_turns_json(seed_turns)
    adapter.set_system_prompt("seeded prompt")
    with pytest.warns(UserWarning, match="first-input on_save failed"):
        transcript, first = await _open_stream(writer)
    settled_turns = [
        *seed_turns,
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "first answer"},
    ]
    adapter.set_turns_json(settled_turns)
    await _end_stream(transcript)
    if always_failing:
        with pytest.warns(UserWarning, match="first-input on_save failed"):
            await writer.on_response()
    else:
        await writer.on_response()
    record = writer._exchange_recorder.record
    assert record is not None
    assert (await _saved(backend, record.id)).nodes[
        record.root_id
    ].checkpoint == "invalid"

    viewer, _ = _make_controller(
        store=backend.reader, adapter=_prompt_adapter()
    )
    await viewer.switch_to(record.id)
    viewer_recorder = viewer._exchange_recorder
    assert viewer_recorder.record is not None
    if always_failing:
        assert viewer_recorder.read_only
        assert viewer_recorder.read_only_reason == "interrupted"
        assert viewer_recorder.source_isolated
    else:
        assert not viewer_recorder.read_only
        assert not viewer_recorder.source_isolated
        assert viewer_recorder.record.active_leaf == first
        assert viewer.adapter.get_turns_json() == settled_turns
        assert viewer.adapter.get_system_prompt() == "seeded prompt"


@pytest.mark.anyio
@pytest.mark.parametrize("first_response", ["stream", "complete"])
async def test_independent_admission_invalidates_prior_candidate_without_app_capture(
    backend: _Backend,
    first_response: str,
) -> None:
    calls: list[str] = []
    writer, _ = _make_controller(
        store=backend.store, save_callbacks=[lambda out: calls.append("app")]
    )
    recorder = writer._exchange_recorder
    if first_response == "stream":
        transcript, node_id = await _open_stream(writer)
        await _end_stream(transcript)
    else:
        from test_history_stream_persistence import _open_input

        transcript, node_id = await _open_input(writer)
        await _complete_append(
            writer, transcript, node_id, "first observed answer"
        )
    record = recorder.record
    assert record is not None
    assert record.nodes[node_id].checkpoint_state == "candidate"
    model_frame = deepcopy(record.nodes[node_id].state)
    outcome = record.nodes[node_id].status
    calls.clear()
    await _complete_append(
        writer, transcript, node_id, "independent observed answer"
    )
    child = record.active_leaf
    assert child is not None and child != node_id
    assert record.nodes[node_id].checkpoint_state == "invalid"
    assert record.nodes[node_id].status == outcome
    assert record.nodes[node_id].state == model_frame
    assert record.nodes[child].checkpoint_state == "candidate"
    assert calls == []
    assert await recorder.response_settled()
    assert calls == ["app"]
    assert record.nodes[child].is_checkpoint
    assert record.nodes[node_id].checkpoint_state == "invalid"
    assert not await recorder.response_settled()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["edit", "retry", "regenerate"])
async def test_live_replay_uses_invalid_input_as_cause_and_only_valid_parent_as_destination(
    kind: str,
) -> None:
    writer, chat, adapter, store, parent, target = (
        _make_v2_resubmit_controller()
    )
    recorder = writer._exchange_recorder
    record = recorder.record
    assert record is not None
    record.nodes[target].checkpoint = "invalid"
    record.nodes[target].status = "error" if kind == "retry" else "ok"
    record.nodes[target].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[
            {
                "role": "assistant",
                "content": "invalid target context must not be restored",
            }
        ],
    )
    await writer.resubmit(target, kind=kind, request_id=kind, message_index=1)
    # The staged resubmission is admitted exactly once, as a new sibling
    # under the valid parent: the invalid target is causal data, never
    # the rewind destination.
    sibling = record.active_leaf
    assert sibling is not None and sibling not in (parent, target)
    assert record.nodes[sibling].parent_id == parent
    assert adapter.turns == [
        {"role": "system", "content": "bootstrap"},
        {"role": "user", "content": "first"},
    ]
    projections = [
        action
        for action in chat.actions
        if action["type"] == "history_edit_projection"
    ]
    assert projections == [
        {
            "type": "history_edit_projection",
            "requestId": kind,
            "index": 1,
            "content": "second",
            "attachments": [],
            "exchange_id": sibling,
        }
    ]
    assert record.nodes[target].checkpoint_state == "invalid"
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        record.require_checkpoint(target)


@pytest.mark.anyio
async def test_trusted_builtin_capture_does_not_recanonicalize_model_payload(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shinychat._history_recorder as module

    writer, _ = _make_controller(store=backend.store, adapter=_prompt_adapter())
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    original = canonical_values
    validations: list[dict[str, Any]] = []

    def capture_values(values: Any) -> dict[str, Any]:
        validations.append(dict(values))
        return original(values)

    monkeypatch.setattr(module, "canonical_values", capture_values)
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            node_id, "node_close", model_only=True
        )
    assert validations == []
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            node_id, "node_close", app_only=True
        )
    assert validations == [
        {}
    ]  # The actual callback values, not an entry wrapper.


@pytest.mark.anyio
async def test_custom_equality_cannot_impersonate_a_trusted_values_hook(
    backend: _Backend,
) -> None:
    writer, _ = _make_controller(store=backend.store)
    transcript, node_id = await _open_stream(writer)
    recorder = writer._exchange_recorder
    external = StateEntry(
        kind="values", version=1, mode="snapshot", data={"list": [1]}
    )
    calls: list[str] = []

    class Custom:  # noqa: PLW1641 - deliberately unhashable, always-equal hook
        def __eq__(self, other: Any) -> bool:
            return True

        def __call__(self, context: Any) -> StateEntry:
            calls.append(context.node_id)
            return external

    recorder._register_capture_hook(VALUES_STATE_KEY, Custom())
    await _end_stream(transcript)
    assert recorder.record is not None
    assert recorder.record.nodes[node_id].checkpoint_state == "candidate"
    assert calls == []
    assert await recorder.response_settled()
    assert calls == [node_id]
    assert isinstance(external.data, dict)
    local = external.data["list"]
    assert isinstance(local, list)
    local.append(2)
    assert recorder.record.nodes[node_id].state[VALUES_STATE_KEY].data == {
        "list": [1]
    }


@pytest.mark.anyio
async def test_isolated_projection_uses_newest_repair_and_preserves_valid_remembered_child(
    backend: _Backend,
) -> None:
    source = _recoverable_tree()
    source.set_active_leaf(source.root_id)
    source.open_exchange("newest", _stored_message("user", "newest"))
    source.finish_exchange("newest", "ok", None)
    source.nodes["newest"].checkpoint = "valid"
    source.nodes["newest"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    source.set_active_leaf(source.root_id)
    source.open_exchange("abandoned", _stored_message("user", "abandoned"))
    viewer, _ = _make_controller(store=backend.reader)
    copy = source.model_copy(deep=True)
    viewer._prepare_exchange_restore(copy)
    assert copy.nodes[source.root_id].selected_child == "newest"
    assert copy.checkpoint_leaf(source.root_id) == "newest"
    source.nodes[source.root_id].selected_child = "valid"
    remembered = source.model_copy(deep=True)
    viewer._prepare_exchange_restore(remembered)
    assert remembered.nodes[source.root_id].selected_child == "valid"
    assert remembered.checkpoint_leaf(source.root_id) == "valid"


@pytest.mark.anyio
@pytest.mark.parametrize("hook_form", ["wrapper", "override"])
async def test_wrapped_and_overridden_captures_are_detached_and_validated(
    hook_form: str,
) -> None:
    from functools import wraps
    from types import MethodType

    from shinychat._history_recorder import _ExchangeRecorder

    writer, _ = _make_controller()
    transcript, node_id = await _open_stream(writer)
    await _end_stream(transcript)
    recorder = writer._exchange_recorder
    external = StateEntry(
        kind="values", version=1, mode="snapshot", data={"items": [1]}
    )

    @wraps(recorder._capture_values)
    def wrapper(context: Any) -> StateEntry:
        return external

    class Override(_ExchangeRecorder):
        def _capture_values(self, context: Any, **kwargs: Any) -> StateEntry:
            return external

    hook = (
        wrapper
        if hook_form == "wrapper"
        else MethodType(Override._capture_values, recorder)
    )
    recorder._register_capture_hook(VALUES_STATE_KEY, hook)
    async with recorder.lock:
        assert await recorder.capture_state_locked(
            node_id, "node_close", app_only=True
        )
    record = recorder.record
    assert record is not None
    assert isinstance(external.data, dict)
    local = external.data["items"]
    assert isinstance(local, list)
    local.append(2)
    assert record.nodes[node_id].state[VALUES_STATE_KEY].data == {"items": [1]}
    before = record.model_dump_json()
    external.data["bad"] = float("nan")
    async with recorder.lock:
        with pytest.raises(ValueError):
            await recorder.capture_state_locked(
                node_id, "node_close", app_only=True
            )
    assert record.model_dump_json() == before


@pytest.mark.anyio
async def test_invalid_settlement_runs_housekeeping_without_success_publication(
    backend: _Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    from test_history_stream_persistence import (
        _assistant_message,
        _chunk,
        _text,
    )

    failing = False

    def save(values: dict[str, Any]) -> None:
        if failing:
            raise RuntimeError("APP capture failed")

    writer, _ = _make_controller(store=backend.store, save_callbacks=[save])
    transcript, first = await _open_stream(writer)
    await _end_stream(transcript)
    await writer.on_response()
    record = writer._exchange_recorder.record
    assert record is not None
    sibling = record.nodes[first].model_copy(deep=True)
    record.nodes["sibling"] = sibling
    record.nodes[record.root_id].children.append("sibling")
    transcript, node_id = await _open_stream(writer)
    older = new_conversation_record_v2(
        title="older", id="older", client_info={}
    )
    await backend.store.put(part(), older)
    writer.adapter.set_turns_json(
        [
            {"role": "user", "content": "input"},
            {"role": "assistant", "content": "large answer" * 1000},
        ]
    )
    await _chunk(transcript, _assistant_message(_text("recoverable answer")))
    await _end_stream(transcript)
    frame = deepcopy(record.nodes[node_id].state)
    metas = await backend.store.list(part())
    writer.max_store_bytes = next(
        m.size_bytes for m in metas if m.id == record.id
    )
    success = AsyncMock()
    retitle = AsyncMock()
    writer.on_response_saved = success
    monkeypatch.setattr(writer, "_schedule_exchange_retitle", retitle)
    siblings = AsyncMock(wraps=writer._send_sibling_metadata)
    monkeypatch.setattr(writer, "_send_sibling_metadata", siblings)
    chat = cast(_FakeChat, writer.chat)
    chat.actions.clear()
    failing = True
    with pytest.warns(UserWarning, match="APP capture failed"):
        await writer.on_response()
    assert await backend.reader.get(part(), older.id) is None
    assert record.response_count == 2
    assert record.nodes[node_id].checkpoint_state == "invalid"
    assert record.nodes[node_id].state == frame
    durable = await _saved(backend, record.id)
    assert durable.response_count == 2
    assert durable.nodes[node_id].state == frame
    assert durable.nodes[node_id].checkpoint_state == "invalid"
    assert (
        durable.nodes[node_id].messages[-1].as_stored_message().content
        == "recoverable answer"
    )
    assert any(a["type"] == "history_update" for a in chat.actions)
    siblings.assert_awaited_once()
    sibling_updates = [
        a for a in chat.actions if a["type"] == "update_siblings"
    ]
    assert sibling_updates == [
        {"type": "update_siblings", "data": {0: {"index": 0, "total": 2}}}
    ]
    success.assert_not_awaited()
    retitle.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["writable", "invalid_parent", "read_only"])
async def test_restored_invalid_ancestor_metadata_and_retained_parent_retry(
    mode: str,
) -> None:
    from shinychat._history_types import HISTORY_ERROR_GENERIC, ErrorEntry

    writer, chat, adapter, store, parent, target = (
        _make_v2_resubmit_controller()
    )
    record = writer._exchange_recorder.record
    assert record is not None
    record.nodes[target].checkpoint = "invalid"
    record.nodes[target].status = "error"
    record.nodes[target].error = ErrorEntry(
        message="secret provider diagnostic"
    )
    descendant = "valid-descendant"
    record.open_exchange(descendant, _stored_message("user", "third"))
    record.nodes[descendant].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "user", "content": "safe descendant"}],
    )
    record.finish_exchange(descendant, "ok", None)
    record.nodes[descendant].checkpoint = "valid"
    if mode == "invalid_parent":
        record.nodes[parent].checkpoint = "invalid"
    from shinychat._history_store import InMemoryConversationStore

    store = InMemoryConversationStore()
    writer.store = store
    await store.put(part(), record)
    writer._exchange_recorder.record = None
    writer._active_id.set(None)
    await writer.switch_to(record.id)
    restored = writer._exchange_recorder.record
    assert restored is not None
    assert not writer._exchange_recorder.read_only
    if mode == "read_only":
        writer._exchange_recorder.install_restored_record(
            restored, read_only=True
        )
    chat.actions.clear()
    await writer._send_exchange_metadata()
    metadata = chat.actions[-1]["data"]
    assert metadata[1] == {
        "status": "error",
        "error_message": HISTORY_ERROR_GENERIC,
        "retryable": mode == "writable",
        "parent_editable": mode != "invalid_parent",
    }
    with pytest.raises(ValueError, match="not a valid checkpoint"):
        restored.require_checkpoint(target)
    if mode == "writable":
        await writer.resubmit(
            target, kind="retry", request_id="retry", message_index=1
        )
        # The staged retry is admitted exactly once, as a new sibling
        # under the valid parent.
        sibling = restored.active_leaf
        assert sibling is not None and sibling not in (parent, target)
        assert restored.nodes[sibling].parent_id == parent
        assert adapter.turns == [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "first"},
        ]
    else:
        with pytest.raises((ValueError, RuntimeError)):
            await writer.resubmit(
                target, kind="retry", request_id="retry", message_index=1
            )
