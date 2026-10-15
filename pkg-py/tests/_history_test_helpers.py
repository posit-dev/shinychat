from typing import Any

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
    """Create a sibling node directly on `record`, bypassing the normal
    append-linear path.

    Production code never branches this way -- `HistoryController.handle_edit`
    achieves branching indirectly by truncating `current_leaf` and letting the
    next `append_linear` (from the resubmit's `on_response`) create the
    sibling. This exists solely to build branched fixtures for tests.
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
    """Replay an exchange-tree record through the production restore path.

    The controller once exposed this as a public method, but nothing in
    production ever called it -- every restore goes through either the
    initial-restore entry (bookmark/session boot) or `switch_to` -- so
    phase 5.8 (D9) deleted it rather than keep a test-only bypass on the
    public surface. Tests call this helper, which drives the same
    production `_restore_exchange_record` entry the deleted method used.
    """
    recorder = controller._exchange_recorder
    target = recorder.record if record is None else record
    if target is not None:
        await controller._restore_exchange_record(target)
