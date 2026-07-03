from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

TitleSource = Literal["llm", "user"]


def new_conversation_record(*, title: str) -> ConversationRecord:
    now = utcnow()
    return ConversationRecord(
        id=new_conversation_id(),
        title=title,
        created_at=now,
        updated_at=now,
    )


class ConversationMeta(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    # Backend-defined storage footprint (e.g. on-disk bytes, in-memory JSON
    # dump size) — required so ConversationStore.total_size() can be derived
    # by summing list() results instead of a separate per-backend sweep.
    size_bytes: int


class ConversationNode(BaseModel):
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    # One or more serialized turns forming a single exchange unit. A tool-call
    # exchange (assistant-request, user-result, ..., assistant-text) is stored
    # as one node so it maps 1:1 with the combined UI message from streaming.
    turns: list[dict[str, Any]]
    # Render cache: StoredMessage dicts produced during this exchange.
    # None => re-render from turns on restore (lossy but never broken).
    ui: list[dict[str, Any]] | None = None


class ConversationRecord(BaseModel):
    schema_version: int = 1
    id: str
    title: str
    # None = timestamp-based title, no explicit source yet — either LLM
    # titling hasn't finished (or was never enabled) or nothing has renamed
    # it. Distinct from "llm"/"user", which are always explicit and final.
    title_source: TitleSource | None = None
    # Completed-response count for this conversation, incremented once per
    # genuinely-new on_response() call. Drives the "title after the second
    # response" trigger in HistoryController.on_response — not derived from
    # turn/node counts, since those vary by client and tool-call structure.
    response_count: int = 0
    created_at: datetime
    updated_at: datetime
    client_info: dict[str, str] = Field(default_factory=dict)
    nodes: dict[str, ConversationNode] = Field(default_factory=dict)
    next_node_seq: int = 1
    current_leaf: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    bookmark_state_id: str | None = None

    def meta(self, *, size_bytes: int) -> ConversationMeta:
        """Lightweight summary for `ConversationStore.list()`.

        See `ConversationMeta.size_bytes` for why the caller must supply it.
        """
        return ConversationMeta(
            id=self.id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            size_bytes=size_bytes,
        )

    def path_node_ids(self) -> list[str]:
        ids: list[str] = []
        visited: set[str] = set()
        cursor = self.current_leaf
        while cursor is not None:
            if cursor in visited:
                raise ValueError(
                    f"Cycle detected in conversation nodes at {cursor!r}"
                )
            node = self.nodes.get(cursor)
            if node is None:
                raise ValueError(f"Dangling parent reference at {cursor!r}")
            visited.add(cursor)
            ids.append(cursor)
            cursor = node.parent
        ids.reverse()
        return ids

    def path_turns(self) -> list[dict[str, Any]]:
        return [
            turn
            for node_id in self.path_node_ids()
            for turn in self.nodes[node_id].turns
        ]

    def children_of(self, node_id: str | None) -> list[str]:
        if node_id is None:
            children = [
                nid for nid, node in self.nodes.items() if node.parent is None
            ]
            children.sort(key=lambda nid: int(nid.split("_")[1]))
            return children
        return list(self.nodes[node_id].children)

    def siblings_of(self, node_id: str) -> list[str]:
        parent = self.nodes[node_id].parent
        return self.children_of(parent)

    def subtree_leaf(self, node_id: str) -> str:
        children = self.children_of(node_id)
        if not children:
            return node_id
        return self.subtree_leaf(children[-1])

    def path_sibling_metadata(self) -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        for nid in self.path_node_ids():
            siblings = self.siblings_of(nid)
            if len(siblings) > 1:
                result[nid] = (siblings.index(nid), len(siblings))
        return result

    def node_id_for_message_index(self, index: int) -> tuple[str, int]:
        if index < 0:
            raise IndexError(f"Message index {index} out of range")
        path = self.path_node_ids()
        cumulative = 0
        for i, nid in enumerate(path):
            n_ui = len(self.nodes[nid].ui or [])
            if index < cumulative + n_ui:
                return nid, i
            cumulative += n_ui
        raise IndexError(f"Message index {index} out of range")

    def branch_from(
        self,
        fork_parent_id: str | None,
        turns: list[dict[str, Any]],
        ui: list[dict[str, Any]] | None = None,
    ) -> str:
        """Create a sibling node directly. No production call site — handle_edit
        achieves branching indirectly via current_leaf truncation; this exists
        for constructing branched fixtures in tests."""
        node_id = f"n_{self.next_node_seq:04d}"
        self.next_node_seq += 1
        self.nodes[node_id] = ConversationNode(
            parent=fork_parent_id, turns=turns, ui=ui
        )
        if fork_parent_id is not None:
            self.nodes[fork_parent_id].children.append(node_id)
        self.current_leaf = node_id
        self.updated_at = utcnow()
        return node_id

    def append_linear(
        self,
        turns: list[dict[str, Any]],
        ui: list[dict[str, Any]] | None = None,
    ) -> str:
        node_id = f"n_{self.next_node_seq:04d}"
        self.next_node_seq += 1
        node = ConversationNode(parent=self.current_leaf, turns=turns, ui=ui)
        self.nodes[node_id] = node
        if self.current_leaf is not None:
            self.nodes[self.current_leaf].children.append(node_id)
        self.current_leaf = node_id
        self.updated_at = utcnow()
        return node_id


def new_conversation_id() -> str:
    # Time-prefixed for rough sortability; token for uniqueness.
    # (Avoids a ULID dependency. Ordering in the UI always comes from
    # updated_at, never from the id.)
    # Same-millisecond collisions are astronomically unlikely (40 bits of
    # token entropy) but not impossible; a collision would be last-writer-wins.
    return f"c_{int(time.time() * 1000):013x}{secrets.token_hex(5)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
