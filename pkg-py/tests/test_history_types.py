import pytest
from shinychat._history_types import (
    ConversationMeta,
    ConversationNode,
    ConversationRecord,
    new_conversation_record,
)


def turn(role: str, content: str) -> list[dict[str, object]]:
    return [{"role": role, "content": content}]


def test_new_record_is_empty_draft():
    rec = new_conversation_record(title="hello world")
    assert rec.schema_version == 1
    assert rec.id.startswith("c_")
    assert rec.nodes == {}
    assert rec.current_leaf is None
    assert rec.path_turns() == []
    assert rec.title == "hello world"
    assert rec.title_source is None
    assert rec.response_count == 0


def test_append_linear_builds_chain():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(
        turn("assistant", "hello"), ui=[{"role": "assistant"}]
    )
    assert rec.nodes[n1].parent is None
    assert rec.nodes[n2].parent == n1
    assert rec.current_leaf == n2
    assert rec.nodes[n2].ui == [{"role": "assistant"}]
    assert [t["role"] for t in rec.path_turns()] == ["user", "assistant"]
    assert rec.updated_at >= rec.created_at


def test_path_follows_current_leaf_not_all_nodes():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "v1"))
    sibling = ConversationNode(parent=n1, turns=turn("assistant", "v2"))
    rec.nodes["n_sib"] = sibling
    rec.current_leaf = "n_sib"
    assert [t["content"] for t in rec.path_turns()] == ["hi", "v2"]


def test_json_round_trip():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "hi"))
    rec2 = ConversationRecord.model_validate_json(rec.model_dump_json())
    assert rec2 == rec


def test_meta_method():
    rec = new_conversation_record(title="t")
    meta = rec.meta(size_bytes=123)
    assert isinstance(meta, ConversationMeta)
    assert (meta.id, meta.title) == (rec.id, rec.title)
    assert meta.created_at == rec.created_at
    assert meta.updated_at == rec.updated_at
    assert meta.size_bytes == 123


def test_path_node_ids_raises_on_cycle():
    rec = new_conversation_record(title="cycle test")
    rec.nodes["n_a"] = ConversationNode(parent="n_b", turns=turn("user", "a"))
    rec.nodes["n_b"] = ConversationNode(
        parent="n_a", turns=turn("assistant", "b")
    )
    rec.current_leaf = "n_b"
    with pytest.raises(ValueError, match="Cycle"):
        rec.path_node_ids()


def test_path_node_ids_raises_on_dangling_parent():
    rec = new_conversation_record(title="dangling test")
    rec.nodes["n_a"] = ConversationNode(
        parent="n_missing", turns=turn("user", "a")
    )
    rec.current_leaf = "n_a"
    with pytest.raises(ValueError, match="Dangling parent"):
        rec.path_node_ids()


def test_append_linear_collision_safe():
    rec = new_conversation_record(title="collision test")
    rec.nodes["n_0005"] = ConversationNode(
        parent=None, turns=turn("user", "pre-inserted")
    )
    rec.current_leaf = "n_0005"
    rec.next_node_seq = 6  # skip past the manually-inserted node
    new_id = rec.append_linear(turn("assistant", "reply"))
    assert new_id == "n_0006"
    assert rec.nodes["n_0005"].turns[0]["content"] == "pre-inserted"
    assert rec.nodes["n_0005"].children == ["n_0006"]


def test_bookmark_state_id_round_trips():
    rec = new_conversation_record(title="t")
    rec.bookmark_state_id = "abc123"
    raw = rec.model_dump(mode="json")
    loaded = ConversationRecord.model_validate(raw)
    assert loaded.bookmark_state_id == "abc123"


def test_append_linear_populates_children():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "hello"))
    n3 = rec.append_linear(turn("user", "follow-up"))
    assert rec.nodes[n1].children == [n2]
    assert rec.nodes[n2].children == [n3]
    assert rec.nodes[n3].children == []


def test_next_node_seq_increments():
    rec = new_conversation_record(title="t")
    assert rec.next_node_seq == 1
    rec.append_linear(turn("user", "hi"))
    assert rec.next_node_seq == 2
    rec.append_linear(turn("assistant", "hello"))
    assert rec.next_node_seq == 3


def test_next_node_seq_never_reuses_ids():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "hello"))
    # Simulate deleting a node (future branch pruning)
    del rec.nodes[n2]
    rec.current_leaf = n1
    rec.nodes[n1].children.clear()
    # next_node_seq should still be 3, not reuse n_0002
    n3 = rec.append_linear(turn("assistant", "v2"))
    assert n3 == "n_0003"
    assert rec.next_node_seq == 4


def test_children_round_trip_json():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "hello"))
    rec2 = ConversationRecord.model_validate_json(rec.model_dump_json())
    for nid in rec.nodes:
        assert rec2.nodes[nid].children == rec.nodes[nid].children
    assert rec2.next_node_seq == rec.next_node_seq


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def test_children_of_returns_direct_children_sorted():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "hey"))
    assert rec.children_of(None) == [n1]
    assert rec.children_of(n1) == [n2]
    assert rec.children_of(n2) == []


def test_children_of_with_branch():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.branch_from(n1, turn("assistant", "v2"))
    assert rec.children_of(n1) == [n2, n3]


def test_siblings_of():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.branch_from(n1, turn("assistant", "v2"))
    assert rec.siblings_of(n2) == [n2, n3]
    assert rec.siblings_of(n3) == [n2, n3]
    # n1 has no siblings (only child of root)
    assert rec.siblings_of(n1) == [n1]


def test_subtree_leaf_returns_self_for_leaf_node():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    assert rec.subtree_leaf(n1) == n1


def test_subtree_leaf_follows_latest_child():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.append_linear(turn("user", "q2"))
    n4 = rec.append_linear(turn("assistant", "a2"))
    # Subtree from n1 follows n2 -> n3 -> n4
    assert rec.subtree_leaf(n1) == n4
    # Add a branch at n2 (sibling of n3)
    n5 = rec.branch_from(n2, turn("user", "q2-edited"))
    n6 = rec.branch_from(n5, turn("assistant", "a2-new"))
    # subtree_leaf from n2 follows the LATEST child (n5) -> n6
    assert rec.subtree_leaf(n2) == n6
    # subtree_leaf from n3 still follows n4
    assert rec.subtree_leaf(n3) == n4


def test_branch_from_creates_sibling():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.branch_from(n1, turn("assistant", "v2"))
    assert rec.nodes[n3].parent == n1
    assert rec.current_leaf == n3
    assert rec.children_of(n1) == [n2, n3]
    assert rec.path_turns() == turn("user", "hi") + turn("assistant", "v2")


def test_branch_from_root():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "v1"))
    n3 = rec.branch_from(None, turn("user", "bye"))
    assert rec.nodes[n3].parent is None
    assert rec.current_leaf == n3
    assert rec.children_of(None) == [n1, n3]


def test_branch_from_preserves_old_branch():
    rec = new_conversation_record(title="t")
    _ = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.append_linear(turn("user", "q2"))
    n4 = rec.append_linear(turn("assistant", "a2"))
    # Branch: edit q2 -> creates sibling of n3
    n5 = rec.branch_from(n2, turn("user", "q2-edited"))
    # Old branch is intact
    assert rec.nodes[n3].parent == n2
    assert rec.nodes[n4].parent == n3
    # New branch is active
    assert rec.current_leaf == n5
    assert rec.path_turns() == (
        turn("user", "hi")
        + turn("assistant", "v1")
        + turn("user", "q2-edited")
    )


def test_node_id_for_message_index_simple():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"), ui=[msg("user")])
    n2 = rec.append_linear(turn("assistant", "a"), ui=[msg("assistant")])
    assert rec.node_id_for_message_index(0) == (n1, 0)
    assert rec.node_id_for_message_index(1) == (n2, 1)


def test_node_id_for_message_index_skips_empty_ui_nodes():
    # Simulates tool-call turns with no UI
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"), ui=[msg("user")])
    rec.append_linear(turn("assistant", "tool_call"))  # no ui
    rec.append_linear(turn("user", "tool_result"))  # no ui
    n4 = rec.append_linear(turn("assistant", "a"), ui=[msg("assistant")])
    assert rec.node_id_for_message_index(0) == (n1, 0)
    # Message index 1 -> n4 (node index 3, skipping 2 empty-ui nodes)
    assert rec.node_id_for_message_index(1) == (n4, 3)


def test_node_id_for_message_index_out_of_range():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "q"), ui=[msg("user")])
    with pytest.raises(IndexError):
        rec.node_id_for_message_index(1)


def test_node_id_for_message_index_negative_is_out_of_range():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "q"), ui=[msg("user")])
    with pytest.raises(IndexError):
        rec.node_id_for_message_index(-1)


def test_node_id_for_message_index_multi_ui_node():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"), ui=[msg("user")])
    n2 = rec.append_linear(
        turn("assistant", "a"),
        ui=[msg("assistant"), msg("assistant")],  # two UI messages
    )
    assert rec.node_id_for_message_index(0) == (n1, 0)
    assert rec.node_id_for_message_index(1) == (n2, 1)  # first msg of n2
    assert rec.node_id_for_message_index(2) == (n2, 1)  # second msg of n2


def test_path_sibling_metadata_no_branches():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "q"))
    rec.append_linear(turn("assistant", "a"))
    assert rec.path_sibling_metadata() == {}


def test_path_sibling_metadata_with_branch():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"))
    rec.append_linear(turn("assistant", "v1"))
    n3 = rec.branch_from(n1, turn("assistant", "v2"))
    meta = rec.path_sibling_metadata()
    assert meta == {n3: (1, 2)}  # n3 is index 1 of 2 siblings


def test_path_sibling_metadata_multiple_branches():
    rec = new_conversation_record(title="t")
    _ = rec.append_linear(turn("user", "q"))
    n2 = rec.append_linear(turn("assistant", "a1"))
    rec.append_linear(turn("user", "q2"))
    rec.append_linear(turn("assistant", "a2"))
    # Branch at n2: create sibling of n3
    n5 = rec.branch_from(n2, turn("user", "q2-edited"))
    rec.branch_from(n5, turn("assistant", "a2-new"))
    # Active path is [n1, n2, n5, n6]; n5 has siblings [n3, n5] -> (1, 2)
    meta = rec.path_sibling_metadata()
    assert meta == {n5: (1, 2)}
