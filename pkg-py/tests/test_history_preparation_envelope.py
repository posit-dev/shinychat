"""Round-trip proof for failure metadata in the existing StateEntry envelope.

This fixture deliberately uses only baseline model/controller APIs. The same
cases were exercised against unchanged e4f2021e before implementing admission.
"""

import json
from pathlib import Path
from typing import Literal

import pytest
from _history_test_helpers import replay_exchange_record
from shinychat._history_store import (
    ConversationPartition,
    ConversationStore,
    FileConversationStore,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    ConversationMeta,
    ConversationRecordV1,
    ConversationRecordV2,
    StateEntry,
    new_conversation_record_v2,
)
from test_history_controller import _make_controller, _stored_message, part

PREPARATION_KEY = "shinychat:preparation"
PREPARATION_ENTRY = StateEntry(
    kind="input_preparation",
    version=1,
    mode="snapshot",
    data={"terminal": True, "accepted": False, "app_values": "unavailable"},
)


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
def envelope_store(
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
        id="c_envelope", title="Original", client_info={}
    )
    root_id = record.root_id
    record.nodes[root_id].state["shinychat:turns"] = StateEntry(
        kind="turns", version=1, mode="snapshot", data=[]
    )
    record.nodes[root_id].state["shinychat:values"] = StateEntry(
        kind="values", version=1, mode="snapshot", data={"region": "all"}
    )
    record.open_exchange("original", _stored_message("user", "B"))
    record.finish_exchange("original", "ok", None)
    record.nodes["original"].checkpoint = "valid"
    record.open_exchange("descendant", _stored_message("user", "C"))
    record.finish_exchange("descendant", "ok", None)
    record.nodes["descendant"].checkpoint = "valid"
    record.set_active_leaf(root_id)
    record.open_exchange("failed", _stored_message("user", "B-prime"))
    record.finish_exchange("failed", "error", "Message not sent.")
    record.nodes["failed"].checkpoint = "invalid"
    record.nodes["failed"].state[PREPARATION_KEY] = (
        PREPARATION_ENTRY.model_copy(deep=True)
    )
    record.set_active_leaf("descendant")
    return record


@pytest.mark.anyio
async def test_controller_rewrite_keeps_failed_sibling_envelope(
    envelope_store: ConversationStore,
) -> None:
    original = _record_with_failed_sibling()
    await envelope_store.put(part(), original)
    loaded = await envelope_store.get(part(), original.id)
    assert isinstance(loaded, ConversationRecordV2)
    controller, _ = _make_controller(store=envelope_store)
    await replay_exchange_record(controller, loaded)

    await controller.rename(original.id, "Renamed")
    assert await controller.save_current()

    rewritten = await envelope_store.get(part(), original.id)
    assert isinstance(rewritten, ConversationRecordV2)
    assert rewritten.title == "Renamed"
    assert rewritten.active_leaf == "descendant"
    assert rewritten.nodes["failed"].state[PREPARATION_KEY] == (
        PREPARATION_ENTRY
    )
    assert rewritten.nodes["failed"].input == original.nodes["failed"].input
    assert rewritten.nodes["failed"].checkpoint == "invalid"
    assert rewritten.nodes["original"].children == ["descendant"]
    assert rewritten.nodes["descendant"].input == (
        original.nodes["descendant"].input
    )
    assert not controller._exchange_recorder.source_isolated
