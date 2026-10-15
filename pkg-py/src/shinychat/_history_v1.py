"""Pure v1 -> v2 conversation-record import.

:func:`import_v1_record` turns a legacy v1 :class:`ConversationRecordV1`
(the linear node-tree record written by shinychat py 0.6.x-0.7.2 and
R 0.5.0) into a v2 :class:`~shinychat._history_types.ConversationRecordV2`
exchange tree. The transform is pure data: no session, no store, no I/O,
and no provider client.

Fidelity contract: the imported record displays
exactly what released py 0.7.2 displayed for the v1 record — no better,
no worse. Versioned stored UI is carried verbatim; unversioned or missing
UI is discarded and re-derived from turns; user-message attachment content
is stripped. F3-class artifacts already in the record are carried, not
repaired. The contract covers records written by the released v1 writers;
corrupt shapes no released writer produces (e.g. one-sided parent/child
links) import best-effort, without a fidelity guarantee.

Structure mapping: an input-bearing v1 node U pairs with each of its
response children R into one exchange (id R) whose input is U's first
display message and whose messages are the rest of U plus R — regenerate
responses become sibling exchanges sharing the input. A "bare" exchange
(id U, no response) is created when U's selected child is not a response,
U has non-response children, or U is the record's current leaf (v1's
displayed path stopped at U even when a response child could follow it);
non-response children re-parent under bare(U) to preserve the turn prefix.
Every v1 node id is reused verbatim as an
exchange id; ids are never parsed, so foreign/custom ids are tolerated.
Multiple v1 roots re-parent under a synthesized input-less root.

Warnings name only genuinely lossy steps (dropped messages, a dangling
active leaf) and are *returned*, never emitted, so the read-gate wiring
that upgrades on read can surface each warning once instead of re-warning
on every read.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, cast

from pydantic import JsonValue, ValidationError

from ._attachments import Attachment, attachment_to_content
from ._chat_normalize import normalize_message
from ._chat_types import StoredMessage, as_stored_message
from ._history_client import (
    normalize_turn_group,
    turn_dict_effective_role,
    turn_fallback_markdown,
)
from ._history_types import (
    STORED_UI_VERSION,
    TURNS_STATE_KEY,
    CapturedMessage,
    ConversationNode,
    ConversationRecordV1,
    ConversationRecordV2,
    ExchangeNode,
    StateEntry,
    StoredUiMessage,
    TurnDict,
    _ancestor_path,
    is_stored_ui_versioned,
)

if TYPE_CHECKING:
    from shiny.session import Session

_INPUT = "input"
_RESPONSE = "response"
_NEUTRAL = "neutral"


def import_v1_record(record: ConversationRecordV1) -> ConversationRecordV2:
    """Import a legacy v1 record as a v2 exchange tree.

    Lossy-import warnings are discarded; use
    :func:`import_v1_record_with_warnings` to collect them.
    """
    imported, _ = import_v1_record_with_warnings(record)
    return imported


def import_v1_record_with_warnings(
    record: ConversationRecordV1,
) -> tuple[ConversationRecordV2, list[str]]:
    """Import a v1 record, returning the v2 record and its warnings.

    The returned warnings describe genuinely lossy steps only — dropped
    display messages and a dangling active leaf — never the synthesized
    root, status, or ``created_at`` values, the v1 record's missing system
    prompt, or the ``chatlas``/``turns`` turn-kind inference.
    """
    warns: list[str] = []
    display = _display_messages(record, warns)
    nodes = record.nodes
    klass = {nid: _message_class(messages) for nid, messages in display.items()}
    existing_children = {
        nid: _dedupe([child for child in node.children if child in nodes])
        for nid, node in nodes.items()
    }
    root_level = [
        nid
        for nid, node in nodes.items()
        if node.parent is None or node.parent not in nodes
    ]

    def stored_pointer(nid: str) -> str | None:
        """The pointer stored on `nid` when it names an existing child.

        v1's own rule: a ``selected_child`` that does not name an existing
        child of the node is ignored — whether stale (it names no node in
        the record) or one-sided (it names a real node missing from this
        node's children list) — and v1's fallback applies. Both passes
        resolve pointers through this one predicate so an ignored pointer
        can never reach the v2 record.
        """
        selected = nodes[nid].selected_child
        if selected is None or selected not in existing_children[nid]:
            return None
        return selected

    def effective_selected(nid: str) -> str | None:
        """The child v1 itself would follow from this node.

        Mirrors v1's ``subtree_leaf`` rule: the stored pointer when it names
        an existing child, else the last child. Records written before the
        pointer existed (py 0.6.x never stored ``selected_child`` at all)
        therefore keep their real continuation — the last response — instead
        of sprouting phantom bare exchanges for every user turn.
        """
        selected = stored_pointer(nid)
        if selected is not None:
            return selected
        children = existing_children[nid]
        return children[-1] if children else None

    def has_bare(nid: str) -> bool:
        """Whether input node `nid` also keeps a bare exchange of its own.

        True when the child v1 would follow is not a response (it is a
        leaf, or the active path continues through a non-response child),
        when any child must re-parent under the bare exchange to
        preserve its turn prefix, or when `nid` is the record's current
        leaf: v1's displayed path stopped at an input leaf even when the
        node had a response child it could have followed (a leaf saved
        mid-regenerate or after a cancelled regenerate), so the import
        keeps a bare exchange for the path to stop there too.
        """
        response_ids = {
            child
            for child in existing_children[nid]
            if klass[child] == _RESPONSE
        }
        if effective_selected(nid) not in response_ids:
            return True
        if nid == record.current_leaf:
            return True
        return any(
            klass[child] != _RESPONSE for child in existing_children[nid]
        )

    # The synthesized root never collides with a v1 node id: membership
    # checks only, never id parsing (foreign/custom ids are tolerated).
    root_id = "n_0000"
    suffix = 1
    while root_id in nodes:
        root_id = f"n_0000_{suffix}"
        suffix += 1

    def mapped(nid: str) -> str:
        """The exchange covering v1 node `nid`'s continuation.

        An input-bearing node continues through its selected response's
        pair exchange whenever the child v1 would follow is a response —
        whether or not the node also keeps a bare exchange — so pointer
        values never depend on dictionary order. Otherwise the node's own
        exchange (bare for inputs) carries it.
        """
        if klass[nid] != _INPUT:
            return nid
        selected = effective_selected(nid)
        if selected is not None and klass[selected] == _RESPONSE:
            return selected
        return nid

    def cover(nid: str | None) -> str:
        """The exchange id carrying `nid`'s own content (root for None).

        Placement and continuation follow different exchanges for an
        input-bearing node with both a selected response and a bare exchange:
        `mapped` follows the selected continuation, while placement keeps the
        bare exchange so non-response children re-parent under it. They agree
        everywhere else (and share this delegation for the no-bare case), so
        the two cannot drift apart.
        """
        if nid is None or nid not in nodes:
            return root_id
        if klass[nid] == _INPUT and not has_bare(nid):
            return mapped(nid)
        return nid

    exchanges: dict[str, ExchangeNode] = {
        root_id: ExchangeNode(
            parent_id=None,
            created_at=record.created_at,
            status="ok",
        )
    }

    turn_kind = _turn_entry_kind(nodes)

    for nid, node in nodes.items():
        node_class = klass[nid]
        if node_class == _INPUT and not has_bare(nid):
            continue
        messages: list[StoredMessage]
        input_message: StoredMessage | None
        turns: list[dict[str, Any]]
        parent_id: str | None
        if node_class == _RESPONSE and (
            node.parent in nodes and klass[node.parent] == _INPUT
        ):
            user_messages = display[node.parent]
            input_message = user_messages[0]
            messages = user_messages[1:] + display[nid]
            turns = list(nodes[node.parent].turns) + list(node.turns)
            parent_id = cover(nodes[node.parent].parent)
        else:
            input_message = display[nid][0] if node_class == _INPUT else None
            messages = (
                display[nid][1:] if node_class == _INPUT else display[nid]
            )
            turns = list(node.turns)
            parent_id = cover(node.parent)

        exchanges[nid] = ExchangeNode(
            parent_id=parent_id,
            created_at=record.created_at,
            status=(
                "ok"
                if messages
                else ("cancelled" if input_message is not None else "ok")
            ),
            input=input_message.model_copy(deep=True)
            if input_message is not None
            else None,
            messages=[
                CapturedMessage.from_stored_message(message, icon=None)
                for message in messages
            ],
        )
        # v1 never stored the system prompt, so the record carries per-
        # exchange deltas and no root snapshot: folding the chain from
        # entry 0 reproduces v1's path_turns() exactly.
        exchanges[nid].state[TURNS_STATE_KEY] = StateEntry(
            kind=turn_kind,
            version=1,
            mode="delta",
            data=cast(JsonValue, copy.deepcopy(turns)),
        )

    def covering_exchanges(nid: str) -> list[str]:
        """Exchange ids covering `nid`'s alternatives, in v1 child order.

        An input-bearing node contributes one pair exchange per response
        child plus its bare exchange when one exists; response and neutral
        nodes contribute themselves.
        """
        if klass[nid] != _INPUT:
            return [nid]
        ids: list[str] = []
        bare_listed = False
        for child in existing_children[nid]:
            if klass[child] == _RESPONSE:
                ids.append(child)
            elif not bare_listed:
                ids.append(nid)
                bare_listed = True
        if has_bare(nid) and not bare_listed:
            ids.append(nid)
        return ids

    def continuations_after(nid: str | None) -> list[str]:
        """Covering-exchange ids of the continuations after `nid`.

        `None` means the record roots. Response children of an
        input-bearing node are skipped: they pair with the node itself, so
        their exchanges hang above the node's own content.
        """
        child_ids = (
            root_level if nid is None else existing_children.get(nid, [])
        )
        ids: list[str] = []
        for child in child_ids:
            if (
                nid is not None
                and klass[child] == _RESPONSE
                and klass[nid] == _INPUT
            ):
                continue
            ids.extend(covering_exchanges(child))
        return _dedupe(ids)

    for nid, exchange in exchanges.items():
        exchange.children = continuations_after(None if nid == root_id else nid)

    for nid, exchange in exchanges.items():
        parent_id = exchange.parent_id
        if parent_id is not None and nid not in exchanges[parent_id].children:
            exchanges[parent_id].children.append(nid)

    for nid in nodes:
        selected = stored_pointer(nid)
        if selected is None:
            continue
        if klass[nid] == _INPUT and klass[selected] == _RESPONSE:
            continue
        exchanges[nid].selected_child = mapped(selected)

    active_leaf: str | None = None
    if record.current_leaf is not None:
        if record.current_leaf in nodes:
            leaf = record.current_leaf
            active_leaf = leaf if klass[leaf] == _INPUT else mapped(leaf)
        else:
            best_effort = _best_effort_leaf(exchanges, root_id)
            warns.append(
                f"conversation {record.id}: current leaf "
                f"{record.current_leaf!r} is not a node in this record; the "
                f"best-effort leaf {best_effort!r} was imported instead"
            )
            active_leaf = best_effort
    else:
        active_leaf = root_id

    # Explicit active-path walk keeps the copied pointers consistent along
    # the imported path (and clears the leaf's own pointer, as v1 does).
    if active_leaf is not None:
        path = _ancestor_path(exchanges, active_leaf)
        for index, nid in enumerate(path):
            exchanges[nid].selected_child = (
                path[index + 1] if index + 1 < len(path) else None
            )

    imported = ConversationRecordV2(
        id=record.id,
        title=record.title,
        title_source=record.title_source,
        response_count=record.response_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        client_info=dict(record.client_info),
        nodes=exchanges,
        next_node_seq=record.next_node_seq,
        active_leaf=active_leaf,
        values=copy.deepcopy(record.values),
        bookmark_state_id=record.bookmark_state_id,
    )
    return imported, warns


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for nid in ids:
        if nid not in seen:
            seen.add(nid)
            result.append(nid)
    return result


def _message_class(messages: list[StoredMessage]) -> str:
    if not messages:
        return _NEUTRAL
    return _INPUT if messages[0].role == "user" else _RESPONSE


def _turn_entry_kind(nodes: dict[str, ConversationNode]) -> str:
    """Infer the turn-state kind from the stored turn shapes.

    ``chatlas`` turns carry top-level ``contents`` lists (ellmer's
    ``contents_record()`` writes the same shape); anything else is the
    generic ``turns`` kind. The inference itself never warns.
    """
    all_turns = [turn for node in nodes.values() for turn in node.turns]
    if not all_turns:
        return "turns"
    return (
        "chatlas"
        if all(
            isinstance(turn, dict) and isinstance(turn.get("contents"), list)
            for turn in all_turns
        )
        else "turns"
    )


def _best_effort_leaf(exchanges: dict[str, ExchangeNode], root_id: str) -> str:
    cursor = root_id
    visited: set[str] = set()
    while exchanges[cursor].children:
        if cursor in visited:
            raise ValueError(
                f"Cycle detected in conversation nodes at {cursor!r}"
            )
        visited.add(cursor)
        selected = exchanges[cursor].selected_child
        children = exchanges[cursor].children
        cursor = selected if selected in children else children[-1]
    return cursor


def _stored_ui_dict(stored: StoredMessage) -> StoredUiMessage:
    """Serialize a StoredMessage for persistence in a node's ``ui`` list.

    Adds the version marker and drops empty ``attachments`` so text-only
    messages keep their previous shape.
    """
    d = stored.model_dump(exclude_none=True)
    if not d.get("attachments"):
        d.pop("attachments", None)
    d["version"] = STORED_UI_VERSION
    return cast(StoredUiMessage, d)


def derive_stored_ui_message(
    group: list[TurnDict],
    session: Session | None = None,
) -> StoredUiMessage | None:
    """Derive one stored UI message from a turn group.

    The group is merged and normalized through ``normalize_turn_group``,
    so the result's ``segments`` interleave string segments and structured
    blocks. Returns ``None`` when the group has nothing to display.
    """
    msg = normalize_turn_group(group)
    if msg is None:
        return None
    return _stored_ui_dict(as_stored_message(msg, session))


# Stopgap: turn-derived UI mixes model-facing attachment content into user
# message bodies, so we re-serialize each attachment and subtract it here.
# v2 records capture user messages as displayed, so this only serves v1
# records. Delete it and attachment_content_stripped when v1 is retired.
def _strip_attachment_content(
    message: StoredUiMessage,
) -> StoredUiMessage:
    attachments = message.get("attachments")
    if (
        message.get("role") != "user"
        or not attachments
        or message.get("attachment_content_stripped") is True
    ):
        return message

    segments = [dict(segment) for segment in message["segments"]]
    attachment_segments: list[dict[str, Any]] = []
    try:
        for value in attachments:
            attachment = Attachment.model_validate(value)
            attachment_message = normalize_message(
                attachment_to_content(attachment)
            )
            stored = _stored_ui_dict(
                as_stored_message(attachment_message, session=None)
            )
            attachment_segments.extend(
                cast(list[dict[str, Any]], stored["segments"])
            )
    except Exception:
        # StoredMessage validation reports malformed attachments later. Do not
        # make replay more fragile while cleaning records from older versions.
        return message

    for attachment_segment in reversed(attachment_segments):
        if "type" in attachment_segment:
            for index in range(len(segments) - 1, -1, -1):
                if segments[index] == attachment_segment:
                    segments.pop(index)
                    break
            continue

        suffix = str(attachment_segment.get("content", ""))
        if not suffix:
            continue
        for index in range(len(segments) - 1, -1, -1):
            segment = segments[index]
            if "type" in segment:
                continue
            content = str(segment.get("content", ""))
            if content == suffix:
                segment["content"] = ""
                break
            separator_suffix = f"\n\n{suffix}"
            if content.endswith(separator_suffix):
                segment["content"] = content[: -len(separator_suffix)]
                break

    segments = [
        segment
        for segment in segments
        if "type" in segment or segment.get("content") != ""
    ]
    if not any("type" not in segment for segment in segments):
        segments.insert(0, {"content": "", "content_type": "markdown"})

    cleaned = dict(message)
    cleaned["segments"] = cast(Any, segments)
    cleaned["attachment_content_stripped"] = True
    return cast(StoredUiMessage, cleaned)


def derive_node_ui(
    turns: list[TurnDict],
    session: Session | None = None,
) -> list[StoredUiMessage]:
    """Re-derive a node's stored UI from its turns.

    Called at replay time when the stored UI is missing or predates the
    structured format (no version marker). Old persisted UI is discarded,
    never re-parsed. A node holds one turn group, so this derives at most
    one message. Falls back to a text-only message when the turns are
    missing or normalize to nothing.
    """
    derived = (
        derive_stored_ui_message(turns, session=session) if turns else None
    )
    if derived is not None:
        return [derived]
    if turns:
        last = turns[-1]
        role = turn_dict_effective_role(last)
        content = turn_fallback_markdown(last)
    else:
        role, content = "assistant", ""
    return [
        cast(
            StoredUiMessage,
            {
                "version": STORED_UI_VERSION,
                "role": role,
                "segments": [{"content": content, "content_type": "markdown"}],
            },
        )
    ]


def _display_messages(
    record: ConversationRecordV1, warns: list[str]
) -> dict[str, list[StoredMessage]]:
    """Per-node display messages, following the 0.7.2 replay fidelity rule.

    Versioned stored UI is carried verbatim; unversioned or missing UI is
    discarded and re-derived from turns. User-message attachment content
    is stripped either way. Messages that cannot be represented in a v2
    record (system role, or failing ``StoredMessage`` validation) are
    dropped with a warning naming the node.
    """
    result: dict[str, list[StoredMessage]] = {}
    for nid, node in record.nodes.items():
        if node.ui is not None and is_stored_ui_versioned(node.ui):
            raw: list[dict[str, Any]] = list(node.ui)
        else:
            if node.ui:
                if not node.turns:
                    warns.append(
                        f"conversation {record.id}: node {nid!r} carried "
                        f"{len(node.ui)} stored UI message(s) but no turns "
                        f"to re-derive display from; the message(s) were "
                        f"dropped"
                    )
                elif len(node.ui) > 1:
                    warns.append(
                        f"conversation {record.id}: node {nid!r} carried "
                        f"{len(node.ui)} stored UI message(s) without a "
                        f"version marker, but only one display message can "
                        f"be re-derived from its turns; "
                        f"{len(node.ui) - 1} message(s) were dropped"
                    )
            raw = cast(
                "list[dict[str, Any]]",
                derive_node_ui(cast("list[TurnDict]", list(node.turns))),
            )
        messages: list[StoredMessage] = []
        for raw_message in raw:
            stripped = _strip_attachment_content(
                cast("StoredUiMessage", raw_message)
            )
            payload = dict(stripped)
            payload.pop("attachment_content_stripped", None)
            try:
                stored = StoredMessage.model_validate(payload)
            except ValidationError as error:
                details = "; ".join(
                    f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                    for err in error.errors(include_input=False)
                )
                warns.append(
                    f"conversation {record.id}: node {nid!r} had a stored "
                    f"UI message that cannot be represented in the "
                    f"exchange-tree record (invalid message: {details}); "
                    f"it was dropped"
                )
                continue
            if stored.role == "system":
                warns.append(
                    f"conversation {record.id}: node {nid!r} had a stored "
                    f"UI message that cannot be represented in the "
                    f"exchange-tree record (system role); it was dropped"
                )
                continue
            messages.append(stored)
        result[nid] = messages
    return result
