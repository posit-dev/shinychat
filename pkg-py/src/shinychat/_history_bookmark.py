from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

_STATE_ID_RE = re.compile(r"[?&]_state_id_=([A-Za-z0-9_-]+)")


def extract_state_id(url: str) -> str | None:
    m = _STATE_ID_RE.search(url)
    return m.group(1) if m else None


async def delete_bookmark_state(state_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", state_id):
        return
    try:
        from shiny.bookmark._global import (
            get_bookmark_restore_dir_fn,  # type: ignore[attr-defined]
        )
        from shiny.types import MISSING  # type: ignore[attr-defined]

        restore_dir_fn = get_bookmark_restore_dir_fn(MISSING)
        if restore_dir_fn is None:
            return
        restore_dir = await restore_dir_fn(state_id)
    except Exception:
        return
    p = Path(restore_dir)
    if p.is_dir():
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: shutil.rmtree(p, ignore_errors=True)
        )
