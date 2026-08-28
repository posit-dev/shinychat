from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from ._history_bookmark import global_save_dir_fn
from ._history_types import (
    ConversationMeta,
    ConversationNode,
    ConversationRecord,
    ConversationRecordV2,
    check_schema_version,
)

logger = logging.getLogger(__name__)

HISTORY_BOOKMARK_ID = "shinychat-conversations"


@dataclasses.dataclass(frozen=True)
class ConversationPartition:
    """Storage partition for a chat history collection.

    `chat_id` is the resolved/namespaced chat id. `scope` is the owner
    namespace: explicit scope, authenticated user, or browser token.
    """

    chat_id: str
    scope: str


class ConversationStore(ABC):
    """
    Storage interface for chat conversation history.

    Conversations are partitioned by `ConversationPartition`. Implement the
    four abstract methods to plug any backend into `Chat.enable_history()`.
    """

    @abstractmethod
    async def list(
        self, partition: ConversationPartition
    ) -> list[ConversationMeta]:
        """All conversations in `partition`, newest-first (by created_at)."""

    @abstractmethod
    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> Any:
        """Full record, or None if missing."""

    @abstractmethod
    async def put(
        self,
        partition: ConversationPartition,
        record: Any,
    ) -> None:
        """Upsert. Rename = mutate record.title and put()."""

    @abstractmethod
    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        """Remove a conversation. Missing ids are a no-op."""

    async def search(
        self, partition: ConversationPartition, query: str
    ) -> list[ConversationMeta]:
        q = query.casefold()
        return [
            m for m in await self.list(partition) if q in m.title.casefold()
        ]

    async def total_size(self, partition: ConversationPartition) -> int:
        """Total bytes used by all conversations in partition.

        Derived from `list()`'s per-record `size_bytes` — backends don't
        need to override this unless they have a cheaper way to compute it.
        """
        return sum(m.size_bytes for m in await self.list(partition))


@dataclasses.dataclass
class _WriteState:
    turn_seq_map: dict[str, list[int]] = dataclasses.field(default_factory=dict)
    # node_id -> digest of the UI messages last persisted for that node.
    # ui.jsonl is last-write-wins, so any content change must re-append the
    # complete current UI, even if its message count did not change.
    ui_node_digest: dict[str, str] = dataclasses.field(default_factory=dict)
    next_turn_seq: int = 0


def _json_digest(value: object) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _append_jsonl(path: Path, lines: list[str]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        if lines:
            f.write("\n".join(lines) + "\n")


def _rollback_jsonl(path: Path, *, existed: bool, size: int) -> None:
    if existed:
        with open(path, "r+b") as f:
            f.truncate(size)
    else:
        path.unlink(missing_ok=True)


def _check_record_for_store(
    record: Any,
) -> ConversationRecord | ConversationRecordV2:
    if not isinstance(record, (ConversationRecord, ConversationRecordV2)):
        raise TypeError("Conversation stores require a supported record model.")
    version = check_schema_version(record.schema_version)
    if (
        isinstance(record, ConversationRecord)
        and version != 1
        or isinstance(record, ConversationRecordV2)
        and version != 2
    ):
        raise ValueError(
            "Conversation record model does not match its schema version."
        )
    return record


class FileConversationStore(ConversationStore):
    """
    Default store: each conversation is a directory at
    ``<dir>/<chat_id>/<scope>/<id>/`` containing ``record.json``,
    ``turns.jsonl``, and ``ui.jsonl``.

    ``record.json`` holds tree structure and metadata (small, rewritten
    atomically on every save). ``turns.jsonl`` and ``ui.jsonl`` are
    append-only — new turns and UI entries are appended, never rewritten.

    Temporary records and journal rollback protect against ordinary I/O
    failures, but this store does not fsync files or directories. It also
    does not coordinate concurrent access across processes; callers must
    serialize reads and writes for each conversation.

    On ``get()``, the three files are read and merged into a full
    ``ConversationRecord`` with inline turns and UI on each node. Callers
    never see the split.
    """

    def __init__(self, dir: str | Path | None = None):
        self._dir: Path | None = Path(dir) if dir is not None else None
        self._meta_cache: dict[
            ConversationPartition, list[ConversationMeta]
        ] = {}
        self._write_state: dict[
            tuple[ConversationPartition, str], _WriteState
        ] = {}

    def _ws_key(
        self, partition: ConversationPartition, conv_id: str
    ) -> tuple[ConversationPartition, str]:
        return (partition, conv_id)

    def _get_or_init_write_state(
        self, partition: ConversationPartition, conv_id: str, conv_dir: Path
    ) -> _WriteState:
        key = self._ws_key(partition, conv_id)
        if key in self._write_state:
            return self._write_state[key]
        ws = _WriteState()
        turns_file = conv_dir / "turns.jsonl"
        if turns_file.is_file():
            lines = turns_file.read_text(encoding="utf-8").strip().splitlines()
            ws.next_turn_seq = len(lines)

        record_file = conv_dir / "record.json"
        if record_file.is_file():
            raw = json.loads(record_file.read_text(encoding="utf-8"))
            for nid, node_data in raw.get("nodes", {}).items():
                turn_ids = node_data.get("turn_ids", [])
                if turn_ids:
                    ws.turn_seq_map[nid] = turn_ids
        ui_file = conv_dir / "ui.jsonl"
        if ui_file.is_file():
            for line_number, line in enumerate(
                ui_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if (
                        not isinstance(entry, dict)
                        or not isinstance(entry.get("node_id"), str)
                        or not isinstance(entry.get("data"), list)
                    ):
                        raise ValueError("expected node_id and data")
                    ws.ui_node_digest[entry["node_id"]] = _json_digest(
                        entry["data"]
                    )
                except (
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    logger.warning(
                        "Skipping malformed JSONL line %s:%d",
                        ui_file,
                        line_number,
                    )
        self._write_state[key] = ws
        return ws

    async def list(
        self, partition: ConversationPartition
    ) -> list[ConversationMeta]:
        if partition in self._meta_cache:
            return list(self._meta_cache[partition])
        partition_dir = await self._partition_dir(partition)
        metas: list[ConversationMeta] = []
        if partition_dir.is_dir():
            for d in partition_dir.iterdir():
                record_file = d / "record.json"
                if not d.is_dir() or not record_file.is_file():
                    continue
                try:
                    raw = json.loads(record_file.read_text(encoding="utf-8"))
                    schema_version = check_schema_version(
                        raw.get("schema_version")
                    )
                    if schema_version == 2:
                        rec = ConversationRecordV2.model_validate(raw)
                        size_bytes = sum(
                            f.stat().st_size for f in d.iterdir() if f.is_file()
                        )
                        metas.append(rec.meta(size_bytes=size_bytes))
                        continue
                    nodes_raw = raw.get("nodes", {})
                    nodes = {}
                    for nid, nd in nodes_raw.items():
                        nodes[nid] = ConversationNode(
                            parent=nd.get("parent"),
                            children=nd.get("children", []),
                            turns=[],
                        )
                    rec = ConversationRecord(
                        id=raw["id"],
                        title=raw["title"],
                        title_source=raw.get("title_source"),
                        created_at=raw["created_at"],
                        updated_at=raw["updated_at"],
                        client_info=raw.get("client_info", {}),
                        nodes=nodes,
                        next_node_seq=raw.get("next_node_seq", 1),
                        current_leaf=raw.get("current_leaf"),
                        values=raw.get("values", {}),
                        bookmark_state_id=raw.get("bookmark_state_id"),
                    )
                    size_bytes = sum(
                        f.stat().st_size for f in d.iterdir() if f.is_file()
                    )
                    metas.append(rec.meta(size_bytes=size_bytes))
                except Exception as e:
                    logger.warning("Unreadable conversation %s: %s", d.name, e)
                    continue
            metas.sort(key=lambda m: m.created_at, reverse=True)
        self._meta_cache[partition] = metas
        return list(metas)

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> Any:
        conv_dir = safe_conv_path(await self._partition_dir(partition), conv_id)
        record_file = conv_dir / "record.json"
        if not record_file.is_file():
            # Cache may be stale (e.g. another worker deleted this
            # conversation) — drop it so the next list() re-reads disk.
            self._meta_cache.pop(partition, None)
            return None

        raw = json.loads(record_file.read_text(encoding="utf-8"))
        schema_version = check_schema_version(raw.get("schema_version"))
        if schema_version == 2:
            return ConversationRecordV2.model_validate(raw)

        turns_map: dict[int, dict[str, Any]] = {}
        turns_file = conv_dir / "turns.jsonl"
        if turns_file.is_file():
            for line_number, line in enumerate(
                turns_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if (
                        not isinstance(entry, dict)
                        or type(entry.get("seq")) is not int
                        or not isinstance(entry.get("data"), dict)
                    ):
                        raise ValueError("expected seq and data")
                    turns_map[entry["seq"]] = entry["data"]
                except (
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    logger.warning(
                        "Skipping malformed JSONL line %s:%d",
                        turns_file,
                        line_number,
                    )

        ui_map: dict[str, list[dict[str, Any]]] = {}
        ui_file = conv_dir / "ui.jsonl"
        if ui_file.is_file():
            for line_number, line in enumerate(
                ui_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if (
                        not isinstance(entry, dict)
                        or not isinstance(entry.get("node_id"), str)
                        or not isinstance(entry.get("data"), list)
                    ):
                        raise ValueError("expected node_id and data")
                    ui_map[entry["node_id"]] = entry["data"]
                except (
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    logger.warning(
                        "Skipping malformed JSONL line %s:%d",
                        ui_file,
                        line_number,
                    )

        nodes: dict[str, ConversationNode] = {}
        for nid, node_data in raw.get("nodes", {}).items():
            turn_ids = node_data.get("turn_ids", [])
            turns = [turns_map[tid] for tid in turn_ids if tid in turns_map]
            nodes[nid] = ConversationNode(
                parent=node_data.get("parent"),
                children=node_data.get("children", []),
                turns=turns,
                ui=ui_map.get(nid),
                selected_child=node_data.get("selected_child"),
            )

        return ConversationRecord(
            id=raw["id"],
            title=raw["title"],
            title_source=raw.get("title_source"),
            response_count=raw.get("response_count", 0),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            client_info=raw.get("client_info", {}),
            nodes=nodes,
            next_node_seq=raw.get("next_node_seq", 1),
            current_leaf=raw.get("current_leaf"),
            values=raw.get("values", {}),
            bookmark_state_id=raw.get("bookmark_state_id"),
        )

    async def put(
        self,
        partition: ConversationPartition,
        record: Any,
    ) -> None:
        record = _check_record_for_store(record)

        partition_dir = await self._partition_dir(partition)
        conv_dir = safe_conv_path(partition_dir, record.id)
        # Validate the on-disk schema version before creating/modifying
        # anything, so an unsupported existing record is rejected fail-closed
        # rather than partially overwritten.
        record_file = conv_dir / "record.json"
        if record_file.is_file():
            raw = json.loads(record_file.read_text(encoding="utf-8"))
            existing_schema_version = check_schema_version(
                raw.get("schema_version")
            )
            if existing_schema_version != record.schema_version:
                raise ValueError(
                    "Cannot overwrite a conversation record with a different "
                    "schema version."
                )

        if isinstance(record, ConversationRecordV2):
            await self._put_v2(partition, record, conv_dir)
            return

        conv_dir.mkdir(parents=True, exist_ok=True)

        ws_key = self._ws_key(partition, record.id)
        had_write_state = ws_key in self._write_state
        ws = self._get_or_init_write_state(partition, record.id, conv_dir)
        staged_ws = dataclasses.replace(
            ws,
            turn_seq_map={
                nid: list(turn_ids) for nid, turn_ids in ws.turn_seq_map.items()
            },
            ui_node_digest=dict(ws.ui_node_digest),
        )

        new_turns_lines: list[str] = []
        new_ui_lines: list[str] = []
        record_nodes: dict[str, dict[str, Any]] = {}

        for nid, node in record.nodes.items():
            if nid not in staged_ws.turn_seq_map:
                turn_ids: list[int] = []
                for turn_data in node.turns:
                    seq = staged_ws.next_turn_seq
                    staged_ws.next_turn_seq += 1
                    turn_ids.append(seq)
                    new_turns_lines.append(
                        json.dumps(
                            {"seq": seq, "data": turn_data},
                            ensure_ascii=False,
                        )
                    )
                staged_ws.turn_seq_map[nid] = turn_ids
            if node.ui is not None:
                ui_digest = _json_digest(node.ui)
                if ui_digest != staged_ws.ui_node_digest.get(nid):
                    new_ui_lines.append(
                        json.dumps(
                            {"node_id": nid, "data": node.ui},
                            ensure_ascii=False,
                        )
                    )
                    staged_ws.ui_node_digest[nid] = ui_digest
            record_nodes[nid] = {
                "parent": node.parent,
                "children": node.children,
                "turn_ids": staged_ws.turn_seq_map.get(nid, []),
                "selected_child": node.selected_child,
            }

        record_data = {
            "schema_version": record.schema_version,
            "id": record.id,
            "title": record.title,
            "title_source": record.title_source,
            "response_count": record.response_count,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "client_info": record.client_info,
            "next_node_seq": record.next_node_seq,
            "current_leaf": record.current_leaf,
            "nodes": record_nodes,
            "values": record.values,
            "bookmark_state_id": record.bookmark_state_id,
        }
        record_json = json.dumps(record_data, ensure_ascii=False)

        turns_file = conv_dir / "turns.jsonl"
        ui_file = conv_dir / "ui.jsonl"
        jsonl_snapshots = [
            (
                path,
                path.exists(),
                path.stat().st_size if path.exists() else 0,
            )
            for path in (turns_file, ui_file)
        ]
        tmp = conv_dir / ".record.json.tmp"
        try:
            # Serialize and write the replacement record before appending
            # journal entries. A later append or rename failure rolls those
            # entries back to these snapshots.
            tmp.write_text(record_json, encoding="utf-8")
            _append_jsonl(turns_file, new_turns_lines)
            _append_jsonl(ui_file, new_ui_lines)
            os.replace(tmp, record_file)
        except Exception:
            for path, existed, size in reversed(jsonl_snapshots):
                _rollback_jsonl(path, existed=existed, size=size)
            tmp.unlink(missing_ok=True)
            if not had_write_state:
                self._write_state.pop(ws_key, None)
            raise

        self._write_state[ws_key] = staged_ws

        if partition in self._meta_cache:
            size_bytes = sum(
                f.stat().st_size for f in conv_dir.iterdir() if f.is_file()
            )
            updated = [
                m for m in self._meta_cache[partition] if m.id != record.id
            ]
            updated.append(record.meta(size_bytes=size_bytes))
            updated.sort(key=lambda m: m.created_at, reverse=True)
            self._meta_cache[partition] = updated

    async def _put_v2(
        self,
        partition: ConversationPartition,
        record: ConversationRecordV2,
        conv_dir: Path,
    ) -> None:
        """Write the v2 logical record through one atomic file replacement."""
        conv_dir.mkdir(parents=True, exist_ok=True)
        record_file = conv_dir / "record.json"
        tmp = conv_dir / ".record.json.tmp"
        try:
            tmp.write_text(
                record.model_dump_json(exclude_none=True), encoding="utf-8"
            )
            os.replace(tmp, record_file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        if partition in self._meta_cache:
            size_bytes = record_file.stat().st_size
            updated = [
                m for m in self._meta_cache[partition] if m.id != record.id
            ]
            updated.append(record.meta(size_bytes=size_bytes))
            updated.sort(key=lambda m: m.updated_at, reverse=True)
            self._meta_cache[partition] = updated

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        conv_dir = safe_conv_path(await self._partition_dir(partition), conv_id)
        if conv_dir.is_dir():
            shutil.rmtree(conv_dir)
        key = self._ws_key(partition, conv_id)
        self._write_state.pop(key, None)
        if partition in self._meta_cache:
            self._meta_cache[partition] = [
                m for m in self._meta_cache[partition] if m.id != conv_id
            ]

    async def _partition_dir(self, partition: ConversationPartition) -> Path:
        if self._dir is None:
            self._dir = await resolve_history_dir()
        return (
            self._dir
            / sanitize_scope(partition.chat_id)
            / sanitize_scope(partition.scope)
        )


class InMemoryConversationStore(ConversationStore):
    """
    Ephemeral store: conversations live in process memory, lost on restart.

    The default when ``SHINY_DEV_MODE=1``. Useful for development, testing,
    and apps where per-session history is sufficient.
    """

    def __init__(self) -> None:
        self._data: dict[
            ConversationPartition,
            dict[str, ConversationRecord | ConversationRecordV2],
        ] = {}
        self._meta_cache: dict[
            ConversationPartition, list[ConversationMeta]
        ] = {}

    async def list(
        self, partition: ConversationPartition
    ) -> list[ConversationMeta]:
        if partition in self._meta_cache:
            return list(self._meta_cache[partition])
        metas = [
            r.meta(size_bytes=len(r.model_dump_json().encode("utf-8")))
            for r in self._data.get(partition, {}).values()
        ]
        metas.sort(key=lambda m: m.created_at, reverse=True)
        self._meta_cache[partition] = metas
        return list(metas)

    async def get(
        self, partition: ConversationPartition, conv_id: str
    ) -> Any:
        return self._data.get(partition, {}).get(conv_id)

    async def put(
        self,
        partition: ConversationPartition,
        record: Any,
    ) -> None:
        record = _check_record_for_store(record)

        if partition not in self._data:
            self._data[partition] = {}
        existing = self._data[partition].get(record.id)
        if existing is not None:
            existing = _check_record_for_store(existing)
            if existing.schema_version != record.schema_version:
                raise ValueError(
                    "Cannot overwrite a conversation record with a different "
                    "schema version."
                )
        self._data[partition][record.id] = record

        # Only touched-record work — mirrors FileConversationStore.put(), so
        # a warm cache stays warm without resumming/reserializing everything
        # in partition (the cost _evict_if_needed would otherwise pay every turn).
        if partition in self._meta_cache:
            size_bytes = len(record.model_dump_json().encode("utf-8"))
            updated = [
                m for m in self._meta_cache[partition] if m.id != record.id
            ]
            updated.append(record.meta(size_bytes=size_bytes))
            updated.sort(key=lambda m: m.created_at, reverse=True)
            self._meta_cache[partition] = updated

    async def delete(
        self, partition: ConversationPartition, conv_id: str
    ) -> None:
        self._data.get(partition, {}).pop(conv_id, None)
        if partition in self._meta_cache:
            self._meta_cache[partition] = [
                m for m in self._meta_cache[partition] if m.id != conv_id
            ]


AUTO_DEV_MEMORY_STORE: dict[str, InMemoryConversationStore] = {}


def auto_dev_memory_store() -> InMemoryConversationStore:
    store = AUTO_DEV_MEMORY_STORE.get("store")
    if store is None:
        store = InMemoryConversationStore()
        AUTO_DEV_MEMORY_STORE["store"] = store
    return store


def resolve_store(
    store: "ConversationStore | Literal['auto', 'memory', 'file']",
) -> ConversationStore:
    if isinstance(store, ConversationStore):
        return store
    if store == "memory":
        return InMemoryConversationStore()
    if store == "file":
        return FileConversationStore()
    # "auto": use in-memory for dev, file-based for production
    if os.getenv("SHINY_DEV_MODE") == "1":
        logger.info(
            "Chat history: using in-memory storage (dev mode). "
            "History is lost on restart. To persist across restarts, "
            "pass history=HistoryOptions(store='file') to Chat()."
        )
        return auto_dev_memory_store()
    logger.info(
        "Chat history: using file-based storage. "
        "To use in-memory storage instead, "
        "pass history=HistoryOptions(store='memory') to Chat()."
    )
    return FileConversationStore()


CONV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def sanitize_scope(scope: str) -> str:
    # Dots are excluded to prevent path-traversal sequences like ".."
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", scope)[:40]
    digest = hashlib.sha256(scope.encode()).hexdigest()[:12]
    return f"{safe}-{digest}"


def safe_conv_path(scope_dir: Path, conv_id: str) -> Path:
    if not CONV_ID_RE.fullmatch(conv_id):
        raise ValueError(f"Invalid conversation id: {conv_id!r}")
    return scope_dir / conv_id


async def resolve_history_dir() -> Path:
    """
    Resolve the default conversation directory.

    Order:
    1. `CONNECT_CONTENT_DATA_DIR` (Connect's persistent per-content dir,
       Early Access, on-prem).
    2. Shiny's global bookmark save-dir function, requesting a reserved id.
       Connect and Connect Cloud register this fn to point at the persistent,
       redeploy-safe bookmarks area — piggybacking on it gives history the
       same persistence guarantees as server bookmarks, with zero config.
    3. `.shinychat/conversations/` (plain local dev).
    """
    env = os.environ.get("CONNECT_CONTENT_DATA_DIR")
    if env:
        return Path(env) / HISTORY_BOOKMARK_ID

    save_dir_fn = global_save_dir_fn()
    if save_dir_fn is not None:
        # set_global_save_dir_fn already wraps with wrap_async, so fn is async.
        # Registrants may return str despite the Path annotation; coerce defensively.
        return Path(await save_dir_fn(HISTORY_BOOKMARK_ID))

    return Path(".shinychat") / "conversations"
