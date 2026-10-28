from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shinychat._history_controller import HistoryController
from shinychat._history_types import (
    ConversationNode,
    ConversationRecordV1,
    ConversationRecordV2,
    utcnow,
)


def branch_from(
    record: ConversationRecordV1,
    fork_parent_id: str | None,
    turns: list[dict[str, Any]],
    ui: list[dict[str, Any]] | None = None,
) -> str:
    """Create a sibling node directly on a v1 `record` for fixtures.

    Production v1 code never branched this way, and the v2 exchange tree
    branches through resubmit/open_exchange instead. This exists solely to
    build branched v1 fixtures for tests.
    """
    node_id = f"n_{record.next_node_seq:04d}"
    record.next_node_seq += 1
    record.nodes[node_id] = ConversationNode(
        parent=fork_parent_id, turns=turns, ui=ui
    )
    if fork_parent_id is not None:
        record.nodes[fork_parent_id].children.append(node_id)
    record.current_leaf = node_id
    record.updated_at = utcnow()
    return node_id


async def replay_exchange_record(
    controller: HistoryController,
    record: ConversationRecordV2 | None = None,
) -> None:
    """Replay an exchange-tree record through the controller's restore path.

    Defaults to the recorder's live record; a no-op when there is none.
    """
    recorder = controller._exchange_recorder
    target = recorder.record if record is None else record
    if target is None:
        return
    node_ids, planned_state, bootstrap = controller._prepare_exchange_restore(
        target
    )
    async with controller._destructive_mutation():
        async with controller._exchange_mutation():
            await controller._restore_exchange_record_locked(
                target,
                node_ids=node_ids,
                planned_state=planned_state,
                bootstrap=bootstrap,
            )
