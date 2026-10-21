"""Restore/rewind planning for v2 exchange-tree conversation history.

The planner is a set of module-level pure functions: nothing here reads or
writes recorder state, and every adapter (live chat turns) read is an
explicit ``adapter`` parameter so the live-turns dependency stays visible
at call sites. Plan tuples carry their bound hooks, so :func:`run_plan`
executes a plan without touching any hook registry.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any, Awaitable, Callable, Literal, cast

from pydantic import JsonValue
from pydantic_core import to_jsonable_python

from ._history_client import (
    TurnsAdapter,
    _validate_mapping_keys,
)
from ._history_types import (
    SYSTEM_PROMPT_STATE_KEY,
    TURNS_STATE_KEY,
    VALUES_STATE_KEY,
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
    # Concrete classification cause when ``turns_unavailable`` (kind,
    # version, validation failure, or prompt-capability mismatch); used
    # for the developer warning at restore time. Never sent to the UI.
    turns_unavailable_reason: str | None = None
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


def latest_values(
    entries: tuple[tuple[str, StateEntry], ...],
) -> StateEntry | None:
    """Resolve values entries: every validated JSON object is effective.

    Unlike the system prompt, values have no null/empty inheritance
    semantics: an empty object is an explicit value, ``null`` is not a
    values object, and only a *missing* entry inherits the nearest
    recorded ancestor.
    """
    latest = None
    for _, entry in entries:
        if (
            entry.kind != "values"
            or entry.version != 1
            or entry.mode != "snapshot"
            or not isinstance(entry.data, dict)
        ):
            raise ValueError("Unsupported shinychat:values state entry.")
        latest = entry
    return latest


def canonical_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an application-values object; return a detached JSON copy.

    Non-string keys are rejected first (JSON object keys must already
    be strings), *before* any coercion can quietly rename them. Rich
    app values are then coerced exactly the way the old
    ``model_dump_json`` path coerced them (``date``/``datetime``,
    ``Decimal``, ``UUID``, tuples, sets, and bytes become their JSON
    forms via ``pydantic_core.to_jsonable_python``; common Shiny
    values like ``input.date()`` and ``input.date_range()`` keep
    saving). Unknown objects are still refused loudly, and
    non-finite floats are rejected after normalization
    (``allow_nan=False``) rather than silently coerced to ``null``;
    the JSON round trip detaches the result from the callback's
    dictionary.
    """
    _validate_mapping_keys(values, what="app state values")
    normalized = to_jsonable_python(values)
    return cast(
        dict[str, Any],
        json.loads(
            json.dumps(normalized, allow_nan=False, separators=(",", ":"))
        ),
    )


def _canonical_data(data: JsonValue) -> str:
    """Canonical JSON for value comparison.

    Python equality conflates distinct JSON values (``True == 1``,
    ``False == 0``), which would silently drop real boolean/numeric
    changes; the canonical form also ignores dictionary order. Computed
    locally per comparison -- no persistent fingerprints or baselines.
    """
    return json.dumps(
        data, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def sparse_snapshot_entry(
    record: ConversationRecordV2,
    node_id: str,
    key: str,
    data: JsonValue,
    *,
    is_effective: Callable[[StateEntry | None], bool],
    kind: str,
    default_entry: StateEntry | None = None,
) -> StateEntry | None:
    """The shared sparse per-node snapshot operation.

    The root always records; a descendant records only when ``data``
    differs (canonical JSON comparison: ``True``/``1`` are distinct, and
    dictionary order is ignored) from the nearest effective ancestor
    entry for ``key``. ``default_entry`` is the effective value for a
    path with no recorded entry at all: it answers the previous-value
    fallback, the descendant dedupe, and the child anchoring alike
    (values pass an explicit ``{}`` entry, since a path without any entry
    resolves to ``{}``; the system prompt passes nothing, so unrecorded
    paths keep their record-everywhere behavior). Before a shared
    parent's recapture changes what its existing children inherit,
    children without their own effective entry are pinned to the previous
    effective value -- including the default, so a first recording cannot
    silently rewrite what an older branch resolves to. ``is_effective``
    carries the per-key inheritance semantics (the system prompt treats
    null as inheriting; values treat every recorded object as effective).
    Returns ``None`` when a descendant's value is unchanged and it should
    inherit instead of record.
    """
    node = record.nodes[node_id]
    ancestor: StateEntry | None = None
    parent_id = node.parent_id
    while parent_id is not None:
        parent = record.nodes[parent_id]
        candidate = parent.state.get(key)
        if is_effective(candidate):
            ancestor = candidate
            break
        parent_id = parent.parent_id
    effective_ancestor = ancestor if ancestor is not None else default_entry
    previous = node.state.get(key)
    if not is_effective(previous):
        previous = effective_ancestor
    canonical = _canonical_data(data)
    if (
        previous is not None
        and _canonical_data(previous.data) != canonical
    ):
        for child_id in node.children:
            child = record.nodes[child_id]
            if not is_effective(child.state.get(key)):
                child.state[key] = previous.model_copy(deep=True)
    if (
        node.parent_id is not None
        and effective_ancestor is not None
        and _canonical_data(effective_ancestor.data) == canonical
    ):
        # A descendant with an unchanged value inherits instead of
        # recording; the root always records.
        return None
    return StateEntry(kind=kind, version=1, mode="snapshot", data=data)


def resolve_path_values(
    record: ConversationRecordV2, node_id: str
) -> dict[str, Any]:
    """The detached effective application values at ``node_id``.

    The nearest recorded ``shinychat:values`` entry on the ancestor path
    (inclusive) wins; a path without any entry resolves to ``{}``. The
    winning entry is envelope-validated (``latest_values``), and the
    returned object is a deep copy: callers (and the callbacks they hand
    it to) can never mutate the stored entry.
    """
    cursor: str | None = node_id
    while cursor is not None:
        node = record.nodes[cursor]
        entry = node.state.get(VALUES_STATE_KEY)
        if entry is not None:
            winning = latest_values(((cursor, entry),))
            assert winning is not None
            return copy.deepcopy(cast(dict[str, Any], winning.data))
        cursor = node.parent_id
    return {}


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


def _turn_entries_incompatibility(
    entries: tuple[tuple[str, StateEntry], ...],
    *,
    adapter: TurnsAdapter,
) -> str | None:
    """The concrete cause the entries cannot rebuild live turns, if any.

    Returns ``None`` when the entries are compatible with ``adapter``;
    otherwise a developer-facing classification (expected/recorded kind,
    unsupported version, or a validation exception summary). The text is
    never sent to the client.
    """
    expected_kind = turn_entry_kind(adapter)
    for _, entry in entries:
        if entry.kind != expected_kind:
            return (
                f"recorded turn kind {entry.kind!r} does not match the "
                f"active client's {expected_kind!r} kind"
            )
        if entry.version != 1:
            return (
                f"recorded {entry.kind!r} turn-state version "
                f"{entry.version!r} is unsupported"
            )
        if expected_kind == "chatlas":
            from chatlas import Turn

            try:
                for turn in cast(list[dict[str, Any]], entry.data):
                    Turn.model_validate(turn)
            except (TypeError, ValueError) as error:
                return f"recorded turns failed chatlas validation: {error}"
    return None


def _turns_incompatibility(
    context: StatePathContext,
    *,
    adapter: TurnsAdapter,
) -> str | None:
    return _turn_entries_incompatibility(
        _effective_turn_entries(context), adapter=adapter
    )


def _system_prompt_capability_mismatch(
    entries: tuple[tuple[str, StateEntry], ...],
    *,
    adapter: TurnsAdapter,
) -> str | None:
    """The cause a recorded prompt directive cannot apply, if any.

    Validates the entries even without a registered prompt hook (this is
    the one known builtin key that is always recognized). A null-only
    path carries no directive and is not a mismatch; an explicit clear
    (``""``) is a directive and does require the capability.
    """
    if not entries:
        return None
    latest = latest_system_prompt(entries)
    if latest is None or adapter.has_system_prompt():
        return None
    return (
        "the recorded system prompt requires a client with "
        "system-prompt support"
    )


# Builtin state keys recognized (and validated) without a registered hook.
_KNOWN_BUILTIN_STATE_KEYS = frozenset(
    {SYSTEM_PROMPT_STATE_KEY, VALUES_STATE_KEY}
)


def _validate_values_entries(
    record: ConversationRecordV2, node_ids: Sequence[str]
) -> None:
    if not node_ids:
        return
    latest_values(
        tuple(
            (node_id, record.nodes[node_id].state[VALUES_STATE_KEY])
            for node_id in node_ids
        )
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


def validate_active_path_state(record: ConversationRecordV2) -> None:
    """Strictly validate every state entry on the record's active path.

    Resubmit rewinds only the parent prefix, but the abandoned target
    stays on the record: malformed builtin state anywhere on the active
    path must fail before any mutation, matching restore/navigation.
    """
    if record.active_leaf is None:
        raise ValueError("Exchange-tree record has no active leaf.")
    node_ids = tuple(record.path_node_ids())
    turn_entries: list[tuple[str, StateEntry]] = []
    prompt_entries: list[tuple[str, StateEntry]] = []
    values_entries: list[tuple[str, StateEntry]] = []
    for node_id in node_ids:
        for name, entry in record.nodes[node_id].state.items():
            _validate_restore_state_entry(name, entry)
            if name == TURNS_STATE_KEY:
                turn_entries.append((node_id, entry))
            elif name == SYSTEM_PROMPT_STATE_KEY:
                prompt_entries.append((node_id, entry))
            elif name == VALUES_STATE_KEY:
                values_entries.append((node_id, entry))
    _validate_turn_entries(tuple(turn_entries))
    if prompt_entries:
        latest_system_prompt(tuple(prompt_entries))
    if values_entries:
        latest_values(tuple(values_entries))


def materialize_restore_turns(
    context: StatePathContext,
    *,
    adapter: TurnsAdapter,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fold a path's turn entries into the turn list to set.

    Returns the materialized turns and the incompatibility cause, if any
    (a non-``None`` cause means the caller must keep or clear live turns
    instead of replaying them, and the returned list is empty). Recorded
    entries rebuild the list from scratch; the live turns never seed it.
    """
    turns: list[Any] = []
    _validate_turn_entries(context.entries)
    incompatible = _turns_incompatibility(context, adapter=adapter)
    if incompatible is not None:
        return canonical_turns(turns)[0], incompatible

    for _node_id, entry in _effective_turn_entries(context):
        entry_turns = cast(list[dict[str, Any]], entry.data)
        if entry.mode == "snapshot":
            turns = list(entry_turns)
        else:
            turns.extend(entry_turns)

    return canonical_turns(turns)[0], None


def turns_unavailable(planned: StatePlan) -> bool:
    return any(
        name == TURNS_STATE_KEY and context.turns_unavailable
        for name, _, context in planned
    )


def turns_unavailable_reason(planned: StatePlan) -> str | None:
    """The classified cause the plan's model context is unavailable."""
    for name, _, context in planned:
        if name == TURNS_STATE_KEY and context.turns_unavailable:
            return (
                context.turns_unavailable_reason
                or "recorded turns are incompatible with the active client"
            )
    return None


def preflight_state(
    record: ConversationRecordV2,
    node_ids: tuple[str, ...],
    hooks: Mapping[str, StateHook],
    *,
    adapter: TurnsAdapter,
    previous_node_ids: tuple[str, ...] | None = None,
    reject_unavailable: bool = False,
    phase: Literal["restore", "rewind"] = "restore",
) -> StatePlan:
    """Plan one state-path application before anything is mutated.

    Validates every state entry on ``node_ids`` against ``hooks`` first, so
    malformed state can never move the persisted path. ``phase`` names the
    flow in validation errors and ``reject_unavailable`` (rewind only)
    refuses plans whose recorded model context cannot be reconstructed.
    ``previous_node_ids`` (the record's path before the rewind, passed
    before node-close capture) populates ``previous_entries``.

    ``shinychat:system_prompt`` is a known builtin key: it is recognized
    and validated even without a registered prompt hook (a client without
    the prompt capability), where a recorded directive degrades the plan
    to unavailable model context instead of failing preflight.
    ``shinychat:values`` is likewise a known builtin key: it is recognized
    and validated even though it owns no restore/rewind hook (application
    values are delivered to ``on_restore``/``on_navigate`` callbacks, not
    applied to the model client).
    """
    if record.active_leaf is None:
        raise ValueError("Exchange-tree record has no active leaf.")
    values_node_ids: list[str] = []
    for node_id in node_ids:
        for name, entry in record.nodes[node_id].state.items():
            if name not in hooks and name not in _KNOWN_BUILTIN_STATE_KEYS:
                raise ValueError(f"Unsupported {phase} state entry {name!r}.")
            _validate_restore_state_entry(name, entry)
        if VALUES_STATE_KEY in record.nodes[node_id].state:
            values_node_ids.append(node_id)
    _validate_values_entries(record, values_node_ids)
    if previous_node_ids is not None:
        _validate_values_entries(
            record,
            [
                node_id
                for node_id in previous_node_ids
                if VALUES_STATE_KEY in record.nodes[node_id].state
            ],
        )

    prompt_mismatch = _system_prompt_capability_mismatch(
        tuple(
            (node_id, record.nodes[node_id].state[SYSTEM_PROMPT_STATE_KEY])
            for node_id in node_ids
            if SYSTEM_PROMPT_STATE_KEY in record.nodes[node_id].state
        ),
        adapter=adapter,
    )

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
            prepared_turns, unavailable_reason = materialize_restore_turns(
                context, adapter=adapter
            )
            if unavailable_reason is None and prompt_mismatch is not None:
                # The turns themselves are compatible, but a recorded
                # prompt directive cannot apply: the model context is
                # still unavailable, so live turns are cleared rather
                # than seeded from an incomplete reconstruction.
                unavailable_reason = prompt_mismatch
                prepared_turns = []
            if reject_unavailable and unavailable_reason is not None:
                raise ValueError(
                    "Unsupported shinychat:turns state entry: "
                    f"{unavailable_reason}."
                )
            context = dataclasses.replace(
                context,
                prepared_turns=prepared_turns,
                turns_unavailable=unavailable_reason is not None,
                turns_unavailable_reason=unavailable_reason,
            )
        planned.append((name, hook, context))
    return tuple(planned)


async def run_plan(
    planned: StatePlan,
) -> None:
    """Execute a planned state-path application hook by hook.

    A hook that raises wraps its error in :class:`StateHookError`, which
    names the entry; cancellation (any other ``BaseException``)
    propagates unchanged.
    """
    for name, hook, context in planned:
        try:
            result = hook(context)
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            raise StateHookError(name, error) from error
