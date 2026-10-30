"""New-reader round trip for failed-position fields and unknown state fields.

A terminal rejected input records its availability on the exchange node
(``not_sent`` and ``app_values``) and owns a values snapshot. Fields
written by a newer writer on a state entry must survive a controller
read/modify/write on every store backend, including explicit nulls, even when
``save_current`` recaptures and replaces that entry.
"""

import json
from pathlib import Path
from typing import Any, Literal

import pytest
from _history_test_helpers import replay_exchange_record
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
    ConversationMeta,
    ConversationRecordV1,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_controller import (
    _FakeAdapter,
    _make_controller,
    _stored_message,
    part,
)

# Written by a newer writer; the current reader must not drop them. The null
# value is deliberate: explicit nulls are state, not absent fields.
FUTURE_FIELDS: dict[str, Any] = {"future_flag": None, "future_note": "kept"}
# Nested values are copied, not shared, when an entry is replaced.
NESTED_FIELDS: dict[str, Any] = {"future_nested": {"tags": [None, {"k": 1}]}}
UNKNOWN_FIELDS: dict[str, Any] = {**FUTURE_FIELDS, **NESTED_FIELDS}


class _JSONStore(ConversationStore):
    """A custom backend that round-trips whole records through the v2 model."""

    def __init__(self) -> None:
        self.records: dict[tuple[ConversationPartition, str], str] = {}

    def _decode(self, raw: str) -> ConversationRecordV1 | ConversationRecordV2:
        data = json.loads(raw)
        if data.get("schema_version", 1) == 1:
            return ConversationRecordV1.model_validate(data)
        return ConversationRecordV2.model_validate(data)

    async def list(
        self, partition: ConversationPartition
    ) -> list[ConversationMeta]:
        metadata = [
            self._decode(raw).meta(size_bytes=len(raw.encode("utf-8")))
            for (stored_partition, _), raw in self.records.items()
            if stored_partition == partition
        ]
        return sorted(metadata, key=lambda item: item.created_at, reverse=True)

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecordV1 | ConversationRecordV2 | None:
        raw = self.records.get((partition, conv_id))
        return None if raw is None else self._decode(raw)

    async def put(
        self,
        partition: ConversationPartition,
        record: ConversationRecordV1 | ConversationRecordV2,
    ) -> None:
        self.records[(partition, record.id)] = record.model_dump_json(
            exclude_none=True
        )

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self.records.pop((partition, conv_id), None)


@pytest.fixture(params=["file", "memory", "custom-json"])
def unknown_fields_store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> ConversationStore:
    backend: Literal["file", "memory", "custom-json"] = request.param
    if backend == "file":
        return FileConversationStore(dir=tmp_path)
    if backend == "memory":
        return InMemoryConversationStore()
    return _JSONStore()


def _record_with_failed_sibling() -> ConversationRecordV2:
    record = new_conversation_record_v2(
        id="c_unknown_fields", title="Original", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.nodes[root_id].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"region": "all"}
    )
    record.open_exchange("original", _stored_message("user", "B"))
    record.finish_exchange("original", "ok", None)
    record.nodes["original"].checkpoint = "valid"
    record.open_exchange("descendant", _stored_message("user", "C"))
    record.finish_exchange("descendant", "ok", None)
    record.nodes["descendant"].checkpoint = "valid"
    # The active leaf's turns entry is recaptured by save_current, so the
    # unknown fields sit on an entry the controller replaces on write.
    record.nodes["descendant"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[],
        **FUTURE_FIELDS,
    )
    record.set_active_leaf(root_id)
    record.open_exchange("failed", _stored_message("user", "B-prime"))
    record.finish_exchange("failed", "error", "Message not sent.")
    record.nodes["failed"].checkpoint = "invalid"
    record.nodes["failed"].not_sent = True
    record.nodes["failed"].app_values = "unavailable"
    record.nodes["failed"].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={}
    )
    record.set_active_leaf("descendant")
    return record


@pytest.mark.anyio
async def test_controller_rewrite_preserves_new_reader_unknown_fields(
    unknown_fields_store: ConversationStore,
) -> None:
    original = _record_with_failed_sibling()
    await unknown_fields_store.put(part(), original)
    loaded = await unknown_fields_store.get(part(), original.id)
    assert isinstance(loaded, ConversationRecordV2)
    controller, _ = _make_controller(store=unknown_fields_store)
    await replay_exchange_record(controller, loaded)

    await controller.rename(original.id, "Renamed")
    assert await controller.save_current()

    rewritten = await unknown_fields_store.get(part(), original.id)
    assert isinstance(rewritten, ConversationRecordV2)
    assert rewritten.title == "Renamed"
    assert rewritten.active_leaf == "descendant"
    # The replaced, recaptured entry keeps its unknown fields, nulls included.
    replaced = rewritten.nodes["descendant"].state[TURNS_STATE_KEY]
    assert replaced.model_extra == FUTURE_FIELDS
    assert replaced.model_dump()["future_flag"] is None
    # The failed sibling's node fields and own values snapshot are untouched.
    failed = rewritten.nodes["failed"]
    assert failed.not_sent is True
    assert failed.app_values == "unavailable"
    assert failed.state[VALUES_STATE_KEY] == StateEntry(
        kind="values", version=1, mode="snapshot", data={}
    )
    assert failed.input == original.nodes["failed"].input
    assert failed.checkpoint == "invalid"
    assert rewritten.nodes["original"].children == ["descendant"]
    assert rewritten.nodes["descendant"].input == (
        original.nodes["descendant"].input
    )
    assert not controller._exchange_recorder.source_isolated


def _values_chain_record() -> ConversationRecordV2:
    record = new_conversation_record_v2(
        id="c_values_sparse", title="Values", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.nodes[root_id].state[VALUES_STATE_KEY] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"region": "all"}
    )
    record.open_exchange("child", _stored_message("user", "B"))
    record.finish_exchange("child", "ok", None)
    record.nodes["child"].checkpoint = "valid"
    record.nodes["child"].state[VALUES_STATE_KEY] = StateEntry(
        kind="values",
        version=1,
        mode="snapshot",
        data={"region": "north"},
        **UNKNOWN_FIELDS,
    )
    record.set_active_leaf("child")
    return record


@pytest.mark.anyio
async def test_values_recapture_matching_ancestor_keeps_unknown_fields(
    unknown_fields_store: ConversationStore,
) -> None:
    # The live app now matches the root's value, so sparse capture would
    # inherit and drop the child's entry. Its unknown fields must keep the
    # entry alive instead, with the explicit nulls and nested values intact.
    original = _values_chain_record()
    await unknown_fields_store.put(part(), original)
    loaded = await unknown_fields_store.get(part(), original.id)
    assert isinstance(loaded, ConversationRecordV2)
    current: dict[str, Any] = {"region": "all"}
    controller, _ = _make_controller(
        store=unknown_fields_store,
        save_callbacks=[lambda values: values.update(current)],
    )
    await replay_exchange_record(controller, loaded)

    assert await controller.save_current()

    rewritten = await unknown_fields_store.get(part(), original.id)
    assert isinstance(rewritten, ConversationRecordV2)
    assert rewritten.active_leaf == "child"
    assert VALUES_STATE_KEY in rewritten.nodes["child"].state
    child = rewritten.nodes["child"].state[VALUES_STATE_KEY]
    assert child.data == {"region": "all"}
    assert child.model_extra == UNKNOWN_FIELDS
    assert child.model_dump()["future_flag"] is None
    assert rewritten.nodes[rewritten.root_id].state[VALUES_STATE_KEY].data == {
        "region": "all"
    }


def _turns_chain_record() -> ConversationRecordV2:
    record = new_conversation_record_v2(
        id="c_turn_pin", title="Turns", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="snapshot",
        data=[{"role": "system", "content": "s"}],
    )
    record.open_exchange("parent", _stored_message("user", "a"))
    record.finish_exchange("parent", "ok", None)
    record.nodes["parent"].checkpoint = "valid"
    record.nodes["parent"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "a"}],
    )
    record.open_exchange("child", _stored_message("user", "c1"))
    record.finish_exchange("child", "ok", None)
    record.nodes["child"].checkpoint = "valid"
    record.nodes["child"].state[TURNS_STATE_KEY] = StateEntry(
        kind="turns",
        version=1,
        mode="delta",
        data=[{"role": "user", "content": "c1"}],
        **UNKNOWN_FIELDS,
    )
    record.set_active_leaf("parent")
    return record


@pytest.mark.anyio
async def test_turn_pin_of_child_keeps_unknown_fields_after_parent_recapture(
    unknown_fields_store: ConversationStore,
) -> None:
    # Recapturing the parent's rewritten turns pins its delta child to a
    # snapshot. The pinned replacement entry must keep the child's unknown
    # fields, nulls and nested values included.
    original = _turns_chain_record()
    await unknown_fields_store.put(part(), original)
    loaded = await unknown_fields_store.get(part(), original.id)
    assert isinstance(loaded, ConversationRecordV2)
    adapter = _FakeAdapter()
    controller, _ = _make_controller(
        store=unknown_fields_store, adapter=adapter
    )
    await replay_exchange_record(controller, loaded)
    adapter.turns = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a rewritten"},
    ]

    assert await controller.save_current()

    rewritten = await unknown_fields_store.get(part(), original.id)
    assert isinstance(rewritten, ConversationRecordV2)
    parent_entry = rewritten.nodes["parent"].state[TURNS_STATE_KEY]
    assert parent_entry.data == [{"role": "user", "content": "a rewritten"}]
    pinned = rewritten.nodes["child"].state[TURNS_STATE_KEY]
    assert pinned.mode == "snapshot"
    assert pinned.data == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "c1"},
    ]
    assert pinned.model_extra == UNKNOWN_FIELDS
    assert pinned.model_dump()["future_flag"] is None
