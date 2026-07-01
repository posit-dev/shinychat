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
)

logger = logging.getLogger(__name__)

HISTORY_BOOKMARK_ID = "shinychat-conversations"


class ConversationStore(ABC):
    """
    Storage interface for chat conversation history.

    Conversations are partitioned by `scope` (a user-identity key). Implement
    the four abstract methods to plug any backend into `Chat.enable_history()`.
    """

    @abstractmethod
    async def list(self, scope: str) -> list[ConversationMeta]:
        """All conversations in `scope`, newest-first (by updated_at)."""

    @abstractmethod
    async def get(self, scope: str, conv_id: str) -> ConversationRecord | None:
        """Full record, or None if missing."""

    @abstractmethod
    async def put(self, scope: str, record: ConversationRecord) -> None:
        """Upsert. Rename = mutate record.title and put()."""

    @abstractmethod
    async def delete(self, scope: str, conv_id: str) -> None:
        """Remove a conversation. Missing ids are a no-op."""

    async def search(self, scope: str, query: str) -> list[ConversationMeta]:
        q = query.casefold()
        return [m for m in await self.list(scope) if q in m.title.casefold()]

    async def total_size(self, scope: str) -> int:
        """Total bytes used by all conversations in scope.

        Derived from `list()`'s per-record `size_bytes` — backends don't
        need to override this unless they have a cheaper way to compute it.
        """
        return sum(m.size_bytes for m in await self.list(scope))


@dataclasses.dataclass
class _WriteState:
    turn_seq_map: dict[str, list[int]] = dataclasses.field(default_factory=dict)
    ui_node_set: set[str] = dataclasses.field(default_factory=set)
    next_turn_seq: int = 0


class FileConversationStore(ConversationStore):
    """
    Default store: each conversation is a directory at
    ``<dir>/<scope>/<id>/`` containing ``record.json``, ``turns.jsonl``,
    and ``ui.jsonl``.

    ``record.json`` holds tree structure and metadata (small, rewritten
    atomically on every save). ``turns.jsonl`` and ``ui.jsonl`` are
    append-only — new turns and UI entries are appended, never rewritten.

    On ``get()``, the three files are read and merged into a full
    ``ConversationRecord`` with inline turns and UI on each node. Callers
    never see the split.
    """

    def __init__(self, dir: str | Path | None = None):
        self._dir: Path | None = Path(dir) if dir is not None else None
        self._meta_cache: dict[str, list[ConversationMeta]] = {}
        self._write_state: dict[str, _WriteState] = {}

    def _ws_key(self, scope: str, conv_id: str) -> str:
        return f"{scope}:{conv_id}"

    def _get_or_init_write_state(
        self, scope: str, conv_id: str, conv_dir: Path
    ) -> _WriteState:
        key = self._ws_key(scope, conv_id)
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
            for line in ui_file.read_text(encoding="utf-8").strip().splitlines():
                try:
                    entry = json.loads(line)
                    ws.ui_node_set.add(entry["node_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
        self._write_state[key] = ws
        return ws

    async def list(self, scope: str) -> list[ConversationMeta]:
        if scope in self._meta_cache:
            return list(self._meta_cache[scope])
        scope_dir = await self._scope_dir(scope)
        metas: list[ConversationMeta] = []
        if scope_dir.is_dir():
            for d in scope_dir.iterdir():
                record_file = d / "record.json"
                if not d.is_dir() or not record_file.is_file():
                    continue
                try:
                    raw = json.loads(record_file.read_text(encoding="utf-8"))
                    nodes_raw = raw.get("nodes", {})
                    nodes = {}
                    for nid, nd in nodes_raw.items():
                        nodes[nid] = ConversationNode(
                            parent=nd.get("parent"),
                            children=nd.get("children", []),
                            turns=[],
                        )
                    rec = ConversationRecord(
                        schema_version=raw.get("schema_version", 1),
                        id=raw["id"],
                        title=raw["title"],
                        title_source=raw.get("title_source", "fallback"),
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
            metas.sort(key=lambda m: m.updated_at, reverse=True)
        self._meta_cache[scope] = metas
        return list(metas)

    async def get(self, scope: str, conv_id: str) -> ConversationRecord | None:
        conv_dir = safe_conv_path(await self._scope_dir(scope), conv_id)
        record_file = conv_dir / "record.json"
        if not record_file.is_file():
            # Cache may be stale (e.g. another worker deleted this
            # conversation) — drop it so the next list() re-reads disk.
            self._meta_cache.pop(scope, None)
            return None

        raw = json.loads(record_file.read_text(encoding="utf-8"))

        # Read turns
        turns_map: dict[int, dict[str, Any]] = {}
        turns_file = conv_dir / "turns.jsonl"
        if turns_file.is_file():
            for line in turns_file.read_text(encoding="utf-8").strip().splitlines():
                try:
                    entry = json.loads(line)
                    turns_map[entry["seq"]] = entry["data"]
                except (json.JSONDecodeError, KeyError):
                    continue

        # Read UI
        ui_map: dict[str, list[dict[str, Any]]] = {}
        ui_file = conv_dir / "ui.jsonl"
        if ui_file.is_file():
            for line in ui_file.read_text(encoding="utf-8").strip().splitlines():
                try:
                    entry = json.loads(line)
                    ui_map[entry["node_id"]] = entry["data"]
                except (json.JSONDecodeError, KeyError):
                    continue

        # Reconstruct nodes with inline turns and UI
        nodes: dict[str, ConversationNode] = {}
        for nid, node_data in raw.get("nodes", {}).items():
            turn_ids = node_data.get("turn_ids", [])
            turns = [turns_map[tid] for tid in turn_ids if tid in turns_map]
            nodes[nid] = ConversationNode(
                parent=node_data.get("parent"),
                children=node_data.get("children", []),
                turns=turns,
                ui=ui_map.get(nid),
            )

        return ConversationRecord(
            schema_version=raw.get("schema_version", 1),
            id=raw["id"],
            title=raw["title"],
            title_source=raw.get("title_source", "fallback"),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            client_info=raw.get("client_info", {}),
            nodes=nodes,
            next_node_seq=raw.get("next_node_seq", 1),
            current_leaf=raw.get("current_leaf"),
            values=raw.get("values", {}),
            bookmark_state_id=raw.get("bookmark_state_id"),
        )

    async def put(self, scope: str, record: ConversationRecord) -> None:
        scope_dir = await self._scope_dir(scope)
        conv_dir = safe_conv_path(scope_dir, record.id)
        conv_dir.mkdir(parents=True, exist_ok=True)

        ws = self._get_or_init_write_state(scope, record.id, conv_dir)

        # Append new turns and UI
        new_turns_lines: list[str] = []
        new_ui_lines: list[str] = []
        record_nodes: dict[str, dict[str, Any]] = {}

        for nid, node in record.nodes.items():
            if nid not in ws.turn_seq_map:
                turn_ids: list[int] = []
                for turn_data in node.turns:
                    seq = ws.next_turn_seq
                    ws.next_turn_seq += 1
                    turn_ids.append(seq)
                    new_turns_lines.append(
                        json.dumps(
                            {"seq": seq, "data": turn_data},
                            ensure_ascii=False,
                        )
                    )
                ws.turn_seq_map[nid] = turn_ids
            if node.ui is not None and nid not in ws.ui_node_set:
                new_ui_lines.append(
                    json.dumps(
                        {"node_id": nid, "data": node.ui},
                        ensure_ascii=False,
                    )
                )
                ws.ui_node_set.add(nid)
            record_nodes[nid] = {
                "parent": node.parent,
                "children": node.children,
                "turn_ids": ws.turn_seq_map.get(nid, []),
            }

        # Append to JSONL files
        turns_file = conv_dir / "turns.jsonl"
        if new_turns_lines:
            with open(turns_file, "a", encoding="utf-8") as f:
                f.write("\n".join(new_turns_lines) + "\n")
        elif not turns_file.exists():
            turns_file.touch()

        ui_file = conv_dir / "ui.jsonl"
        if new_ui_lines:
            with open(ui_file, "a", encoding="utf-8") as f:
                f.write("\n".join(new_ui_lines) + "\n")
        elif not ui_file.exists():
            ui_file.touch()

        # Write record.json atomically
        record_data = {
            "schema_version": record.schema_version,
            "id": record.id,
            "title": record.title,
            "title_source": record.title_source,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "client_info": record.client_info,
            "next_node_seq": record.next_node_seq,
            "current_leaf": record.current_leaf,
            "nodes": record_nodes,
            "values": record.values,
            "bookmark_state_id": record.bookmark_state_id,
        }
        tmp = conv_dir / ".record.json.tmp"
        tmp.write_text(
            json.dumps(record_data, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, conv_dir / "record.json")

        # Update meta cache
        if scope in self._meta_cache:
            size_bytes = sum(
                f.stat().st_size for f in conv_dir.iterdir() if f.is_file()
            )
            updated = [m for m in self._meta_cache[scope] if m.id != record.id]
            updated.append(record.meta(size_bytes=size_bytes))
            updated.sort(key=lambda m: m.updated_at, reverse=True)
            self._meta_cache[scope] = updated

    async def delete(self, scope: str, conv_id: str) -> None:
        conv_dir = safe_conv_path(await self._scope_dir(scope), conv_id)
        if conv_dir.is_dir():
            shutil.rmtree(conv_dir)
        key = self._ws_key(scope, conv_id)
        self._write_state.pop(key, None)
        if scope in self._meta_cache:
            self._meta_cache[scope] = [
                m for m in self._meta_cache[scope] if m.id != conv_id
            ]

    async def _scope_dir(self, scope: str) -> Path:
        if self._dir is None:
            self._dir = await resolve_history_dir()
        return self._dir / sanitize_scope(scope)


class InMemoryConversationStore(ConversationStore):
    """
    Ephemeral store: conversations live in process memory, lost on restart.

    The default when ``SHINY_DEV_MODE=1``. Useful for development, testing,
    and apps where per-session history is sufficient.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, ConversationRecord]] = {}
        self._meta_cache: dict[str, list[ConversationMeta]] = {}

    async def list(self, scope: str) -> list[ConversationMeta]:
        if scope in self._meta_cache:
            return list(self._meta_cache[scope])
        metas = [
            r.meta(size_bytes=len(r.model_dump_json().encode("utf-8")))
            for r in self._data.get(scope, {}).values()
        ]
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        self._meta_cache[scope] = metas
        return list(metas)

    async def get(self, scope: str, conv_id: str) -> ConversationRecord | None:
        return self._data.get(scope, {}).get(conv_id)

    async def put(self, scope: str, record: ConversationRecord) -> None:
        if scope not in self._data:
            self._data[scope] = {}
        self._data[scope][record.id] = record

        # Only touched-record work — mirrors FileConversationStore.put(), so
        # a warm cache stays warm without resumming/reserializing everything
        # in scope (the cost _evict_if_needed would otherwise pay every turn).
        if scope in self._meta_cache:
            size_bytes = len(record.model_dump_json().encode("utf-8"))
            updated = [m for m in self._meta_cache[scope] if m.id != record.id]
            updated.append(record.meta(size_bytes=size_bytes))
            updated.sort(key=lambda m: m.updated_at, reverse=True)
            self._meta_cache[scope] = updated

    async def delete(self, scope: str, conv_id: str) -> None:
        self._data.get(scope, {}).pop(conv_id, None)
        if scope in self._meta_cache:
            self._meta_cache[scope] = [
                m for m in self._meta_cache[scope] if m.id != conv_id
            ]


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
        return InMemoryConversationStore()
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
