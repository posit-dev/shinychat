import pytest
from _history_test_helpers import branch_from
from shinychat._attachments import Attachment
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_types import (
    CapturedMessage,
    ConversationMeta,
    ConversationNode,
    ConversationRecord,
    ConversationRecordV1,
    ConversationRecordV2,
    UnsupportedSchemaVersionError,
    check_schema_version,
    new_conversation_record,
    new_conversation_record_v2,
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


def test_v2_record_tracks_an_exchange_path_with_captured_messages():
    input_message = StoredMessage(
        role="user",
        segments=[StoredSegment(content="hello", content_type="markdown")],
    )
    response = StoredMessage(
        role="assistant",
        segments=[StoredSegment(content="hi", content_type="markdown")],
    )
    rec = new_conversation_record_v2(
        title="hello",
        client_info={"kind": "test"},
    )

    rec.open_exchange("exchange-1", input_message)
    rec.append_message(
        "exchange-1",
        CapturedMessage.from_stored_message(response, icon="bot"),
    )

    assert isinstance(rec, ConversationRecordV2)
    assert rec.schema_version == 2
    assert rec.path_node_ids() == ["n_0000", "exchange-1"]
    node = rec.nodes["exchange-1"]
    assert node.status == "ok"
    assert node.input == input_message
    assert node.messages[0].as_stored_message() == response
    assert node.messages[0].icon == "bot"


def test_captured_message_round_trips_attachments_for_display():
    """The capture seam keeps attachments for display and drops nothing else.

    Pins main #394/#401 semantics at the seam level (gwg3): a captured
    message round-trips its attachments verbatim. (Controller-level tests
    cover that the model-facing attachment text never enters the capture.)
    """
    stored = StoredMessage(
        role="user",
        segments=[
            StoredSegment(content="See attached", content_type="markdown")
        ],
        attachments=[
            Attachment(
                mime="text/plain",
                name="notes.txt",
                size=5,
                data_url="data:text/plain;base64,aGVsbG8=",
            )
        ],
    )
    captured = CapturedMessage.from_stored_message(stored, icon=None)
    assert captured.attachments == stored.attachments
    assert captured.as_stored_message() == stored


def _v2_user_message(content: str) -> StoredMessage:
    return StoredMessage(
        role="user",
        segments=[StoredSegment(content=content, content_type="markdown")],
    )


def test_v2_graph_primitives_track_children_siblings_and_selected_path():
    rec = new_conversation_record_v2(
        title="hello",
        id="c_v2",
        client_info={"kind": "test"},
    )
    first = "exchange-1"
    second = "exchange-2"
    rec.open_exchange(first, _v2_user_message("first"))
    rec.set_active_leaf("n_0000")
    rec.open_exchange(second, _v2_user_message("second"))

    assert rec.children_of(None) == ["n_0000"]
    assert rec.children_of("n_0000") == [first, second]
    assert rec.siblings_of(first) == [first, second]
    assert rec.siblings_of(second) == [first, second]

    rec.set_active_leaf(first)
    assert rec.active_leaf == first
    assert rec.nodes["n_0000"].selected_child == first
    assert rec.nodes[first].selected_child is None


def test_v2_set_active_leaf_validates_before_mutating():
    rec = new_conversation_record_v2(
        title="hello",
        id="c_v2",
        client_info={"kind": "test"},
    )
    rec.open_exchange("exchange-1", _v2_user_message("first"))
    before = rec.model_dump()

    with pytest.raises(ValueError, match="Unknown exchange id"):
        rec.set_active_leaf("missing")

    assert rec.model_dump() == before


def test_v2_subtree_leaf_remembers_child_then_falls_back_to_newest():
    rec = new_conversation_record_v2(
        title="hello",
        id="c_v2",
        client_info={"kind": "test"},
    )
    first = "exchange-1"
    second = "exchange-2"
    first_leaf = "exchange-1-leaf"
    second_leaf = "exchange-2-leaf"
    rec.open_exchange(first, _v2_user_message("first"))
    rec.set_active_leaf("n_0000")
    rec.open_exchange(second, _v2_user_message("second"))
    rec.set_active_leaf(first)
    rec.open_exchange(first_leaf, _v2_user_message("first leaf"))
    rec.set_active_leaf(second)
    rec.open_exchange(second_leaf, _v2_user_message("second leaf"))

    rec.nodes["n_0000"].selected_child = first
    assert rec.subtree_leaf("n_0000") == first_leaf

    rec.nodes["n_0000"].selected_child = None
    assert rec.subtree_leaf("n_0000") == second_leaf


def test_v2_path_sibling_metadata_tracks_the_selected_exchange():
    rec = new_conversation_record_v2(
        title="hello",
        id="c_v2",
        client_info={"kind": "test"},
    )
    first = "exchange-1"
    original = "exchange-2-original"
    replacement = "exchange-2-replacement"
    rec.open_exchange(first, _v2_user_message("first"))
    rec.open_exchange(original, _v2_user_message("original"))
    rec.set_active_leaf(first)
    rec.open_exchange(replacement, _v2_user_message("replacement"))

    rec.finish_exchange(original, "ok", None)
    rec.finish_exchange(replacement, "ok", None)
    rec.nodes[original].checkpoint = "valid"
    rec.nodes[replacement].checkpoint = "valid"
    assert rec.path_sibling_metadata() == {replacement: (1, 2)}

    rec.set_active_leaf(original)
    assert rec.path_sibling_metadata() == {original: (0, 2)}


def test_v2_user_message_projection_skips_inputless_path_nodes():
    rec = new_conversation_record_v2(
        title="hello",
        id="c_v2",
        client_info={"kind": "test"},
    )
    first = "exchange-1"
    second = "exchange-2"
    rec.open_inputless_exchange()
    rec.open_exchange(first, _v2_user_message("first"))
    inputless = rec.open_inputless_exchange()
    response = StoredMessage(
        role="assistant",
        segments=[StoredSegment(content="response", content_type="markdown")],
    )
    rec.append_message(
        inputless, CapturedMessage.from_stored_message(response, icon=None)
    )
    rec.append_message(
        first, CapturedMessage.from_stored_message(response, icon=None)
    )
    rec.append_message(
        first, CapturedMessage.from_stored_message(response, icon=None)
    )
    rec.open_exchange(second, _v2_user_message("second"))

    assert rec.exchange_id_for_user_message_index(0) == first
    assert rec.exchange_id_for_user_message_index(4) == second
    with pytest.raises(IndexError):
        rec.exchange_id_for_user_message_index(1)
    with pytest.raises(IndexError):
        rec.exchange_id_for_user_message_index(5)
    with pytest.raises(IndexError):
        rec.exchange_id_for_user_message_index(-1)


@pytest.mark.parametrize("version", [True, 1.0, "1", [], [1], float("nan")])
def test_check_schema_version_rejects_non_integer_values(version: object):
    with pytest.raises(UnsupportedSchemaVersionError):
        check_schema_version(version)


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
    assert [t.get("role") for t in rec.path_turns()] == ["user", "assistant"]
    assert rec.updated_at >= rec.created_at


def test_path_follows_current_leaf_not_all_nodes():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "v1"))
    sibling = ConversationNode(parent=n1, turns=turn("assistant", "v2"))
    rec.nodes["n_sib"] = sibling
    rec.current_leaf = "n_sib"
    assert [t.get("content") for t in rec.path_turns()] == ["hi", "v2"]


def test_json_round_trip():
    rec = new_conversation_record(title="t")
    rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "hello"))
    rec2 = ConversationRecordV1.model_validate_json(rec.model_dump_json())
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
    loaded = ConversationRecordV1.model_validate(raw)
    assert loaded.bookmark_state_id == "abc123"


def test_append_linear_populates_children():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "hello"))
    n3 = rec.append_linear(turn("user", "follow-up"))
    assert rec.nodes[n1].children == [n2]
    assert rec.nodes[n2].children == [n3]
    assert rec.nodes[n3].children == []


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


def msg(role: str) -> dict[str, object]:
    return {
        "role": role,
        "segments": [{"content": role, "content_type": "markdown"}],
    }


def test_children_of_with_branch():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = branch_from(rec, n1, turn("assistant", "v2"))
    assert rec.children_of(n1) == [n2, n3]


def test_siblings_of():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = branch_from(rec, n1, turn("assistant", "v2"))
    assert rec.siblings_of(n2) == [n2, n3]
    assert rec.siblings_of(n3) == [n2, n3]
    # n1 has no siblings (only child of root)
    assert rec.siblings_of(n1) == [n1]


def test_subtree_leaf_returns_self_for_leaf_node():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    assert rec.subtree_leaf(n1) == n1


def test_subtree_leaf_follows_selected_child_else_newest():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = rec.append_linear(turn("user", "q2"))
    n4 = rec.append_linear(turn("assistant", "a2"))
    # append_linear recorded selected_child at each node, so subtree_leaf
    # replays it back to the current leaf.
    assert rec.subtree_leaf(n1) == n4
    # Branch a sibling of n3 under n2. branch_from bypasses set_current_leaf,
    # so n2 still remembers n3 from the linear appends.
    n5 = branch_from(rec, n2, turn("user", "q2-edited"))
    n6 = branch_from(rec, n5, turn("assistant", "a2-new"))
    # n2 remembers n3, so it returns to n4 rather than the newer n5 -> n6.
    assert rec.subtree_leaf(n2) == n4
    # With the memory cleared, it falls back to the newest child (n5 -> n6).
    rec.nodes[n2].selected_child = None
    assert rec.subtree_leaf(n2) == n6
    # n3 still leads to n4.
    assert rec.subtree_leaf(n3) == n4


def test_subtree_leaf_remembers_descendant_across_sibling_navigation():
    rec = new_conversation_record(title="t")
    root = rec.append_linear(turn("user", "start"))
    # Two sibling branches under root, each with two leaves of its own.
    b1 = branch_from(rec, root, turn("assistant", "b1"))
    b1a = branch_from(rec, b1, turn("assistant", "b1a"))
    branch_from(rec, b1, turn("assistant", "b1b"))
    b2 = branch_from(rec, root, turn("assistant", "b2"))
    branch_from(rec, b2, turn("assistant", "b2a"))
    b2b = branch_from(rec, b2, turn("assistant", "b2b"))

    # Land inside b1 on the OLDER leaf b1a (not the newest, b1b).
    rec.set_current_leaf(b1a)
    # Navigate to sibling b2: no memory yet, so its newest leaf (b2b).
    rec.set_current_leaf(rec.subtree_leaf(b2))
    assert rec.current_leaf == b2b
    # Navigate back to b1: returns to b1a, the last-viewed descendant, rather
    # than the newest leaf b1b.
    rec.set_current_leaf(rec.subtree_leaf(b1))
    assert rec.current_leaf == b1a


def test_branch_from_creates_sibling():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    n2 = rec.append_linear(turn("assistant", "v1"))
    n3 = branch_from(rec, n1, turn("assistant", "v2"))
    assert rec.nodes[n3].parent == n1
    assert rec.current_leaf == n3
    assert rec.children_of(n1) == [n2, n3]
    assert rec.path_turns() == turn("user", "hi") + turn("assistant", "v2")


def test_branch_from_root():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "v1"))
    n3 = branch_from(rec, None, turn("user", "bye"))
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
    n5 = branch_from(rec, n2, turn("user", "q2-edited"))
    # Old branch is intact
    assert rec.nodes[n3].parent == n2
    assert rec.nodes[n4].parent == n3
    # New branch is active
    assert rec.current_leaf == n5
    assert rec.path_turns() == (
        turn("user", "hi") + turn("assistant", "v1") + turn("user", "q2-edited")
    )


def test_node_id_for_message_index_simple():
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"), ui=[msg("user")])
    n2 = rec.append_linear(turn("assistant", "a"), ui=[msg("assistant")])
    assert rec.node_id_for_message_index(0) == (n1, 0)
    assert rec.node_id_for_message_index(1) == (n2, 1)


def test_node_id_for_message_index_counts_empty_ui_nodes_as_one():
    # A node with ui=None still renders one fabricated message on restore
    # (`node.ui or [fallback]`), so it occupies one client message
    # slot here too — the mapping must not skip it, or client indices would
    # disagree with the server.
    rec = new_conversation_record(title="t")
    n1 = rec.append_linear(turn("user", "q"), ui=[msg("user")])
    n2 = rec.append_linear(turn("assistant", "no-ui-1"))  # no ui
    n3 = rec.append_linear(turn("user", "no-ui-2"))  # no ui
    n4 = rec.append_linear(turn("assistant", "a"), ui=[msg("assistant")])
    assert rec.node_id_for_message_index(0) == (n1, 0)
    assert rec.node_id_for_message_index(1) == (n2, 1)
    assert rec.node_id_for_message_index(2) == (n3, 2)
    assert rec.node_id_for_message_index(3) == (n4, 3)


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
    n3 = branch_from(rec, n1, turn("assistant", "v2"))
    meta = rec.path_sibling_metadata()
    assert meta == {n3: (1, 2)}  # n3 is index 1 of 2 siblings


def test_path_sibling_metadata_multiple_branches():
    rec = new_conversation_record(title="t")
    _ = rec.append_linear(turn("user", "q"))
    n2 = rec.append_linear(turn("assistant", "a1"))
    rec.append_linear(turn("user", "q2"))
    rec.append_linear(turn("assistant", "a2"))
    # Branch at n2: create sibling of n3
    n5 = branch_from(rec, n2, turn("user", "q2-edited"))
    branch_from(rec, n5, turn("assistant", "a2-new"))
    # Active path is [n1, n2, n5, n6]; n5 has siblings [n3, n5] -> (1, 2)
    meta = rec.path_sibling_metadata()
    assert meta == {n5: (1, 2)}


# -- ConversationRecord: the name for the current version (plan §7.6, D1) --

def _v1_record_with_exchange() -> ConversationRecordV1:
    rec = new_conversation_record(title="legacy", id="c_v1")
    rec.append_linear(turn("user", "hi"))
    rec.append_linear(turn("assistant", "hello"))
    rec.bookmark_state_id = "st1"
    return rec


def test_conversation_record_names_the_current_version():
    assert issubclass(ConversationRecord, ConversationRecordV2)
    v2 = new_conversation_record_v2(title="t", client_info={})
    loaded = ConversationRecord.model_validate(v2.model_dump(mode="json"))
    assert isinstance(loaded, ConversationRecord)
    assert loaded.schema_version == 2
    assert loaded.model_dump(mode="json") == v2.model_dump(mode="json")


def test_conversation_record_upgrades_a_v1_dict():
    """A v1-era store calling model_validate on a v1 dict gets a v2 record."""
    rec = _v1_record_with_exchange()
    imported = ConversationRecord.model_validate(rec.model_dump(mode="json"))
    assert isinstance(imported, ConversationRecord)
    assert isinstance(imported, ConversationRecordV2)
    assert not isinstance(imported, ConversationRecordV1)
    assert imported.schema_version == 2
    assert imported.id == "c_v1"
    assert imported.title == "legacy"
    assert imported.bookmark_state_id == "st1"
    # The v1 user/assistant pair became one exchange on the active path.
    (exchange_id,) = [
        nid
        for nid, node in imported.nodes.items()
        if node.parent_id is not None
    ]
    exchange = imported.nodes[exchange_id]
    assert exchange.input is not None
    assert exchange.input.content == "hi"
    assert [m.as_stored_message().content for m in exchange.messages] == [
        "hello"
    ]
    assert imported.active_leaf == exchange_id


def test_conversation_record_upgrades_a_v1_dict_without_schema_version():
    # check_schema_version's None→1 convention: records that predate the
    # marker are v1 and upgrade too.
    rec = _v1_record_with_exchange()
    raw = rec.model_dump(mode="json")
    del raw["schema_version"]
    imported = ConversationRecord.model_validate(raw)
    assert isinstance(imported, ConversationRecord)
    assert imported.schema_version == 2
    assert imported.id == rec.id


def test_conversation_record_upgrades_a_v1_instance():
    imported = ConversationRecord.model_validate(_v1_record_with_exchange())
    assert isinstance(imported, ConversationRecord)
    assert imported.schema_version == 2
    assert imported.active_leaf is not None


def test_conversation_record_upgrades_via_validate_json():
    rec = _v1_record_with_exchange()
    imported = ConversationRecord.model_validate_json(rec.model_dump_json())
    assert isinstance(imported, ConversationRecord)
    assert imported.schema_version == 2
    assert imported.id == rec.id


def test_conversation_record_does_not_rewarn_on_upgrades():
    # The validator runs the non-warning import path: reads must not emit
    # lossy-import warnings on every validation (plan §7.4, D2).
    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        ConversationRecord.model_validate(_v1_record_with_exchange())


def test_conversation_record_rejects_unsupported_schema_versions():
    rec = _v1_record_with_exchange()
    raw = rec.model_dump(mode="json")
    raw["schema_version"] = 3
    with pytest.raises(Exception, match="schema_version"):
        ConversationRecord.model_validate(raw)


def test_upgraded_record_survives_revalidation():
    rec = _v1_record_with_exchange()
    imported = ConversationRecord.model_validate(rec.model_dump(mode="json"))
    # Re-validating the upgraded record must not run the import again (or
    # otherwise change it): v2 input passes through unchanged.
    again = ConversationRecord.model_validate(
        imported.model_dump(mode="json")
    )
    assert again == imported


def test_conversation_record_constructs_from_v2_kwargs_without_marker():
    """v2 kwargs without schema_version are current-version input, not v1.

    Building `ConversationRecord` -- the class that names the current
    version -- must not misroute into the v1 model just because the caller
    left the (defaulted) marker off; the node values here are v2
    `ExchangeNode`s and the dict says `active_leaf`, never `current_leaf`.
    """
    v2 = new_conversation_record_v2(title="t", client_info={"provider": "x"})
    built = ConversationRecord(
        id=v2.id,
        title=v2.title,
        created_at=v2.created_at,
        updated_at=v2.updated_at,
        client_info=v2.client_info,
        nodes=v2.nodes,
        active_leaf=v2.active_leaf,
    )
    assert isinstance(built, ConversationRecord)
    assert built.schema_version == 2
    assert built.model_dump(mode="json") == v2.model_dump(mode="json")

    raw = v2.model_dump(mode="json")
    del raw["schema_version"]
    loaded = ConversationRecord.model_validate(raw)
    assert isinstance(loaded, ConversationRecord)
    assert loaded.schema_version == 2
    assert loaded.model_dump(mode="json") == v2.model_dump(mode="json")


def test_conversation_record_still_upgrades_markerless_v1_shapes():
    """The markerless path stays load-bearing for pre-marker records.

    Released v1 record forms that predate the schema_version marker have no
    explicit version to route on, so shape decides: `current_leaf` alone,
    and v1 node keys (`parent`/`turns`) when the leaf was dropped from the
    dump too. Both must upgrade, never validate as v2.
    """
    rec = _v1_record_with_exchange()
    expected_id = rec.id

    raw = rec.model_dump(mode="json")
    del raw["schema_version"]
    imported = ConversationRecord.model_validate(raw)
    assert isinstance(imported, ConversationRecord)
    assert imported.schema_version == 2
    assert imported.id == expected_id

    # Same dict with both markerless routes gone: detection falls back to
    # the v1-only node keys.
    del raw["current_leaf"]
    imported = ConversationRecord.model_validate(raw)
    assert isinstance(imported, ConversationRecord)
    assert imported.schema_version == 2
    assert imported.id == expected_id


def test_conversation_record_accepts_a_plain_v2_instance():
    """A plain ConversationRecordV2 validates as the current version.

    The controller/recorder build plain V2 objects, and a store may hand
    one back to `ConversationRecord.model_validate*`; the record survives
    with equal content and the result is a ConversationRecord.
    """
    v2 = new_conversation_record_v2(title="t", client_info={})
    assert not isinstance(v2, ConversationRecord)
    rec = ConversationRecord.model_validate(v2)
    assert isinstance(rec, ConversationRecord)
    assert rec.model_dump(mode="json") == v2.model_dump(mode="json")
    # An already-converted record revalidates to itself, not a copy.
    again = ConversationRecord.model_validate(rec)
    assert again is rec
