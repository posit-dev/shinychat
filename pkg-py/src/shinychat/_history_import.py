"""Pure v1 -> v2 conversation-record import (plan sections 7.3-7.5).

:func:`import_v1_record` turns a legacy v1 :class:`ConversationRecordV1`
(the linear node-tree record written by shinychat py 0.6.x-0.7.2 and
R 0.5.0) into a v2 :class:`~shinychat._history_types.ConversationRecordV2`
exchange tree. The transform is pure data: no session, no store, no I/O,
and no provider client.

Fidelity contract (plan section 7.4): the imported record displays
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
from typing import Any, cast

from pydantic import JsonValue, ValidationError

from ._chat_types import StoredMessage
from ._history_client import TurnDict
from ._history_types import (
    CapturedMessage,
    ConversationNode,
    ConversationRecordV1,
    ConversationRecordV2,
    ExchangeNode,
    StateEntry,
    StoredUiMessage,
    is_stored_ui_versioned,
)

# The blessed state-entry name; mirrors `_history_recorder`.
_TURNS_STATE_KEY = "shinychat:turns"

# Node classes, decided by a node's first display message.
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
    # Root level includes orphans whose parent id names no node, so their
    # content stays reachable under the synthesized root.
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
            # No bare exchange: the node folds into the pair exchange built
            # from its selected response child.
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

    # One exchange per v1 node, except input-bearing nodes without a bare
    # exchange: those fold into the pair exchange of their selected
    # response child and never occupy an id of their own. Pair and bare
    # exchanges keyed by the v1 node they *end* at, so children lists and
    # parent ids below resolve without chaining.
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
            # Pair exchange: the input-bearing parent's user message plus
            # this response. Regenerate siblings each build their own pair,
            # sharing the same input.
            user_messages = display[node.parent]
            input_message = user_messages[0]
            messages = user_messages[1:] + display[nid]
            turns = list(nodes[node.parent].turns) + list(node.turns)
            parent_id = cover(nodes[node.parent].parent)
        else:
            # A bare input exchange, an unpaired response, or a node with
            # no representable display messages.
            input_message = display[nid][0] if node_class == _INPUT else None
            messages = (
                display[nid][1:] if node_class == _INPUT else display[nid]
            )
            turns = list(node.turns)
            parent_id = cover(node.parent)

        exchanges[nid] = ExchangeNode(
            parent_id=parent_id,
            created_at=record.created_at,
            # Driver-approved synthesis (2026-10-15): "ok" once an exchange
            # carries messages, "cancelled" when an input-bearing exchange
            # has no response messages (an interrupted exchange, retryable).
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
        exchanges[nid].state[_TURNS_STATE_KEY] = StateEntry(
            kind=turn_kind,
            version=1,
            mode="delta",
            data=cast(JsonValue, copy.deepcopy(turns)),
        )

    # Children lists preserve v1 sibling order: each exchange's children
    # are the covering exchanges of the continuations after the v1 node it
    # ends at (the record roots for the synthesized root).
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

    # One-sided links (a node whose parent field names an existing node that
    # does not list it among its children) never surface through the edge
    # pass above, so reconcile: every non-root exchange must appear in its
    # parent's children list exactly once. Appending (rather than re-rooting)
    # keeps the node reachable under its named parent. This is a corrupt
    # shape no released v1 writer produces, so it imports best-effort only:
    # the section 7.4 fidelity contract does not cover it.
    for nid, exchange in exchanges.items():
        parent_id = exchange.parent_id
        if parent_id is not None and nid not in exchanges[parent_id].children:
            exchanges[parent_id].children.append(nid)

    # Pointer post-pass. Each v1 pointer N.selected = C writes exactly one
    # v2 slot: the exchange covering N (N's bare exchange for input nodes).
    # A pointer from an input node to a response child is skipped — the pair
    # exchange covering that input and its selected response embodies it, and
    # `mapped` reports it wherever the parent level needs it — so two v1
    # pointers can never race for one slot and the result never depends on
    # dictionary order (the active-path walk below re-affirms the path).
    # Pointers resolve through the same `stored_pointer` predicate the
    # structure pass uses, so one that does not name an existing child of
    # its node (stale or one-sided) is ignored here exactly as v1's own
    # fallback semantics would, instead of writing a pointer no exchange
    # covers.
    for nid in nodes:
        selected = stored_pointer(nid)
        if selected is None:
            continue
        if klass[nid] == _INPUT and klass[selected] == _RESPONSE:
            continue
        exchanges[nid].selected_child = mapped(selected)

    # Active leaf: reuse the current leaf's covering exchange; a dangling
    # pointer falls back to a best-effort leaf walked from the root. An
    # input-node leaf maps to its own bare exchange (has_bare above forces
    # one into existence for it): v1's displayed path stopped at the input
    # node itself, not at the response child it could have followed, so the
    # imported path must stop at the same place instead of displaying that
    # response.
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
        # No active leaf: v1 displayed nothing for this record, and the
        # imported record must display nothing too. Sitting at the
        # synthesized root gives exactly that (the root has no input or
        # messages) and is the same shape a fresh v2 record has, so restore
        # paths that need a concrete leaf (e.g. the legacy bookmark stamp's
        # active-leaf fallback) see a well-formed record.
        active_leaf = root_id

    # Explicit active-path walk keeps the copied pointers consistent along
    # the imported path (and clears the leaf's own pointer, as v1 does).
    if active_leaf is not None:
        path: list[str] = []
        visited: set[str] = set()
        cursor: str | None = active_leaf
        while cursor is not None:
            if cursor in visited:
                raise ValueError(
                    f"Cycle detected in conversation nodes at {cursor!r}"
                )
            visited.add(cursor)
            path.append(cursor)
            cursor = exchanges[cursor].parent_id
        path.reverse()
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
    """Descend selected-child pointers from the root, newest child last."""
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
    # Lazy import: `_history` imports this module's siblings in cycles.
    from ._history import _strip_attachment_content, derive_node_ui

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
