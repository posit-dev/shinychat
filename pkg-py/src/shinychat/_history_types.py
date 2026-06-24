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
    # Serialized turn (client-specific JSON, e.g. chatlas Turn.model_dump(mode="json"))
    turn: dict[str, Any]
    # Render cache: serialized StoredMessage dicts produced during this turn.
    # None => re-render from `turn` on restore (lossy but never broken).
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
    current_leaf: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)

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
            visited.add(cursor)
            ids.append(cursor)
            cursor = self.nodes[cursor].parent
        ids.reverse()
        return ids

    def path_turns(self) -> list[dict[str, Any]]:
        return [self.nodes[node_id].turn for node_id in self.path_node_ids()]

    def append_linear(
        self,
        turn: dict[str, Any],
        ui: list[dict[str, Any]] | None = None,
    ) -> str:
        existing = [
            int(k[2:])
            for k in self.nodes
            if k.startswith("n_") and k[2:].isdigit()
        ]
        seq = max(existing, default=0) + 1
        node_id = f"n_{seq:04d}"
        self.nodes[node_id] = ConversationNode(
            parent=self.current_leaf, turn=turn, ui=ui
        )
        self.current_leaf = node_id
        self.updated_at = utcnow()
        return node_id


def new_conversation_id() -> str:
    # Time-prefixed for rough sortability; token for uniqueness.
    # (Avoids a ULID dependency. Ordering in the UI always comes from
    # updated_at, never from the id.)
    return f"c_{int(time.time() * 1000):013x}{secrets.token_hex(5)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
