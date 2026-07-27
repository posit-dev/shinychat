from typing import Any

from shinychat._history_types import (
    ConversationNode,
    ConversationRecord,
    utcnow,
)


def branch_from(
    record: ConversationRecord,
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
