from __future__ import annotations

import dataclasses
import inspect
import json
from typing import Any, Awaitable, Callable, Literal, cast

from pydantic import JsonValue

from ._history_client import TurnsAdapter, _validate_mapping_keys
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


class _ExchangeState:
    """Capture and restore provider state independently of its UI or worker host."""

    def __init__(self, adapter: TurnsAdapter) -> None:
        self._adapter = adapter
        self.record: ConversationRecordV2 | None = None
        self._capture_hooks: dict[str, CaptureHook] = {}
        self._restore_hooks: dict[str, RestoreHook] = {}
        self._rewind_hooks: dict[str, RewindHook] = {}
        self._turn_baseline: list[str] = []
        self._register_capture_hook("shinychat:turns", self._capture_turns)
        self._register_restore_hook("shinychat:turns", self._restore_turns)
        self._register_rewind_hook("shinychat:turns", self._restore_turns)

    def _register_capture_hook(self, name: str, hook: CaptureHook) -> None:
        self._capture_hooks[name] = hook

    def _register_restore_hook(self, name: str, hook: RestoreHook) -> None:
        self._restore_hooks[name] = hook

    def _register_rewind_hook(self, name: str, hook: RewindHook) -> None:
        self._rewind_hooks[name] = hook

    @staticmethod
    def _canonical_turns(
        turns: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        for turn in turns:
            _validate_mapping_keys(turn)
        serialized = [
            json.loads(json.dumps(turn, allow_nan=False, separators=(",", ":")))
            for turn in turns
        ]
        return serialized, [
            json.dumps(
                turn, allow_nan=False, sort_keys=True, separators=(",", ":")
            )
            for turn in serialized
        ]

    def _set_turn_baseline(self, turns: list[dict[str, Any]]) -> None:
        _, self._turn_baseline = self._canonical_turns(turns)

    def _invalidate_turn_baseline(self) -> None:
        # Canonical turn fingerprints always serialize a dictionary, never "".
        self._turn_baseline = [""]

    def _capture_turns(self, context: CaptureContext) -> StateEntry:
        adapter = self._adapter
        include_system_prompt = getattr(adapter, "is_chatlas", lambda: False)()
        turns, fingerprints = self._canonical_turns(
            adapter.get_turns_json(include_system_prompt=include_system_prompt)
        )
        is_prefix = (
            len(self._turn_baseline) <= len(fingerprints)
            and self._turn_baseline == fingerprints[: len(self._turn_baseline)]
        )
        if context.reason == "root_close" or not is_prefix:
            mode: Literal["delta", "snapshot"] = "snapshot"
            data = turns
        else:
            mode = "delta"
            data = turns[len(self._turn_baseline) :]

        self._turn_baseline = fingerprints
        assert self.record is not None
        previous = self.record.nodes[context.node_id].state.get(
            "shinychat:turns"
        )
        if mode == "delta" and previous is not None:
            if not isinstance(previous.data, list):
                raise ValueError("Turn-state entries must contain a list.")
            data = [*previous.data, *data]
            mode = previous.mode
        return StateEntry(
            kind="chatlas"
            if getattr(adapter, "is_chatlas", lambda: False)()
            else "turns",
            version=1,
            mode=mode,
            data=cast(JsonValue, data),
        )

    async def _capture_state(self, node_id: str, reason: CaptureReason) -> None:
        assert self.record is not None
        node = self.record.nodes[node_id]
        context = CaptureContext(node_id=node_id, reason=reason)
        for name, hook in self._capture_hooks.items():
            entry = hook(context)
            if inspect.isawaitable(entry):
                entry = await entry
            if entry is None:
                node.state.pop(name, None)
            else:
                node.state[name] = entry

    @staticmethod
    def _effective_turn_entries(
        context: StatePathContext,
    ) -> tuple[tuple[str, StateEntry], ...]:
        last_snapshot = -1
        for index, (_, entry) in enumerate(context.entries):
            if entry.mode == "snapshot":
                last_snapshot = index
        return context.entries[last_snapshot if last_snapshot >= 0 else 0 :]

    def _turn_entries_are_incompatible(
        self, entries: tuple[tuple[str, StateEntry], ...]
    ) -> bool:
        expected_kind = (
            "chatlas"
            if getattr(self._adapter, "is_chatlas", lambda: False)()
            else "turns"
        )
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

    def _turns_are_incompatible(self, context: StatePathContext) -> bool:
        return self._turn_entries_are_incompatible(
            self._effective_turn_entries(context)
        )

    def _validate_turn_entries(
        self, entries: tuple[tuple[str, StateEntry], ...]
    ) -> None:
        for _, entry in entries:
            if not isinstance(entry.data, list) or not all(
                isinstance(turn, dict) for turn in entry.data
            ):
                raise ValueError(
                    "Turn-state entries must contain a list of JSON objects."
                )
            self._canonical_turns(cast(list[dict[str, Any]], entry.data))

    def _active_path_turns_are_incompatible(
        self, record: ConversationRecordV2
    ) -> bool:
        if record.active_leaf is None:
            raise ValueError("Exchange-tree record has no active leaf.")
        node_ids = tuple(record.path_node_ids())
        for node_id in node_ids:
            for name, entry in record.nodes[node_id].state.items():
                self._validate_restore_state_entry(name, entry)
        entries = tuple(
            (node_id, record.nodes[node_id].state["shinychat:turns"])
            for node_id in node_ids
            if "shinychat:turns" in record.nodes[node_id].state
        )
        self._validate_turn_entries(entries)
        return self._turn_entries_are_incompatible(
            self._effective_turn_entries(
                StatePathContext(
                    conversation_id=record.id,
                    active_leaf=record.active_leaf,
                    node_ids=node_ids,
                    entries=entries,
                    bootstrap="recorded",
                )
            )
        )

    def _materialize_restore_turns(
        self, context: StatePathContext
    ) -> tuple[list[dict[str, Any]], bool]:
        adapter = self._adapter
        include_system_prompt = getattr(adapter, "is_chatlas", lambda: False)()
        turns = (
            adapter.get_turns_json(include_system_prompt=include_system_prompt)
            if context.bootstrap == "live"
            else []
        )
        root_id = context.node_ids[0]
        self._validate_turn_entries(context.entries)
        if self._turns_are_incompatible(context):
            return self._canonical_turns(turns)[0], True

        for node_id, entry in self._effective_turn_entries(context):
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

        return self._canonical_turns(turns)[0], False

    async def _restore_turns(self, context: StatePathContext) -> None:
        if context.prepared_turns is None:
            raise RuntimeError("Turns must be materialized before restore.")
        turns = context.prepared_turns
        adapter = self._adapter
        if context.turns_unavailable:
            if context.bootstrap == "recorded":
                adapter.set_turns_json([])
            self._set_turn_baseline(turns)
            return
        adapter.set_turns_json(turns)
        self._set_turn_baseline(turns)

    @staticmethod
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

    def _preflight_restore_state(
        self,
        record: ConversationRecordV2,
        node_ids: tuple[str, ...],
        bootstrap: Literal["recorded", "live"],
    ) -> RestorePlan:
        if record.active_leaf is None:
            raise ValueError("Exchange-tree record has no active leaf.")
        for node_id in node_ids:
            for name, entry in record.nodes[node_id].state.items():
                if name not in self._restore_hooks:
                    raise ValueError(
                        f"Unsupported restore state entry {name!r}."
                    )
                self._validate_restore_state_entry(name, entry)

        planned: list[tuple[str, RestoreHook, StatePathContext]] = []
        for name, hook in self._restore_hooks.items():
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
            if name == "shinychat:turns" and bootstrap == "recorded":
                prepared_turns, turns_unavailable = (
                    self._materialize_restore_turns(context)
                )
                context = dataclasses.replace(
                    context,
                    prepared_turns=prepared_turns,
                    turns_unavailable=turns_unavailable,
                )
            planned.append((name, hook, context))
        return tuple(planned)

    def _materialize_live_restore_turns(
        self, planned: RestorePlan
    ) -> RestorePlan:
        materialized: list[tuple[str, RestoreHook, StatePathContext]] = []
        for name, hook, context in planned:
            prepared_context = context
            if name == "shinychat:turns":
                prepared_turns, turns_unavailable = (
                    self._materialize_restore_turns(context)
                )
                prepared_context = dataclasses.replace(
                    context,
                    prepared_turns=prepared_turns,
                    turns_unavailable=turns_unavailable,
                )
            materialized.append((name, hook, prepared_context))
        return tuple(materialized)

    @staticmethod
    def _turns_unavailable(planned: RestorePlan) -> bool:
        return any(
            name == "shinychat:turns" and context.turns_unavailable
            for name, _, context in planned
        )

    async def _restore_state(self, planned: RestorePlan) -> None:
        for _, hook, context in planned:
            result = hook(context)
            if inspect.isawaitable(result):
                await result

    def _preflight_rewind_state(
        self,
        record: ConversationRecordV2,
        node_ids: tuple[str, ...],
        *,
        preserve_live_turns: bool = False,
    ) -> RewindPlan:
        if record.active_leaf is None:
            raise ValueError("Exchange-tree record has no active leaf.")
        for node_id in node_ids:
            for name, entry in record.nodes[node_id].state.items():
                if name not in self._rewind_hooks:
                    raise ValueError(
                        f"Unsupported rewind state entry {name!r}."
                    )
                self._validate_restore_state_entry(name, entry)

        planned: list[tuple[str, RewindHook, StatePathContext]] = []
        for name, hook in self._rewind_hooks.items():
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
                bootstrap="recorded",
            )
            if name == "shinychat:turns":
                if preserve_live_turns:
                    adapter = self._adapter
                    include_system_prompt = getattr(
                        adapter, "is_chatlas", lambda: False
                    )()
                    prepared_turns = self._canonical_turns(
                        adapter.get_turns_json(
                            include_system_prompt=include_system_prompt
                        )
                    )[0]
                    turns_unavailable = True
                    context = dataclasses.replace(context, bootstrap="live")
                else:
                    prepared_turns, turns_unavailable = (
                        self._materialize_restore_turns(context)
                    )
                    if turns_unavailable:
                        raise ValueError(
                            "Unsupported shinychat:turns state entry."
                        )
                context = dataclasses.replace(
                    context,
                    prepared_turns=prepared_turns,
                    turns_unavailable=turns_unavailable,
                )
            planned.append((name, hook, context))
        return tuple(planned)

    async def _rewind_state(self, planned: RewindPlan) -> None:
        for _, hook, context in planned:
            result = hook(context)
            if inspect.isawaitable(result):
                await result

    async def _rewind_non_turn_state(self, planned: RewindPlan) -> None:
        for name, hook, context in planned:
            if name == "shinychat:turns":
                continue
            result = hook(context)
            if inspect.isawaitable(result):
                await result
