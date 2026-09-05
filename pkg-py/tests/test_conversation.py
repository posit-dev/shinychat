from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import chatlas
import pytest
from shiny.session import get_current_session
from shinychat import Conversation
from shinychat._history_store import InMemoryConversationStore
from shinychat._history_types import new_conversation_record
from shinychat.types import ConversationPartition, FileConversationStore


class TurnsClient:
    def __init__(self) -> None:
        self.turns: list[Any] = [
            {"role": "system", "content": "Initial instructions"}
        ]

    def get_turns(self) -> list[Any]:
        return copy.deepcopy(self.turns)

    def set_turns(self, turns: list[Any]) -> None:
        self.turns = copy.deepcopy(turns)


@pytest.fixture(params=["memory", "file"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    return (
        InMemoryConversationStore()
        if request.param == "memory"
        else FileConversationStore(tmp_path)
    )


PARTITION = ConversationPartition(chat_id="module-chat", scope="alice")


@pytest.mark.anyio
async def test_branch_compaction_preserves_display_and_original_turns(store):
    assert get_current_session() is None
    client = TurnsClient()
    conversation = await Conversation.create(store, PARTITION, client=client)
    root = conversation.active_leaf
    async with conversation.exchange("Original question") as original:
        client.turns += [{"role": "user", "content": "Original question"}]
        client.turns += [{"role": "assistant", "content": "Provider answer"}]
        await conversation.append_message("Display answer, with **formatting**")
    original_turns = client.get_turns()
    before = await store.get(PARTITION, conversation.id)

    await conversation.select(root)
    async with conversation.exchange("Alternative question") as alternative:
        client.turns = [{"role": "system", "content": "Compacted instructions"}]
        client.turns += [{"role": "user", "content": "Alternative question"}]
        await conversation.append_message("Alternative display")
    conversation.values["deputy"] = {"version": 1, "run_id": "run-123"}
    await conversation.save()

    restored_client = TurnsClient()
    restored = await Conversation.load(
        store, PARTITION, conversation.id, client=restored_client
    )
    assert restored_client.get_turns() == client.get_turns()
    assert restored.active_leaf == alternative
    assert restored.values == {"deputy": {"version": 1, "run_id": "run-123"}}
    record = await store.get(PARTITION, conversation.id)
    assert record.nodes[original] == before.nodes[original]
    assert record.nodes[alternative].state["shinychat:turns"].mode == "snapshot"
    assert record.nodes[root].children == [original, alternative]

    await restored.select(original)
    assert restored_client.get_turns() == original_turns
    assert (await store.get(PARTITION, conversation.id)).active_leaf == original
    assert record.nodes[original].messages[0].segments[0].content == (
        "Display answer, with **formatting**"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["ok", "error", "cancelled"])
async def test_checkpoints_and_terminal_outcomes(store, outcome: str):
    client = TurnsClient()
    conversation = await Conversation.create(store, PARTITION, client=client)
    failure = (
        asyncio.CancelledError()
        if outcome == "cancelled"
        else RuntimeError("secret")
    )

    async def run():
        async with conversation.exchange("Question") as exchange_id:
            pending = await store.get(PARTITION, conversation.id)
            assert pending.nodes[exchange_id].status == "pending"
            assert pending.nodes[exchange_id].input.content == "Question"
            await conversation.append_message("Partial output")
            partial = await store.get(PARTITION, conversation.id)
            assert partial.nodes[exchange_id].status == "pending"
            assert partial.nodes[exchange_id].messages[0].segments[
                0
            ].content == ("Partial output")
            client.turns.append({"role": "user", "content": "Question"})
            if outcome != "ok":
                raise failure

    if outcome == "ok":
        await run()
    else:
        with pytest.raises(type(failure)) as caught:
            await run()
        assert caught.value is failure
    record = await store.get(PARTITION, conversation.id)
    node = record.nodes[conversation.active_leaf]
    assert node.status == outcome
    assert len(node.messages) == 1
    assert node.state["shinychat:turns"].data == [
        {"role": "user", "content": "Question"}
    ]
    assert "secret" not in record.model_dump_json()


@pytest.mark.anyio
async def test_chatlas_system_prompt_and_turns_round_trip(store):
    client = chatlas.ChatOpenAI(
        model="test-model",
        api_key="unused",
        system_prompt="System instructions",
    )
    conversation = await Conversation.create(store, PARTITION, client=client)
    async with conversation.exchange("Question"):
        client.set_turns(
            [
                *client.get_turns(),
                chatlas.Turn(role="user", contents="Question"),
                chatlas.Turn(role="assistant", contents="Answer"),
            ]
        )
        await conversation.append_message("An independent display")

    restored_client = chatlas.ChatOpenAI(model="test-model", api_key="unused")
    await Conversation.load(
        store, PARTITION, conversation.id, client=restored_client
    )
    assert [
        turn.model_dump(mode="json", exclude_none=True)
        for turn in restored_client.get_turns(include_system_prompt=True)
    ] == [
        turn.model_dump(mode="json", exclude_none=True)
        for turn in client.get_turns(include_system_prompt=True)
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "partition",
    [
        ConversationPartition(chat_id="module-chat", scope="bob"),
        ConversationPartition(chat_id="other-chat", scope="alice"),
    ],
)
async def test_partition_is_required_for_load_and_list(store, partition):
    conversation = await Conversation.create(
        store, PARTITION, client=TurnsClient()
    )
    assert [meta.id for meta in await store.list(PARTITION)] == [
        conversation.id
    ]
    assert await store.list(partition) == []
    with pytest.raises(ValueError, match="was not found"):
        await Conversation.load(
            store, partition, conversation.id, client=TurnsClient()
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "damage", ["id", "path", "state", "provider", "version"]
)
async def test_restore_rejects_invalid_history_before_changing_client(
    store, damage
):
    source = await Conversation.create(store, PARTITION, client=TurnsClient())
    record = await store.get(PARTITION, source.id)
    if damage == "id":
        # A custom store can return a record for the wrong requested ID.
        requested_id = "different-id"
    else:
        requested_id = source.id
    if damage == "path":
        record.nodes[record.active_leaf].parent_id = "missing-parent"
    elif damage == "state":
        record.nodes[record.active_leaf].state[
            "shinychat:turns"
        ].data = "not turns"
    elif damage == "provider":
        record.nodes[record.active_leaf].state["shinychat:turns"].version = 99
    elif damage == "version":
        record = new_conversation_record(title="Legacy", id=source.id)

    class LoadedStore(InMemoryConversationStore):
        async def get(self, partition, conv_id):
            return record

    client = TurnsClient()
    client.turns = [{"role": "user", "content": "Keep these turns"}]
    before = client.get_turns()
    with pytest.raises(ValueError):
        await Conversation.load(
            LoadedStore(), PARTITION, requested_id, client=client
        )
    assert client.get_turns() == before


@pytest.mark.anyio
async def test_invalid_selection_and_overlapping_exchange_do_not_change_branch(
    store,
):
    client = TurnsClient()
    conversation = await Conversation.create(store, PARTITION, client=client)
    root = conversation.active_leaf
    with pytest.raises(ValueError, match="Unknown exchange"):
        await conversation.select("unknown")
    assert conversation.active_leaf == root
    async with conversation.exchange("Question") as exchange_id:
        with pytest.raises(RuntimeError, match="already in progress"):
            await conversation.select(root)
        with pytest.raises(RuntimeError, match="already in progress"):
            async with conversation.exchange("Nested"):
                pytest.fail("nested exchange was accepted")
        assert conversation.active_leaf == exchange_id
    with pytest.raises(RuntimeError, match="requires an exchange"):
        await conversation.append_message("Late output")


@pytest.mark.anyio
async def test_unsaved_or_invalid_values_cannot_mutate_store(store):
    conversation = await Conversation.create(
        store, PARTITION, client=TurnsClient()
    )
    conversation.values["run"] = {"version": 1, "id": "unsaved"}
    assert (await store.get(PARTITION, conversation.id)).values == {}
    conversation.values["invalid"] = float("nan")
    with pytest.raises(ValueError):
        await conversation.save()
    assert (await store.get(PARTITION, conversation.id)).values == {}


@pytest.mark.anyio
async def test_input_save_failure_prevents_worker_execution():
    class FailingStore(InMemoryConversationStore):
        fail = False

        async def put(self, partition, record):
            if self.fail:
                raise OSError("disk unavailable")
            await super().put(partition, record)

    store = FailingStore()
    conversation = await Conversation.create(
        store, PARTITION, client=TurnsClient()
    )
    root = conversation.active_leaf
    store.fail = True
    with pytest.raises(OSError, match="disk unavailable"):
        async with conversation.exchange("Never submitted"):
            pytest.fail("work began before input was persisted")
    assert conversation.active_leaf == root
    store.fail = False
    async with conversation.exchange("Try again"):
        await conversation.append_message("Answer")
    record = await store.get(PARTITION, conversation.id)
    assert len(record.nodes) == 2
    assert "Never submitted" not in record.model_dump_json()


@pytest.mark.anyio
async def test_capture_failure_preserves_output_and_propagates_original_error(
    store,
):
    client = TurnsClient()
    conversation = await Conversation.create(store, PARTITION, client=client)
    error = RuntimeError("model failed")
    with pytest.raises(RuntimeError) as caught:
        async with conversation.exchange("Question"):
            await conversation.append_message("Partial output")
            client.turns.append({"invalid": object()})
            raise error
    assert caught.value is error
    assert isinstance(caught.value.__cause__, TypeError)
    record = await store.get(PARTITION, conversation.id)
    node = record.nodes[conversation.active_leaf]
    assert node.status == "error"
    assert node.messages[0].segments[0].content == "Partial output"


@pytest.mark.anyio
async def test_capture_failure_cannot_mark_an_exchange_completed(store):
    client = TurnsClient()
    conversation = await Conversation.create(store, PARTITION, client=client)
    with pytest.raises(TypeError):
        async with conversation.exchange("Question"):
            await conversation.append_message("Output before capture failed")
            client.turns.append({"invalid": object()})
    record = await store.get(PARTITION, conversation.id)
    assert record.nodes[conversation.active_leaf].status == "error"
