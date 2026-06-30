from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

TitleSource = Literal["llm", "user", "fallback"]


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
    title_source: TitleSource = "fallback"
    created_at: datetime
    updated_at: datetime
    client_info: dict[str, str] = Field(default_factory=dict)
    nodes: dict[str, ConversationNode] = Field(default_factory=dict)
    next_node_seq: int = 1
    current_leaf: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    bookmark_state_id: str | None = None

    @property
    def meta(self) -> ConversationMeta:
        return ConversationMeta(
            id=self.id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
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
