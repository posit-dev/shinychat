"""Restore/rewind planning for v2 exchange-tree conversation history.

The planner is a set of module-level pure functions: nothing here reads or
writes recorder state, and every adapter (live chat turns) read is an
explicit ``adapter`` parameter so the live-turns dependency stays visible
at call sites. Plan tuples carry their bound hooks, so :func:`run_plan`
executes a plan without touching any hook registry.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any, Awaitable, Callable, Literal, cast

from ._history_client import (
    TurnsAdapter,
    _validate_mapping_keys,
)
from ._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
)

CaptureReason = Literal["root_close", "stream_finish", "node_close"]
CaptureHook = Callable[
    ["CaptureContext"], Awaitable[StateEntry | None] | StateEntry | None
]


@dataclasses.dataclass(frozen=True)
class CaptureContext:
    node_id: str
    reason: CaptureReason


@dataclasses.dataclass(frozen=True)
class StatePathContext:
    conversation_id: str
    active_leaf: str
    node_ids: tuple[str, ...]
    entries: tuple[tuple[str, StateEntry], ...]
    prepared_turns: list[dict[str, Any]] | None = None
    turns_unavailable: bool = False
    # Deep-copied per-hook entries the same hook owned on the record's
    # previous path (snapshotted at preflight, before node-close capture);
    # ``None`` when the planner has no previous path to report.
    previous_entries: tuple[tuple[str, StateEntry], ...] | None = None


RestoreHook = Callable[[StatePathContext], Awaitable[None] | None]
RestorePlan = tuple[tuple[str, RestoreHook, StatePathContext], ...]
RewindHook = Callable[[StatePathContext], Awaitable[None] | None]
RewindPlan = tuple[tuple[str, RewindHook, StatePathContext], ...]

StateHook = RestoreHook | RewindHook
StatePlan = RestorePlan | RewindPlan


class StateHookError(RuntimeError):
    """A planned state entry failed to apply while a plan was executed.

    Names the failing entry (e.g. ``shinychat:turns``) so restore and
    rewind failures can identify the hook that failed in user-facing
    warnings. The hook's own error stays chained as ``__cause__``;
    cancellations are never wrapped, so ``CancelledError`` keeps its
    identity.
    """

    entry_name: str

    def __init__(self, entry_name: str, error: Exception) -> None:
        super().__init__(f"Failed to apply state entry {entry_name!r}: {error}")
        self.entry_name = entry_name


def adapter_is_chatlas(adapter: TurnsAdapter) -> bool:
    return bool(getattr(adapter, "is_chatlas", lambda: False)())


def turn_entry_kind(adapter: TurnsAdapter) -> Literal["chatlas", "turns"]:
    """Kind marker for turn-state entries captured under ``adapter``."""
    return "chatlas" if adapter_is_chatlas(adapter) else "turns"


def latest_system_prompt(
    entries: tuple[tuple[str, StateEntry], ...],
) -> StateEntry | None:
    """Resolve prompt entries: null inherits, empty string explicitly clears."""
    latest = None
    for _, entry in entries:
        if (
            entry.kind != "system_prompt"
            or entry.version != 1
            or entry.mode != "snapshot"
            or not (entry.data is None or isinstance(entry.data, str))
        ):
            raise ValueError("Unsupported shinychat:system_prompt state entry.")
        if entry.data is not None:
            latest = entry
    return latest


def canonical_turns(
    turns: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    for turn in turns:
        _validate_mapping_keys(turn)
    serialized = [
        json.loads(json.dumps(turn, allow_nan=False, separators=(",", ":")))
        for turn in turns
    ]
    return serialized, [
        json.dumps(turn, allow_nan=False, sort_keys=True, separators=(",", ":"))
        for turn in serialized
    ]


def _effective_turn_entries(
    context: StatePathContext,
) -> tuple[tuple[str, StateEntry], ...]:
    last_snapshot = -1
    for index, (_, entry) in enumerate(context.entries):
        if entry.mode == "snapshot":
            last_snapshot = index
    return context.entries[last_snapshot if last_snapshot >= 0 else 0 :]


def _turn_entries_are_incompatible(
    entries: tuple[tuple[str, StateEntry], ...],
    *,
    adapter: TurnsAdapter,
) -> bool:
    expected_kind = turn_entry_kind(adapter)
    for _, entry in entries:
        if entry.kind != expected_kind or entry.version != 1:
            return True
        if expected_kind == "chatlas":
            from chatlas import Turn

            try:
                for turn in cast(list[dict[str, Any]], entry.data):
                    Turn.model_validate(turn)
            except (TypeError, ValueError):
                return True
    return False


def _turns_are_incompatible(
    context: StatePathContext,
    *,
    adapter: TurnsAdapter,
) -> bool:
    return _turn_entries_are_incompatible(
        _effective_turn_entries(context), adapter=adapter
    )


def _validate_turn_entries(
    entries: tuple[tuple[str, StateEntry], ...],
) -> None:
    for _, entry in entries:
        if not isinstance(entry.data, list) or not all(
            isinstance(turn, dict) for turn in entry.data
        ):
            raise ValueError(
                "Turn-state entries must contain a list of JSON objects."
            )
        canonical_turns(cast(list[dict[str, Any]], entry.data))


def _validate_restore_state_entry(name: str, entry: StateEntry) -> None:
    if not isinstance(entry.kind, str) or not entry.kind:
        raise ValueError(f"State entry {name!r} has an invalid kind.")
    if (
        not isinstance(entry.version, int)
        or isinstance(entry.version, bool)
        or entry.version < 1
    ):
        raise ValueError(f"State entry {name!r} has an invalid version.")
    if not isinstance(entry.mode, str) or entry.mode not in (
        "snapshot",
        "delta",
    ):
        raise ValueError(f"State entry {name!r} has an invalid mode.")
    try:
        json.dumps(entry.data, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"State entry {name!r} has invalid JSON data."
        ) from e


def active_path_turns_are_incompatible(
    record: ConversationRecordV2,
    *,
    adapter: TurnsAdapter,
) -> bool:
    """Whether the active path's turn entries cannot rebuild live turns.

    Raises on structurally invalid state entries along the way, so callers
    treat malformed state and foreign turn kinds alike: keep the live turns
    (``preserve_live_turns``) instead of replaying recorded ones.
    """
    if record.active_leaf is None:
        raise ValueError("Exchange-tree record has no active leaf.")
    node_ids = tuple(record.path_node_ids())
    for node_id in node_ids:
        for name, entry in record.nodes[node_id].state.items():
            _validate_restore_state_entry(name, entry)
    entries = tuple(
        (node_id, record.nodes[node_id].state[TURNS_STATE_KEY])
        for node_id in node_ids
        if TURNS_STATE_KEY in record.nodes[node_id].state
    )
    _validate_turn_entries(entries)
    return _turn_entries_are_incompatible(
        _effective_turn_entries(
            StatePathContext(
                conversation_id=record.id,
                active_leaf=record.active_leaf,
                node_ids=node_ids,
                entries=entries,
            )
        ),
        adapter=adapter,
    )


def materialize_restore_turns(
    context: StatePathContext,
    *,
    adapter: TurnsAdapter,
) -> tuple[list[dict[str, Any]], bool]:
    """Fold a path's turn entries into the turn list to set.

    Returns the materialized turns and whether they are unusable (``True``
    means the caller must keep or clear live turns instead of replaying
    them). Recorded entries rebuild the list from scratch; the live
    turns never seed it.
    """
    turns: list[Any] = []
    _validate_turn_entries(context.entries)
    if _turns_are_incompatible(context, adapter=adapter):
        return canonical_turns(turns)[0], True

    for _node_id, entry in _effective_turn_entries(context):
        entry_turns = cast(list[dict[str, Any]], entry.data)
        if entry.mode == "snapshot":
            turns = list(entry_turns)
        else:
            turns.extend(entry_turns)

    return canonical_turns(turns)[0], False


def turns_unavailable(planned: StatePlan) -> bool:
    return any(
        name == TURNS_STATE_KEY and context.turns_unavailable
        for name, _, context in planned
    )


def preflight_state(
    record: ConversationRecordV2,
    node_ids: tuple[str, ...],
    hooks: Mapping[str, StateHook],
    *,
    adapter: TurnsAdapter,
    previous_node_ids: tuple[str, ...] | None = None,
    preserve_live_turns: bool = False,
    reject_unavailable: bool = False,
    phase: Literal["restore", "rewind"] = "restore",
) -> StatePlan:
    """Plan one state-path application before anything is mutated.

    Validates every state entry on ``node_ids`` against ``hooks`` first, so
    malformed state can never move the persisted path. ``phase`` names the
    flow in validation errors, ``preserve_live_turns`` (rewind only) keeps
    the adapter's current turns, and ``reject_unavailable`` (rewind only)
    refuses plans whose recorded turns cannot be reconstructed.
    ``previous_node_ids`` (the record's path before the rewind, passed
    before node-close capture) populates ``previous_entries``.
    """
    if record.active_leaf is None:
        raise ValueError("Exchange-tree record has no active leaf.")
    for node_id in node_ids:
        for name, entry in record.nodes[node_id].state.items():
            if name not in hooks:
                raise ValueError(f"Unsupported {phase} state entry {name!r}.")
            _validate_restore_state_entry(name, entry)

    planned: list[tuple[str, StateHook, StatePathContext]] = []
    for name, hook in hooks.items():
        entries = tuple(
            (node_id, record.nodes[node_id].state[name])
            for node_id in node_ids
            if name in record.nodes[node_id].state
        )
        previous_entries = (
            tuple(
                (
                    node_id,
                    record.nodes[node_id].state[name].model_copy(deep=True),
                )
                for node_id in previous_node_ids
                if name in record.nodes[node_id].state
            )
            if previous_node_ids is not None
            else None
        )
        context = StatePathContext(
            conversation_id=record.id,
            active_leaf=record.active_leaf,
            node_ids=node_ids,
            entries=entries,
            previous_entries=previous_entries,
        )
        if name == SYSTEM_PROMPT_STATE_KEY:
            latest_system_prompt(entries)
            if previous_entries is not None:
                latest_system_prompt(previous_entries)
        if name == TURNS_STATE_KEY:
            if preserve_live_turns:
                prepared_turns = canonical_turns(adapter.get_turns_json())[0]
                context = dataclasses.replace(
                    context,
                    prepared_turns=prepared_turns,
                    turns_unavailable=True,
                )
            else:
                prepared_turns, unavailable = materialize_restore_turns(
                    context, adapter=adapter
                )
                if reject_unavailable and unavailable:
                    raise ValueError("Unsupported shinychat:turns state entry.")
                context = dataclasses.replace(
                    context,
                    prepared_turns=prepared_turns,
                    turns_unavailable=unavailable,
                )
        planned.append((name, hook, context))
    return tuple(planned)


async def run_plan(
    planned: StatePlan,
    *,
    skip_turns: bool = False,
) -> None:
    """Execute a planned state-path application hook by hook.

    ``skip_turns=True`` drops the ``shinychat:turns`` entry: the
    degraded-resubmit path keeps live turns and rewinds only the rest. A
    hook that raises wraps its error in :class:`StateHookError`, which
    names the entry; cancellation (any other ``BaseException``)
    propagates unchanged.
    """
    for name, hook, context in planned:
        if skip_turns and name == TURNS_STATE_KEY:
            continue
        try:
            result = hook(context)
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            raise StateHookError(name, error) from error
