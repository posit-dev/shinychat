from __future__ import annotations

import hashlib
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from ._history_types import ConversationMeta, ConversationRecord

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

    @abstractmethod
    async def total_size(self, scope: str) -> int:
        """Total bytes used by all conversations in scope."""

    async def search(self, scope: str, query: str) -> list[ConversationMeta]:
        q = query.casefold()
        return [m for m in await self.list(scope) if q in m.title.casefold()]


class FileConversationStore(ConversationStore):
    """
    Default store: one JSON file per conversation at `<dir>/<scope>/<id>.json`.

    When `dir` is None, the directory is resolved lazily on first use via
    `resolve_history_dir()` (Connect-aware; see that function).

    An in-memory metadata cache is kept per scope so that repeated `list()`
    calls (which fire on every assistant response) avoid re-reading every file.
    The cache is populated on the first `list()` per scope and kept in sync by
    `put()` and `delete()`. It is per-process: in multi-worker deployments with
    sticky sessions (the normal Shiny model) each session's worker owns its
    cache and they never diverge. Without sticky sessions, a worker may briefly
    serve a stale list — it self-corrects on the next `put()` or `delete()`.

    """

    def __init__(self, dir: str | Path | None = None):
        self._dir: Path | None = Path(dir) if dir is not None else None
        self._meta_cache: dict[str, list[ConversationMeta]] = {}

    async def list(self, scope: str) -> list[ConversationMeta]:
        if scope in self._meta_cache:
            return list(self._meta_cache[scope])
        scope_dir = await self._scope_dir(scope)
        metas: list[ConversationMeta] = []
        if scope_dir.is_dir():
            for f in scope_dir.glob("*.json"):
                try:
                    rec = ConversationRecord.model_validate_json(
                        f.read_text(encoding="utf-8")
                    )
                except Exception as e:
                    logger.warning("Unreadable conversation %s: %s", f.name, e)
                    continue
                metas.append(rec.meta)
            metas.sort(key=lambda m: m.updated_at, reverse=True)
        self._meta_cache[scope] = metas
        return list(metas)

    async def get(self, scope: str, conv_id: str) -> ConversationRecord | None:
        f = safe_conv_path(await self._scope_dir(scope), conv_id)
        if not f.is_file():
            return None
        return ConversationRecord.model_validate_json(
            f.read_text(encoding="utf-8")
        )

    async def put(self, scope: str, record: ConversationRecord) -> None:
        scope_dir = await self._scope_dir(scope)
        scope_dir.mkdir(parents=True, exist_ok=True)
        dest = safe_conv_path(scope_dir, record.id)
        tmp = scope_dir / f".{record.id}.json.tmp"
        tmp.write_text(record.model_dump_json(), encoding="utf-8")
        os.replace(tmp, dest)  # atomic on POSIX and Windows
        if scope in self._meta_cache:
            updated = [m for m in self._meta_cache[scope] if m.id != record.id]
            updated.append(record.meta)
            updated.sort(key=lambda m: m.updated_at, reverse=True)
            self._meta_cache[scope] = updated

    async def delete(self, scope: str, conv_id: str) -> None:
        f = safe_conv_path(await self._scope_dir(scope), conv_id)
        f.unlink(missing_ok=True)
        if scope in self._meta_cache:
            self._meta_cache[scope] = [
                m for m in self._meta_cache[scope] if m.id != conv_id
            ]

    async def total_size(self, scope: str) -> int:
        scope_dir = await self._scope_dir(scope)
        if not scope_dir.is_dir():
            return 0
        return sum(f.stat().st_size for f in scope_dir.glob("*.json"))

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

    async def list(self, scope: str) -> list[ConversationMeta]:
        metas = [r.meta for r in self._data.get(scope, {}).values()]
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        return metas

    async def get(self, scope: str, conv_id: str) -> ConversationRecord | None:
        return self._data.get(scope, {}).get(conv_id)

    async def put(self, scope: str, record: ConversationRecord) -> None:
        if scope not in self._data:
            self._data[scope] = {}
        self._data[scope][record.id] = record

    async def delete(self, scope: str, conv_id: str) -> None:
        self._data.get(scope, {}).pop(conv_id, None)

    async def total_size(self, scope: str) -> int:
        return sum(
            len(r.model_dump_json().encode("utf-8"))
            for r in self._data.get(scope, {}).values()
        )


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
    return scope_dir / f"{conv_id}.json"


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

    # Private shiny API; coordinate upstream for a public accessor.
    from shiny.bookmark._global import get_bookmark_save_dir_fn
    from shiny.types import MISSING

    save_dir_fn = get_bookmark_save_dir_fn(MISSING)
    if save_dir_fn is not None:
        # set_global_save_dir_fn already wraps with wrap_async, so fn is async.
        # Registrants may return str despite the Path annotation; coerce defensively.
        return Path(await save_dir_fn(HISTORY_BOOKMARK_ID))

    return Path(".shinychat") / "conversations"
