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
    assert rec.title_source == "fallback"


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


def test_meta_property():
    rec = new_conversation_record(title="t")
    meta = rec.meta
    assert isinstance(meta, ConversationMeta)
    assert (meta.id, meta.title) == (rec.id, rec.title)
    assert meta.created_at == rec.created_at
    assert meta.updated_at == rec.updated_at


def test_path_node_ids_raises_on_cycle():
    rec = new_conversation_record(title="cycle test")
    rec.nodes["n_a"] = ConversationNode(parent="n_b", turns=turn("user", "a"))
    rec.nodes["n_b"] = ConversationNode(
        parent="n_a", turns=turn("assistant", "b")
    )
    rec.current_leaf = "n_b"
    with pytest.raises(ValueError, match="Cycle"):
        rec.path_node_ids()


def test_append_linear_collision_safe():
    rec = new_conversation_record(title="collision test")
    rec.nodes["n_0005"] = ConversationNode(
        parent=None, turns=turn("user", "pre-inserted")
    )
    rec.current_leaf = "n_0005"
    new_id = rec.append_linear(turn("assistant", "reply"))
    assert new_id == "n_0006"
    assert rec.nodes["n_0005"].turns[0]["content"] == "pre-inserted"


def test_bookmark_state_id_round_trips():
    rec = new_conversation_record(title="t")
    rec.bookmark_state_id = "abc123"
    raw = rec.model_dump(mode="json")
    loaded = ConversationRecord.model_validate(raw)
    assert loaded.bookmark_state_id == "abc123"
