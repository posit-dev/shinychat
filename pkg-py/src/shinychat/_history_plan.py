"""Restore/rewind planning for v2 exchange-tree conversation history.

The planner is a set of module-level pure functions: nothing here reads or
writes recorder state, and every adapter (live chat turns) read is an
explicit ``adapter`` parameter so the live-turns dependency stays visible
at call sites. Plan tuples carry their bound hooks, so :func:`run_plan`
executes a plan without touching any hook registry.

The R port mirrors this module's structure.
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
from ._history_types import ConversationRecordV2, StateEntry

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
    bootstrap: Literal["recorded", "live"]
    prepared_turns: list[dict[str, Any]] | None = None
    turns_unavailable: bool = False


RestoreHook = Callable[[StatePathContext], Awaitable[None] | None]
RestorePlan = tuple[tuple[str, RestoreHook, StatePathContext], ...]
RewindHook = Callable[[StatePathContext], Awaitable[None] | None]
RewindPlan = tuple[tuple[str, RewindHook, StatePathContext], ...]

StateHook = RestoreHook | RewindHook
StatePlan = RestorePlan | RewindPlan


def adapter_is_chatlas(adapter: TurnsAdapter) -> bool:
    return bool(getattr(adapter, "is_chatlas", lambda: False)())


def turn_entry_kind(adapter: TurnsAdapter) -> Literal["chatlas", "turns"]:
    """Kind marker for turn-state entries captured under ``adapter``."""
    return "chatlas" if adapter_is_chatlas(adapter) else "turns"


def canonical_turns(
    turns: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """JSON round-trip each turn and fingerprint the serialized forms."""
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
        (node_id, record.nodes[node_id].state["shinychat:turns"])
        for node_id in node_ids
        if "shinychat:turns" in record.nodes[node_id].state
    )
    _validate_turn_entries(entries)
    return _turn_entries_are_incompatible(
        _effective_turn_entries(
            StatePathContext(
                conversation_id=record.id,
                active_leaf=record.active_leaf,
                node_ids=node_ids,
                entries=entries,
                bootstrap="recorded",
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
    them). A ``live`` bootstrap starts from the adapter's current turns and
    skips only the implicit root snapshot.
    """
    include_system_prompt = adapter_is_chatlas(adapter)
    turns: list[Any] = (
        adapter.get_turns_json(include_system_prompt=include_system_prompt)
        if context.bootstrap == "live"
        else []
    )
    root_id = context.node_ids[0]
    _validate_turn_entries(context.entries)
    if _turns_are_incompatible(context, adapter=adapter):
        return canonical_turns(turns)[0], True

    for node_id, entry in _effective_turn_entries(context):
        entry_turns = cast(list[dict[str, Any]], entry.data)
        if (
            context.bootstrap == "live"
            and node_id == root_id
            and entry.mode == "snapshot"
        ):
            continue
        if entry.mode == "snapshot":
            turns = list(entry_turns)
        else:
            turns.extend(entry_turns)

    return canonical_turns(turns)[0], False


def materialize_live_restore_turns(
    planned: RestorePlan,
    *,
    adapter: TurnsAdapter,
) -> RestorePlan:
    """Materialize the planned turns after admission, keeping live order.

    Live bootstrap is intentionally captured only after admission and
    recorder serialization, but before destructive effects; the caller
    invokes this at that point and passes the refreshed plan onward.
    """
    materialized: list[tuple[str, RestoreHook, StatePathContext]] = []
    for name, hook, context in planned:
        prepared_context = context
        if name == "shinychat:turns":
            prepared_turns, unavailable = materialize_restore_turns(
                context, adapter=adapter
            )
            prepared_context = dataclasses.replace(
                context,
                prepared_turns=prepared_turns,
                turns_unavailable=unavailable,
            )
        materialized.append((name, hook, prepared_context))
    return tuple(materialized)


def turns_unavailable(planned: StatePlan) -> bool:
    return any(
        name == "shinychat:turns" and context.turns_unavailable
        for name, _, context in planned
    )


def preflight_state(
    record: ConversationRecordV2,
    node_ids: tuple[str, ...],
    hooks: Mapping[str, StateHook],
    *,
    adapter: TurnsAdapter,
    bootstrap: Literal["recorded", "live"] = "recorded",
    preserve_live_turns: bool = False,
    reject_unavailable: bool = False,
    phase: Literal["restore", "rewind"] = "restore",
) -> StatePlan:
    """Plan one state-path application before anything is mutated.

    Validates every state entry on ``node_ids`` against ``hooks`` first, so
    malformed state can never move the persisted path. Consolidates the
    former restore and rewind preflights, which were structurally identical
    except for the hook registry: ``phase`` names the flow in validation
    errors, ``preserve_live_turns`` (rewind only) keeps the adapter's
    current turns, and ``reject_unavailable`` (rewind only) refuses plans
    whose recorded turns cannot be reconstructed. A ``live`` bootstrap
    defers turn materialization to :func:`materialize_live_restore_turns`.
    """
    if record.active_leaf is None:
        raise ValueError("Exchange-tree record has no active leaf.")
    for node_id in node_ids:
        for name, entry in record.nodes[node_id].state.items():
            if name not in hooks:
                raise ValueError(
                    f"Unsupported {phase} state entry {name!r}."
                )
            _validate_restore_state_entry(name, entry)

    planned: list[tuple[str, StateHook, StatePathContext]] = []
    for name, hook in hooks.items():
        entries = tuple(
            (node_id, record.nodes[node_id].state[name])
            for node_id in node_ids
            if name in record.nodes[node_id].state
        )
        context = StatePathContext(
            conversation_id=record.id,
            active_leaf=record.active_leaf,
            node_ids=node_ids,
            entries=entries,
            bootstrap=bootstrap,
        )
        if name == "shinychat:turns":
            if preserve_live_turns:
                include_system_prompt = adapter_is_chatlas(adapter)
                prepared_turns = canonical_turns(
                    adapter.get_turns_json(
                        include_system_prompt=include_system_prompt
                    )
                )[0]
                context = dataclasses.replace(
                    context,
                    bootstrap="live",
                    prepared_turns=prepared_turns,
                    turns_unavailable=True,
                )
            elif bootstrap == "recorded":
                prepared_turns, unavailable = materialize_restore_turns(
                    context, adapter=adapter
                )
                if reject_unavailable and unavailable:
                    raise ValueError(
                        "Unsupported shinychat:turns state entry."
                    )
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
    degraded-resubmit path keeps live turns and rewinds only the rest.
    """
    for name, hook, context in planned:
        if skip_turns and name == "shinychat:turns":
            continue
        result = hook(context)
        if inspect.isawaitable(result):
            await result
