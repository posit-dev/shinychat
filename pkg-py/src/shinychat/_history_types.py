from __future__ import annotations

import copy
import secrets
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, JsonValue, model_validator

from ._attachments import Attachment
from ._chat_types import (
    ContentType,
    Role,
    SerializedDep,
    StoredMessage,
    StoredSegment,
    StructuredBlock,
)
from ._typing_extensions import NotRequired, TypedDict


class TurnDict(TypedDict):
    """A JSON-serialized chat turn dict.

    Matches the shape of ``chatlas.Turn.model_dump(mode="json")`` and the
    plain dicts that non-chatlas clients return from ``get_turns()``. The
    keys this codebase reads are ``role`` (a string), ``contents``
    (chatlas content-item dicts), and ``content`` (plain-text content on
    generic dicts). Extra keys are allowed at runtime.
    """

    role: NotRequired[str]
    contents: NotRequired[list[Any]]
    content: NotRequired[Any]


TitleSource = Literal["llm", "user"]

# The blessed state-entry name for the turn-state capture/restore hooks.
TURNS_STATE_KEY = "shinychat:turns"

MAX_HISTORY_ERROR_MESSAGE = 256
HISTORY_ERROR_GENERIC = "The response could not be completed."
HISTORY_ERROR_STREAM_START = "The response stream could not be started."
HISTORY_ERROR_STREAM_TERMINAL = "The response stream could not be completed."
HISTORY_ERROR_MESSAGES = frozenset(
    {
        HISTORY_ERROR_GENERIC,
        HISTORY_ERROR_STREAM_START,
        HISTORY_ERROR_STREAM_TERMINAL,
    }
)


def normalize_history_error_message(message: str | None) -> str:
    """Return the bounded, catalogue-backed error summary for persistence."""
    value = unicodedata.normalize("NFC", message or "")
    value = "".join(
        " "
        if unicodedata.category(char) in {"Cc", "Cf"}
        or char in {"\u2028", "\u2029"}
        else char
        for char in value
    )
    value = " ".join(value.split()).strip()
    if not value:
        value = HISTORY_ERROR_GENERIC
    if len(value) > MAX_HISTORY_ERROR_MESSAGE:
        value = f"{value[: MAX_HISTORY_ERROR_MESSAGE - 3]}..."
    return value


def project_history_error_message(message: str | None) -> str:
    """Project only a normalized safe catalogue value to the browser."""
    value = normalize_history_error_message(message)
    return value if value in HISTORY_ERROR_MESSAGES else HISTORY_ERROR_GENERIC


class StoredSegmentDict(TypedDict):
    """Serialized form of a ``StoredSegment`` (``model_dump(exclude_none=True)``)."""

    content: str
    content_type: ContentType
    html_deps: NotRequired[list[SerializedDep]]


class AttachmentDict(TypedDict):
    """Serialized form of an :class:`~shinychat._attachments.Attachment`."""

    mime: str
    name: str
    size: int
    data_url: str


class StoredUiMessage(TypedDict):
    """A serialized :class:`StoredMessage` persisted in a node's ``ui`` list.

    Matches ``StoredMessage.model_dump(exclude_none=True)`` plus the
    ``version`` marker. ``segments`` is interleaved: string segment dicts
    and structured blocks in content order. Empty ``attachments`` is
    dropped, so it is ``NotRequired``.
    """

    role: Role
    segments: list[StoredSegmentDict | StructuredBlock]
    version: int
    attachments: NotRequired[list[AttachmentDict]]
    attachment_content_stripped: NotRequired[bool]


def new_conversation_record(
    *, title: str, id: str | None = None
) -> ConversationRecordV1:
    now = utcnow()
    return ConversationRecordV1(
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

# Version marker on stored UI message dicts. The marker's presence, not its
# value, is what counts. Old or absent markers are discarded and re-derived
# from turns at replay time.
STORED_UI_VERSION = 1


def is_stored_ui_versioned(ui: list[dict[str, Any]] | None) -> bool:
    """Whether a node's stored UI carries the version marker.

    Checks the first message only. Derived messages always lead a node's
    UI list. Unversioned entries after them are client-snapshot messages
    preserved from the save-time snapshot.
    """
    if not ui:
        return False
    first = ui[0]
    return isinstance(first, dict) and first.get("version") is not None


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


class ConversationRecordV1(BaseModel):
    """The legacy v1 linear record (py 0.6.x-0.7.2, R 0.5.0).

    Kept as import input for the v1→v2 upgrade (plan section 7.6); the
    current record version is named by :class:`ConversationRecord`.
    """

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

    def path_turns(self) -> list[TurnDict]:
        return cast(
            list[TurnDict],
            [
                turn
                for node_id in self.path_node_ids()
                for turn in self.nodes[node_id].turns
            ],
        )

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
    segments: list[StoredSegment | StructuredBlock]
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
            segments=[copy.deepcopy(segment) for segment in message.segments],
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
            segments=[copy.deepcopy(segment) for segment in self.segments],
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

    def children_of(self, node_id: str | None) -> list[str]:
        if node_id is None:
            return [
                child_id
                for child_id, node in self.nodes.items()
                if node.parent_id is None
            ]
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {node_id!r}")
        return list(node.children)

    def siblings_of(self, node_id: str) -> list[str]:
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Unknown exchange id {node_id!r}")
        return self.children_of(node.parent_id)

    def set_active_leaf(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ValueError(f"Unknown exchange id {node_id!r}")

        path: list[str] = []
        visited: set[str] = set()
        cursor: str | None = node_id
        while cursor is not None:
            if cursor in visited:
                raise ValueError(
                    f"Cycle detected in conversation nodes at {cursor!r}"
                )
            node = self.nodes.get(cursor)
            if node is None:
                raise ValueError(f"Dangling parent reference at {cursor!r}")
            visited.add(cursor)
            path.append(cursor)
            cursor = node.parent_id
        path.reverse()

        self.active_leaf = node_id
        for index, path_node_id in enumerate(path):
            self.nodes[path_node_id].selected_child = (
                path[index + 1] if index + 1 < len(path) else None
            )
        self.updated_at = utcnow()

    def subtree_leaf(self, node_id: str) -> str:
        if node_id not in self.nodes:
            raise ValueError(f"Unknown exchange id {node_id!r}")

        current = node_id
        visited: set[str] = set()
        while True:
            if current in visited:
                raise ValueError(
                    f"Cycle detected in selected-child pointers at {current!r}"
                )
            visited.add(current)
            children = self.children_of(current)
            if not children:
                return current

            selected = self.nodes[current].selected_child
            if selected in children:
                current = selected
                continue

            current = max(
                enumerate(children),
                key=lambda item: (self.nodes[item[1]].created_at, item[0]),
            )[1]

    def exchange_id_for_user_message_index(self, index: int) -> str:
        if index < 0:
            raise IndexError(f"Message index {index} out of range")

        displayed_index = 0
        for node_id in self.path_node_ids():
            node = self.nodes[node_id]
            if node.input is not None:
                if displayed_index == index:
                    return node_id
                displayed_index += 1
            displayed_index += len(node.messages)
        raise IndexError(f"Message index {index} out of range")

    def path_sibling_metadata(self) -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        for node_id in self.path_node_ids():
            siblings = self.siblings_of(node_id)
            if len(siblings) > 1:
                result[node_id] = (siblings.index(node_id), len(siblings))
        return result

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
        node.status = "pending"
        node.error = None
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
        node.error = (
            ErrorEntry(message=project_history_error_message(error))
            if status == "error"
            else None
        )
        self.updated_at = utcnow()


# Keys that appear on v1 nodes but never on v2 exchange data. v2 nodes say
# `parent_id` where v1 says `parent`, and v1 carries `turns` (raw 0.6.x disk
# nodes say `turn_ids`) plus an optional `ui` render cache. `children` and
# `selected_child` exist in both, so they are not discriminative.
_V1_ONLY_NODE_KEYS = frozenset({"parent", "turns", "ui", "turn_ids"})


def _is_v1_shaped(data: dict[str, Any]) -> bool:
    """Whether a `schema_version`-less dict is v1-shaped.

    Records that predate the schema_version marker are v1
    (check_schema_version's None→1 convention), but so is markerless v2
    input built against the current model, so shape decides: `current_leaf`
    is the one v1-only top-level key (v2 says `active_leaf`), and v1 nodes
    carry the keys in _V1_ONLY_NODE_KEYS. Absent every v1 signal the dict
    is treated as v2 -- the current version, and the class validating it.
    """
    if "current_leaf" in data:
        return True
    nodes = data.get("nodes")
    if isinstance(nodes, dict):
        for node in nodes.values():
            if isinstance(node, ConversationNode):
                return True
            if isinstance(node, dict) and _V1_ONLY_NODE_KEYS & node.keys():
                return True
    return False


class ConversationRecord(ConversationRecordV2):
    """The CURRENT conversation record version (v2).

    This name always tracks the current schema; the released forms are
    named by their versions (`ConversationRecordV1`, `ConversationRecordV2`).
    It is the validation/construction entry point, not the runtime record
    type: the controller and recorder build plain `ConversationRecordV2`
    objects, which is the type stores receive in `put()` and should
    isinstance-check against. Validating v1-shaped input -- a v1 dict or
    model instance -- runs the v1→v2 import (plan section 7.6, decision
    D1), so custom stores written against the v1 API that call
    `ConversationRecord.model_validate*` keep working and receive a v2
    record. Stores may also hand back a `ConversationRecordV1` instance
    directly; the controller upgrades it on read. Lossy-import warnings
    are discarded here (reads must not re-warn); use
    `import_v1_record_with_warnings` to collect them.
    """

    @model_validator(mode="before")
    @classmethod
    def _upgrade_v1(cls, data: Any) -> Any:
        # Deferred import: _history_v1 imports this module, so a
        # top-level import would be circular.
        from ._history_v1 import import_v1_record

        if isinstance(data, ConversationRecordV1):
            # The import yields a ConversationRecordV2, which pydantic will
            # not accept as model input for this subclass; hand validation a
            # dict re-built from the imported record.
            return import_v1_record(data).model_dump()
        if isinstance(data, ConversationRecordV2) and not isinstance(
            data, ConversationRecord
        ):
            # A plain v2 instance (built by the controller/recorder, or
            # cached by a store) is already current; pydantic refuses a
            # base-class instance as input for this subclass, so hand
            # validation an equal dict instead.
            return data.model_dump()
        if isinstance(data, dict):
            # An explicit `schema_version: 1` is always v1. A missing marker
            # means the record predates it (check_schema_version's None→1
            # convention) -- but only when the dict is v1-shaped, since v2
            # kwargs built without the marker are current-version input, not
            # v1. Invalid v1 input raises here as a ConversationRecordV1
            # error, the same shape the v1-era model gave.
            version = data.get("schema_version")
            if version == 1 or (version is None and _is_v1_shaped(data)):
                return import_v1_record(
                    ConversationRecordV1.model_validate(data)
                ).model_dump()
        return data


def new_conversation_record_v2(
    *,
    title: str,
    client_info: dict[str, str],
    id: str | None = None,
) -> ConversationRecordV2:
    now = utcnow()
    root_id = "n_0000"
    return ConversationRecordV2(
        id=id or new_conversation_id(),
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
