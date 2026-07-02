from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

_STATE_ID_RE = re.compile(r"[?&]_state_id_=([A-Za-z0-9_-]+)")

BookmarkDirFn = Callable[[str], Awaitable[Path]]


def extract_state_id(url: str) -> str | None:
    m = _STATE_ID_RE.search(url)
    return m.group(1) if m else None


def global_save_dir_fn() -> BookmarkDirFn | None:
    """
    Shiny's currently configured global bookmark save-dir function, if any.

    `shiny.bookmark` only exposes the setter (`set_global_save_dir_fn`); the
    getter lives in the private `shiny.bookmark._global` module. Coordinate
    upstream for a public accessor.
    """
    try:
        from shiny.bookmark._global import get_bookmark_save_dir_fn
        from shiny.types import MISSING

        return get_bookmark_save_dir_fn(MISSING)
    except (ImportError, AttributeError):
        return None


def global_restore_dir_fn() -> BookmarkDirFn | None:
    """Shiny's currently configured global bookmark restore-dir function, if any."""
    try:
        from shiny.bookmark._global import get_bookmark_restore_dir_fn
        from shiny.types import MISSING

        return get_bookmark_restore_dir_fn(MISSING)
    except (ImportError, AttributeError):
        return None


async def delete_bookmark_state(state_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", state_id):
        return
    restore_dir_fn = global_restore_dir_fn()
    if restore_dir_fn is None:
        return
    try:
        restore_dir = await restore_dir_fn(state_id)
    except Exception:
        logger.warning(
            "Failed to resolve bookmark restore dir for cleanup", exc_info=True
        )
        return
    p = Path(restore_dir)
    if p.is_dir():
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: shutil.rmtree(p, ignore_errors=True)
        )
