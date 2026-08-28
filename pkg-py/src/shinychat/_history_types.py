from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, JsonValue

from ._attachments import Attachment
from ._chat_types import StoredMessage, StoredSegment

TitleSource = Literal["llm", "user"]


def new_conversation_record(
    *, title: str, id: str | None = None
) -> ConversationRecord:
    now = utcnow()
    return ConversationRecord(
        id=id if id is not None else new_conversation_id(),
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
    # Which child was last on the active path below this node. Lets
    # subtree_leaf() return to the descendant the user last viewed inside this
    # subtree when they navigate back into it, instead of the newest leaf.
    # None => never descended here (or leaf) => fall back to newest child.
    selected_child: str | None = None

    def ui_message_count(self) -> int:
        # Rendered message count for this node. Must mirror replay_ui's
        # `node.ui or [<fallback>]`: a missing/empty `ui` still renders one
        # fabricated message, so index math (node_id_for_message_index,
        # _send_sibling_metadata) stays aligned with the replayed UI.
        return len(self.ui) if self.ui else 1


MIN_SCHEMA_VERSION = 1
MAX_SCHEMA_VERSION = 2


class UnsupportedSchemaVersionError(ValueError):
    def __init__(self, version: object) -> None:
        super().__init__(
            f"Unsupported conversation record schema version: {version!r} "
            f"(supported: {MIN_SCHEMA_VERSION}-{MAX_SCHEMA_VERSION})"
        )


def check_schema_version(version: object) -> int:
    # None means the record predates schema_version entirely; treat as 1.
    version = 1 if version is None else version
    if (
        type(version) is int
        and MIN_SCHEMA_VERSION <= version <= MAX_SCHEMA_VERSION
    ):
        return version
    raise UnsupportedSchemaVersionError(version)


class ConversationRecord(BaseModel):
    schema_version: Literal[1] = 1
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

    def set_current_leaf(self, node_id: str | None) -> None:
        # Move the active leaf and record, at every node on the new path, which
        # child leads toward that leaf. subtree_leaf() replays those pointers so
        # navigating back into a sibling subtree returns to the last-viewed
        # descendant. Off-path nodes are untouched, so each subtree keeps its
        # own remembered position.
        self.current_leaf = node_id
        path = self.path_node_ids()
        for i, nid in enumerate(path):
            self.nodes[nid].selected_child = (
                path[i + 1] if i + 1 < len(path) else None
            )

    def subtree_leaf(self, node_id: str) -> str:
        children = self.children_of(node_id)
        if not children:
            return node_id
        selected = self.nodes[node_id].selected_child
        next_id = selected if selected in children else children[-1]
        return self.subtree_leaf(next_id)

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
            n_ui = self.nodes[nid].ui_message_count()
            if index < cumulative + n_ui:
                return nid, i
            cumulative += n_ui
        raise IndexError(f"Message index {index} out of range")

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
        self.set_current_leaf(node_id)
        self.updated_at = utcnow()
        return node_id


class CapturedMessage(BaseModel):
    """A server-authored message spec captured after a successful wire send."""

    role: Literal["user", "assistant"]
    segments: list[StoredSegment]
    icon: str | None = None
    attachments: list[Attachment] | None = None

    @classmethod
    def from_stored_message(
        cls, message: StoredMessage, *, icon: str | None
    ) -> CapturedMessage:
        if message.role not in ("user", "assistant"):
            raise ValueError(
                "Only user and assistant messages can be captured in an exchange."
            )
        return cls(
            role=message.role,
            segments=[segment.model_copy(deep=True) for segment in message.segments],
            icon=icon,
            attachments=(
                [attachment.model_copy(deep=True) for attachment in message.attachments]
                if message.attachments
                else None
            ),
        )

    def as_stored_message(self) -> StoredMessage:
        return StoredMessage(
            role=self.role,
            segments=[segment.model_copy(deep=True) for segment in self.segments],
            attachments=(
                [attachment.model_copy(deep=True) for attachment in self.attachments]
                if self.attachments is not None
                else []
            ),
        )


class StateEntry(BaseModel):
    kind: str
    version: int
    mode: Literal["delta", "snapshot"]
    data: JsonValue


class ErrorEntry(BaseModel):
    message: str


class ExchangeNode(BaseModel):
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    selected_child: str | None = None
    created_at: datetime
    status: Literal["pending", "ok", "error", "cancelled"]
    input: StoredMessage | None = None
    messages: list[CapturedMessage] = Field(default_factory=list)
    state: dict[str, StateEntry] = Field(default_factory=dict)
    error: ErrorEntry | None = None


class ConversationRecordV2(BaseModel):
    """The v2 exchange-tree record, isolated from the released v1 model."""

    schema_version: Literal[2] = 2
    id: str
    title: str
    title_source: TitleSource | None = None
    response_count: int = 0
    created_at: datetime
    updated_at: datetime
    client_info: dict[str, str] = Field(default_factory=dict)
    nodes: dict[str, ExchangeNode] = Field(default_factory=dict)
    next_node_seq: int = 1
    active_leaf: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    bookmark_state_id: str | None = None

    def meta(self, *, size_bytes: int) -> ConversationMeta:
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
        cursor = self.active_leaf
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
            cursor = node.parent_id
        ids.reverse()
        return ids

    def open_exchange(self, exchange_id: str, message: StoredMessage) -> None:
        if exchange_id in self.nodes:
            raise ValueError(f"Duplicate exchange id {exchange_id!r}")
        parent_id = self.active_leaf
        self.nodes[exchange_id] = ExchangeNode(
            parent_id=parent_id,
            created_at=utcnow(),
            status="pending",
            input=message.model_copy(deep=True),
        )
        if parent_id is not None:
            self.nodes[parent_id].children.append(exchange_id)
            self.nodes[parent_id].selected_child = exchange_id
        self.active_leaf = exchange_id
        self.next_node_seq += 1
        self.updated_at = utcnow()

    def open_inputless_exchange(self) -> str:
        """Open a pending child for content sent outside a user exchange."""
        exchange_id = f"n_{self.next_node_seq:04d}"
        while exchange_id in self.nodes:
            self.next_node_seq += 1
            exchange_id = f"n_{self.next_node_seq:04d}"
        parent_id = self.active_leaf
        self.nodes[exchange_id] = ExchangeNode(
            parent_id=parent_id,
            created_at=utcnow(),
            status="pending",
        )
        if parent_id is not None:
            self.nodes[parent_id].children.append(exchange_id)
            self.nodes[parent_id].selected_child = exchange_id
        self.active_leaf = exchange_id
        self.next_node_seq += 1
        self.updated_at = utcnow()
        return exchange_id

    def append_message(self, exchange_id: str, message: CapturedMessage) -> None:
        node = self.nodes.get(exchange_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        node.messages.append(message)
        if message.role == "assistant":
            node.status = "ok"
            node.error = None
        self.updated_at = utcnow()

    def append_stream_message(
        self, exchange_id: str, message: CapturedMessage
    ) -> None:
        node = self.nodes.get(exchange_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        node.messages.append(message)
        self.updated_at = utcnow()

    def replace_stream_message(
        self, exchange_id: str, message: CapturedMessage
    ) -> None:
        node = self.nodes.get(exchange_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        if not node.messages:
            raise ValueError(
                f"Cannot replace missing stream message for exchange {exchange_id!r}"
            )
        node.messages[-1] = message
        self.updated_at = utcnow()

    def finish_exchange(
        self,
        exchange_id: str,
        status: Literal["ok", "error", "cancelled"],
        error: str | None,
    ) -> None:
        node = self.nodes.get(exchange_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        node.status = status
        node.error = ErrorEntry(message=error or "") if status == "error" else None
        self.updated_at = utcnow()


def new_conversation_record_v2(
    *, title: str, client_info: dict[str, str]
) -> ConversationRecordV2:
    now = utcnow()
    root_id = "n_0000"
    return ConversationRecordV2(
        id=new_conversation_id(),
        title=title,
        created_at=now,
        updated_at=now,
        client_info=client_info,
        nodes={
            root_id: ExchangeNode(
                parent_id=None,
                created_at=now,
                status="pending",
            )
        },
        active_leaf=root_id,
    )


def new_conversation_id() -> str:
    # Time-prefixed for rough sortability; token for uniqueness.
    # (Avoids a ULID dependency. Ordering in the UI always comes from
    # updated_at, never from the id.)
    # Same-millisecond collisions are astronomically unlikely (40 bits of
    # token entropy) but not impossible; a collision would be last-writer-wins.
    return f"c_{int(time.time() * 1000):013x}{secrets.token_hex(5)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
