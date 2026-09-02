from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import warnings
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, cast

from pydantic import JsonValue

from ._attachments import Attachment, validate_attachments
from ._chat_transcript import TranscriptEntry
from ._chat_types import (
    ExchangeMetadata,
    HistoryAcceptedInputProjectionAction,
    HistoryEditProjectionAction,
    HistoryNavigateAction,
    HistoryUpdateAction,
    StoredMessage,
    StoredSegment,
    UpdateExchangeMetadataAction,
    UpdateInputAction,
    UpdateSiblingsAction,
)
from ._history_bookmark import delete_bookmark_state, extract_state_id
from ._history_client import (
    TurnsAdapter,
    _validate_mapping_keys,
    as_turns_adapter,
    turn_fallback_markdown,
)
from ._history_store import (
    ConversationPartition,
    ConversationStore,
    resolve_store,
)
from ._history_title import (
    MAX_TITLE_LEN,
    TitleFn,
    fallback_title,
    generate_title,
)

# NB: shiny is imported lazily inside methods throughout this module; a
# top-level import would be circular (shiny.ui._chat imports shinychat).
from ._history_types import (
    CapturedMessage,
    ConversationRecord,
    ConversationRecordV2,
    StateEntry,
    check_schema_version,
    new_conversation_id,
    new_conversation_record,
    new_conversation_record_v2,
    project_history_error_message,
)

if TYPE_CHECKING:
    from htmltools import HTML, Tag, TagList
    from shiny import reactive
    from shiny.module import ResolvedId
    from shiny.reactive._reactives import Effect_

    from ._chat import Chat
    from ._chat_types import ChatGreeting


_EXCHANGE_TREE_HISTORY_V2 = False


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


@dataclasses.dataclass(frozen=True)
class HistoryInputIds:
    """All Shiny input IDs owned by the history feature for a given chat."""

    browser_token: ResolvedId
    current_id: ResolvedId
    url_id: ResolvedId
    select: ResolvedId
    new: ResolvedId
    rename: ResolvedId
    delete: ResolvedId
    message_edit: ResolvedId
    message_navigate: ResolvedId
    message_resubmit: ResolvedId

    @classmethod
    def for_chat(cls, chat_id: ResolvedId) -> HistoryInputIds:
        from shiny.module import ResolvedId as RID

        return cls(
            browser_token=RID(f"{chat_id}_history_browser_token"),
            current_id=RID(f"{chat_id}_history_current_id"),
            url_id=RID(f"{chat_id}_history_url_id"),
            select=RID(f"{chat_id}_history_select"),
            new=RID(f"{chat_id}_history_new"),
            rename=RID(f"{chat_id}_history_rename"),
            delete=RID(f"{chat_id}_history_delete"),
            message_edit=RID(f"{chat_id}_message_edit"),
            message_navigate=RID(f"{chat_id}_message_navigate"),
            message_resubmit=RID(f"{chat_id}_message_resubmit"),
        )

    def all_ids(self) -> list[ResolvedId]:
        return [getattr(self, f.name) for f in dataclasses.fields(self)]


class HistoryOptions:
    """
    Configuration for :class:`~shinychat.Chat` conversation history.

    Pass an instance to ``Chat(history=...)``.

    Parameters
    ----------
    restore_mode
        How a previous conversation is reloaded when the page opens.
        ``"browser"`` (the default) stores the active conversation ID in
        localStorage so it survives page reloads without changing the URL.
        ``"url"`` keeps the active conversation ID as a plain
        ``?shinychat_conversation_id=<id>`` query parameter so users can
        bookmark or share a link to a specific conversation; no Shiny server
        bookmarking is required.
        ``"none"`` disables automatic restore entirely.
        ``"bookmark"`` participates in Shiny server bookmarking: after every
        LLM response a fresh server bookmark is minted and the address bar
        updates to ``?_state_id_=...``. Requires ``bookmark_store="server"``
        in the Shiny app. On in-session conversation switches, navigates to
        the target conversation's bookmark URL if one exists. Use this mode
        when the app uses Shiny bookmarks to capture full input state
        alongside the chat.

        The ``values`` dict captured by ``@chat.history.on_save`` callbacks
        is restored by ``@chat.history.on_restore`` in every restore mode,
        including ``"bookmark"``. Callbacks run after the target conversation
        becomes active. Raw Shiny input values (sliders, text boxes, etc.) are
        not synced automatically; use ``on_restore`` to update them on both
        page-load restores and in-session switches.
    store
        Where conversations are persisted. ``"auto"`` (the default) picks
        ``FileConversationStore`` in most environments and defers to the
        platform on Posit Connect. ``"memory"`` keeps conversations in
        process only (useful for testing). ``"file"`` always uses the file
        system. Pass a fully-constructed ``ConversationStore`` instance for
        custom back-ends.
    scope
        Storage namespace for conversations. A string or a callable that
        returns a string. When ``None`` (the default) the authenticated
        ``session.user`` is used; for unauthenticated sessions a
        per-browser localStorage token is used instead.

        Pass a shared string to allow multiple users to share history —
        for example ``session.groups[0]`` to scope by group, or a
        constant like ``"global"`` to share across all users.
    title
        Controls how a new conversation is named. ``"auto"`` (the default)
        generates a title from the first exchange using the LLM. Pass a
        ``TitleFn`` callable to use custom logic instead. Pass ``None`` to
        skip LLM titling entirely — the conversation keeps its initial
        timestamp-based name.
    restore_bootstrap
        How a v2 exchange-tree restore initializes client turns.
        ``"recorded"`` reconstructs them entirely from saved state entries.
        ``"live"`` preserves the app's current turns and skips only the
        implicit root snapshot before applying later entries.
    """

    def __init__(
        self,
        restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = "browser",
        store: "ConversationStore | Literal['auto', 'memory', 'file']" = "auto",
        scope: "str | Callable[..., str] | None" = None,
        title: "TitleFn | Literal['auto'] | None" = "auto",
        max_store_mb: float | None = 100.0,
        restore_bootstrap: "Literal['recorded', 'live']" = "recorded",
    ) -> None:
        self.restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = (
            restore_mode
        )
        self.store: "ConversationStore | Literal['auto', 'memory', 'file']" = (
            store
        )
        self.scope: "str | Callable[..., str] | None" = scope
        self.title: "TitleFn | Literal['auto'] | None" = title
        self.max_store_mb: float | None = max_store_mb
        self.restore_bootstrap: "Literal['recorded', 'live']" = (
            restore_bootstrap
        )


def extend_record_linear(
    record: ConversationRecord,
    turn_groups: list[list[dict[str, Any]]],
    ui_messages: list[dict[str, Any]],
) -> None:
    """
    Append turn groups beyond the record's current path, then reconstruct the
    active path's UI from the server-owned transcript. Each user message goes
    to the next user-turn node; later UI-only messages stay with the first
    response node after that input.

    Each group is one or more turns that form a single exchange unit — e.g. a
    tool-call round (assistant-request, user-result, assistant-text) is one
    group, matching the single combined UI message produced by streaming.
    """
    existing = len(record.path_node_ids())
    new_groups = turn_groups[existing:]

    for group in new_groups:
        record.append_linear(group)
    path = record.path_node_ids()
    fallback = path[-1] if path else None
    if fallback is None:
        return

    for node_id in path:
        record.nodes[node_id].ui = None

    next_user_index = 0
    response_node_id = fallback
    for message in ui_messages:
        if message.get("role") == "user":
            for index in range(next_user_index, len(path)):
                node_id = path[index]
                if record.nodes[node_id].turns[0].get("role") != "user":
                    continue
                target = node_id
                next_user_index = index + 1
                response_node_id = fallback
                for response_id in path[next_user_index:]:
                    if record.nodes[response_id].turns[0].get("role") != "user":
                        response_node_id = response_id
                        break
                break
            else:
                target = response_node_id
        else:
            target = response_node_id
        node = record.nodes[target]
        node.ui = [*(node.ui or []), message]


def _history_transition_request_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    request_id = value.get("requestId")
    return request_id if isinstance(request_id, str) else None


async def _complete_history_transition(chat: "Chat", request_id: str) -> None:
    try:
        await chat._send_action(
            {
                "type": "history_transition_complete",
                "requestId": request_id,
            }
        )
    except (asyncio.CancelledError, Exception):
        # Completion is advisory and must not alter the transition outcome.
        pass


class _ExchangeRecorder:
    """Private v2 capture owner for one history controller session."""

    def __init__(self, controller: HistoryController) -> None:
        self._controller = controller
        self.record: ConversationRecordV2 | None = None
        self._stream_exchanges: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._capture_hooks: dict[str, CaptureHook] = {}
        self._restore_hooks: dict[str, RestoreHook] = {}
        self._rewind_hooks: dict[str, RewindHook] = {}
        self._turn_baseline: list[str] = []
        self._active_id_published_for: ConversationRecordV2 | None = None
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
        adapter = self._controller.adapter
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
            if getattr(self._controller.adapter, "is_chatlas", lambda: False)()
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
        adapter = self._controller.adapter
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
        adapter = self._controller.adapter
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
                    adapter = self._controller.adapter
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

    def install_restored_record(self, record: ConversationRecordV2) -> None:
        self.record = record
        self._stream_exchanges.clear()
        self._active_id_published_for = None

    async def _new_record(self, *, title: str) -> ConversationRecordV2:
        return new_conversation_record_v2(
            title=title,
            id=self._controller._allocate_conversation_id(),
            client_info={
                str(key): str(value)
                for key, value in self._controller.adapter.client_info().items()
            },
        )

    async def _content_exchange(
        self, exchange_id: str | None
    ) -> tuple[str | None, bool]:
        if self.record is None:
            if exchange_id is not None:
                return None, False
            self.record = await self._new_record(title="New chat")
            return self.record.active_leaf, True
        if exchange_id is not None:
            return (
                exchange_id if exchange_id in self.record.nodes else None,
                False,
            )
        return self.record.open_inputless_exchange(), False

    def reset(self) -> None:
        self.record = None
        self._stream_exchanges.clear()
        self._turn_baseline.clear()
        self._active_id_published_for = None

    @contextmanager
    def suspend_capture(self):
        transcript = self._controller.chat._transcript
        transcript.set_capture_callbacks(
            on_accepted_input=None,
            on_message_committed=None,
            on_stream_started=None,
            on_stream_updated=None,
            on_stream_finished=None,
        )
        try:
            yield
        finally:
            transcript.set_capture_callbacks(
                on_accepted_input=self.accepted_input,
                on_message_committed=self.message_committed,
                on_stream_started=self.stream_started,
                on_stream_updated=self.stream_updated,
                on_stream_finished=self.stream_finished,
            )

    async def _persist_record(self) -> None:
        record = self.record
        assert record is not None
        record_id = record.id
        partition = self._controller.partition
        assert partition is not None
        await self._controller.store.put(partition, record)
        if (
            self.record is not record
            or self._controller._active_id_now() != record_id
        ):
            return

        if self._active_id_published_for is not record:
            publisher = getattr(self._controller, "_publish_active_v2_id", None)
            if publisher is not None:
                published = await publisher(record)
            else:
                callback = self._controller.on_active_id_change
                if callback is not None:
                    await callback(record_id)
                published = (
                    self.record is record
                    and self._controller._active_id_now() == record_id
                )
            if published:
                self._active_id_published_for = record

    def _capture_app_state(self) -> None:
        assert self.record is not None
        values: dict[str, Any] = {}
        for callback in self._controller._save_callbacks:
            callback(values)
        self.record.values = values

    async def save_current(self) -> bool:
        async with self._lock:
            return await self.save_current_locked()

    async def save_current_locked(self) -> bool:
        if self.record is None or self._controller.partition is None:
            return False
        self._capture_app_state()
        await self._persist_record()
        return True

    async def response_settled(self) -> bool:
        async with self._lock:
            if self.record is None or self._controller.partition is None:
                return False
            self._capture_app_state()
            self.record.response_count += 1
            await self._persist_record()
            return True

    async def rename_active_locked(self, conv_id: str, title: str) -> bool:
        if (
            self.record is None
            or self.record.id != conv_id
            or self._controller.partition is None
        ):
            return False
        self.record.title = title
        self.record.title_source = "user"
        await self._persist_record()
        return True

    async def bookmark_pointer(
        self, record: ConversationRecordV2 | None = None
    ) -> tuple[str, str] | None:
        """Return one atomic pointer snapshot for a live v2 record."""
        async with self._lock:
            active = self.record
            if (
                active is None
                or active.active_leaf is None
                or (record is not None and active is not record)
            ):
                return None
            return active.id, active.active_leaf

    async def settle_bookmark_state_id(
        self, conversation_id: str, node_id: str, state_id: str
    ) -> tuple[bool, str | None]:
        """Persist a bookmark URL only when its pointer is still active.

        The returned state id is safe to delete: it is either the replaced URL
        after a successful update or the newly minted stale URL.
        """
        async with self._lock:
            record = self.record
            if (
                record is None
                or record.id != conversation_id
                or record.active_leaf != node_id
            ):
                return False, state_id

            old_state_id = record.bookmark_state_id
            record.bookmark_state_id = state_id
            try:
                await self._persist_record()
            except BaseException:
                record.bookmark_state_id = old_state_id
                raise
            return True, old_state_id if old_state_id != state_id else None

    def mark_active_id_published(self, record: ConversationRecordV2) -> None:
        if (
            self.record is record
            and self._controller._active_id_now() == record.id
        ):
            self._active_id_published_for = record

    def _close_root_if_inactive(self) -> None:
        assert self.record is not None
        root_id = "n_0000"
        root = self.record.nodes.get(root_id)
        if (
            root is not None
            and root.status == "pending"
            and root_id not in self._stream_exchanges.values()
        ):
            self.record.finish_exchange(root_id, "ok", None)

    async def accepted_input(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        controller = self._controller
        if controller.partition is None:
            return

        async with self._lock:
            created = False
            if self.record is None:
                title = (
                    " ".join(message.content.split())[:MAX_TITLE_LEN]
                    or "New chat"
                )
                self.record = await self._new_record(title=title)
                created = True
            root_id = "n_0000"
            is_first_input = not any(
                node.input is not None for node in self.record.nodes.values()
            )
            if is_first_input:
                await self._capture_state(root_id, "root_close")
                self._close_root_if_inactive()
            else:
                active_leaf = self.record.active_leaf
                assert active_leaf is not None
                await self._capture_state(active_leaf, "node_close")
            self.record.open_exchange(exchange_id, message)
            await self._persist_record()
            send_history_update = getattr(
                controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def _accepted_resubmit_input_locked(
        self, exchange_id: str, message: StoredMessage
    ) -> None:
        """Open a degraded-resubmit sibling without closing its shared parent."""
        if self._controller.partition is None:
            raise RuntimeError("HistoryController not initialized")

        if self.record is None:
            raise RuntimeError("No exchange-tree conversation is active")
        self.record.open_exchange(exchange_id, message)
        self._invalidate_turn_baseline()
        self.record.nodes[exchange_id].state["shinychat:turns"] = (
            self._capture_turns(
                CaptureContext(node_id=exchange_id, reason="node_close")
            )
        )
        await self._persist_record()

    async def message_committed(
        self, exchange_id: str | None, entry: TranscriptEntry
    ) -> None:
        if entry.message.role not in ("user", "assistant"):
            return
        if self._controller.partition is None:
            return

        async with self._lock:
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            self.record.append_message(
                target,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()
            send_history_update = getattr(
                self._controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def stream_started(
        self,
        stream_id: str,
        exchange_id: str | None,
        entry: TranscriptEntry,
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            target, created = await self._content_exchange(exchange_id)
            if target is None:
                return
            assert self.record is not None
            self._stream_exchanges[stream_id] = target
            self.record.append_stream_message(
                target,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()
            send_history_update = getattr(
                self._controller, "send_history_update", None
            )
            if created and send_history_update is not None:
                await send_history_update()

    async def stream_updated(
        self, stream_id: str, entry: TranscriptEntry
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            self.record.replace_stream_message(
                exchange_id,
                CapturedMessage.from_stored_message(
                    entry.message, icon=entry.icon
                ),
            )
            await self._persist_record()

    async def stream_finished(
        self,
        stream_id: str,
        status: Literal["ok", "cancelled", "error"],
        error: str | None,
    ) -> None:
        if self._controller.partition is None:
            return

        async with self._lock:
            exchange_id = self._stream_exchanges.get(stream_id)
            if exchange_id is None or self.record is None:
                return
            await self._capture_state(exchange_id, "stream_finish")
            self.record.finish_exchange(exchange_id, status, error)
            await self._persist_record()
            self._stream_exchanges.pop(stream_id, None)


class HistoryController:
    """Session-scoped orchestrator for conversation history."""

    def __init__(
        self,
        *,
        chat: Chat,
        adapter: TurnsAdapter,
        store: ConversationStore,
        title_fn: TitleFn | None,
        title_enabled: bool,
        client: Any,
        save_callbacks: "list[Callable[[dict[str, Any]], None]] | None" = None,
        restore_callbacks: "list[Callable[[dict[str, Any]], None]] | None" = None,
        max_store_bytes: int | None = None,
        use_exchange_tree: bool = False,
        restore_bootstrap: Literal["recorded", "live"] = "recorded",
    ):
        self.chat = chat
        self.adapter = adapter
        self.store = store
        self.title_fn = title_fn
        self.title_enabled = title_enabled
        self.client = client
        # List references: mutations to the originals (e.g. registering new
        # callbacks after _start()) are visible here because we share the same
        # list object, not a copy.
        self._save_callbacks: list[Callable[[dict[str, Any]], None]] = (
            save_callbacks if save_callbacks is not None else []
        )
        self._restore_callbacks: list[Callable[[dict[str, Any]], None]] = (
            restore_callbacks if restore_callbacks is not None else []
        )

        self.partition: ConversationPartition | None = None
        self.record: ConversationRecord | None = None  # None => unsaved draft
        # Active conversation identity, separate from `record`: an
        # identified draft (submitted but not yet saved) has an ID and no
        # record. All record/identity mutations go through
        # activate_record()/clear_active() so that when a record exists, its
        # `id` equals the active ID.
        from shiny import reactive

        self._active_id: "reactive.Value[str | None]" = reactive.Value(None)
        # Set by enable() when restore_mode="url"; called with the new
        # conversation id (or None) after any switch that changes the active
        # conversation.
        self.on_active_id_change: (
            Callable[[str | None], Awaitable[None]] | None
        ) = None
        # Internal hook: fired after every save. bookmark mode uses it to mint.
        self.on_response_saved: (
            Callable[[ConversationRecord], Awaitable[None]] | None
        ) = None
        # Internal hook: fired in switch_to before the in-session swap.
        # Return True to skip the swap (caller has already navigated).
        self.on_pre_switch: (
            Callable[[ConversationRecord], Awaitable[bool]] | None
        ) = None
        # Internal hook: fired before a conversation is removed from the store.
        self.on_evict: Callable[[str], Awaitable[None]] | None = None
        # Internal hook: fired whenever it's known whether the active
        # conversation is a restore (True) or a fresh/new one (False) - at
        # the initial restore decision, and again on every new_chat(). Lets
        # greeting generation defer to this instead of racing the client's
        # independent `{id}_greeting_requested` request.
        self.on_settled: Callable[[bool], Awaitable[None]] | None = None
        self.max_store_bytes: int | None = max_store_bytes
        self.restore_bootstrap: Literal["recorded", "live"] = restore_bootstrap
        self._title_task: asyncio.Task[None] | None = None
        self._over_budget_warned: bool = False
        self._exchange_recorder = (
            _ExchangeRecorder(self) if use_exchange_tree else None
        )

    # -- active conversation identity --------------------------------------

    def conversation_id(self) -> str | None:
        """
        Reactive read of the active conversation ID: ``None`` for an empty
        draft, otherwise the ID the eventual ``ConversationRecord`` will (or
        already does) carry. Allocated at first user submission for
        ``chat_app()`` apps, or at first save for standalone history use.

        Like any reactive read, this requires a reactive context;
        non-reactive callers must wrap it in ``shiny.reactive.isolate()``.
        """
        return self._active_id()

    def _active_id_now(self) -> str | None:
        # Non-reactive read: controller methods run both inside and outside
        # reactive contexts.
        from shiny import reactive

        with reactive.isolate():
            return self._active_id()

    def _allocate_conversation_id(self) -> str:
        id = self._active_id_now()
        if id is None:
            id = new_conversation_id()
            self._active_id.set(id)
        return id

    async def ensure_conversation_id(self) -> str:
        """
        Return the active conversation ID, allocating one when the active
        conversation is an empty draft. Repeated calls for the same active
        conversation return the same ID.
        """
        id = self._active_id_now()
        if id is None:
            id = self._allocate_conversation_id()
            if (
                self._exchange_recorder is None
                and self.on_active_id_change is not None
            ):
                await self.on_active_id_change(id)
        return id

    async def activate_record(self, record: ConversationRecord) -> None:
        """
        Activate a stored record. This (with ``clear_active()``) is the
        shared operation every restore/switch/init/delete/new-chat path must
        use, so that ``record`` and the active ID never move independently:
        when ``record`` is not ``None``, the active ID must equal
        ``record.id``.
        """
        self.record = record
        await self._set_active_id(record.id)

    async def clear_active(self) -> None:
        self.record = None
        if self._active_id_now() is not None:
            self._active_id.set(None)

    async def _set_active_id(self, id: str | None) -> None:
        # Single writer for the active ID; notifies on_active_id_change only
        # on an actual change (e.g. first save after ensure_conversation_id()
        # does not re-fire).
        if self._active_id_now() == id:
            return
        self._active_id.set(id)
        if self.on_active_id_change is not None:
            await self.on_active_id_change(id)

    async def _publish_active_v2_id(self, record: ConversationRecordV2) -> bool:
        if self._active_id_now() != record.id:
            return False
        if self.on_active_id_change is not None:
            await self.on_active_id_change(record.id)
        recorder = self._exchange_recorder
        return (
            recorder is not None
            and recorder.record is record
            and self._active_id_now() == record.id
        )

    async def _get_record(
        self, partition: ConversationPartition, conv_id: str
    ) -> ConversationRecord | ConversationRecordV2 | None:
        record = await self.store.get(partition, conv_id)
        if record is not None:
            check_schema_version(record.schema_version)
            expected_type = (
                ConversationRecordV2
                if self._exchange_recorder is not None
                else ConversationRecord
            )
            if not isinstance(record, expected_type):
                raise ValueError(
                    "Conversation record schema does not match the active history path."
                )
        return record

    async def _put_record(
        self, partition: ConversationPartition, record: ConversationRecord
    ) -> None:
        check_schema_version(record.schema_version)
        await self.store.put(partition, record)

    @asynccontextmanager
    async def _destructive_mutation(self, *, block_input: bool = False):
        if block_input:
            async with self.chat._destructive_history_mutation(
                block_input=True
            ):
                yield
            return
        async with self.chat._destructive_history_mutation():
            yield

    @asynccontextmanager
    async def _exchange_mutation(self):
        if self._exchange_recorder is None:
            yield
            return
        async with self._exchange_recorder._lock:
            yield

    # -- save -----------------------------------------------------------

    async def on_response(self) -> None:
        """Save trigger: a completed assistant response.

        A private response lifecycle callback is the only automatic caller.
        It fires after a completed assistant append or a stream terminal
        outcome, so replay, clear, accepted input, and partial chunks do not
        settle history.
        """
        recorder = self._exchange_recorder
        if recorder is not None:
            if not await recorder.response_settled():
                return
            record = recorder.record
            assert record is not None
            await self._evict_if_needed()
            if self.on_response_saved is not None:
                await self.on_response_saved(cast(ConversationRecord, record))
            await self.send_history_update()
            await self._send_sibling_metadata()
            return
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        turn_groups = self.adapter.get_turns_grouped()
        messages = self.chat._messages_for_history()

        first_save = self.record is None
        if first_save:
            turns_flat = self.adapter.get_turns_json()
            # Adopt the active ID allocated at submission time (or allocate
            # one now for standalone history users), so the saved record
            # carries the identity model work was already tagged with.
            new_record = new_conversation_record(
                title=fallback_title(turns_flat),
                id=await self.ensure_conversation_id(),
            )
            new_record.client_info = self.adapter.client_info()
            await self.activate_record(new_record)

        record = self.record
        if record is None:
            raise RuntimeError("HistoryController not initialized")
        extend_record_linear(record, turn_groups, messages)
        record.response_count += 1
        self._capture_app_state(record)
        await self._put_record(self.partition, record)
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(record)
        await self.send_history_update()
        await self._send_sibling_metadata()

        # Wait for the second response before titling: gives the LLM/custom
        # title_fn more context than a single exchange, and avoids spending
        # a call on conversations abandoned after one message. response_count
        # (not turn/node counts) drives this, since a single response's
        # turn-group count isn't fixed across client types.
        if (
            self.title_enabled
            and record.title_source is None
            and record.response_count == 2
        ):
            turns_flat = self.adapter.get_turns_json()
            self._title_task = asyncio.create_task(self.retitle(turns_flat))
            self._title_task.add_done_callback(title_task_done)

    async def retitle(self, turns: list[dict[str, Any]]) -> None:
        target = self.record  # capture before the slow LLM call
        if target is None or target.title_source == "user":
            return
        title = await generate_title(self.title_fn, self.client, turns)
        if (
            title is None
            or self.record is not target
            or target.title_source == "user"
        ):
            return  # conversation switched away or user renamed mid-call
        target.title = title
        target.title_source = "llm"
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        await self._put_record(self.partition, target)
        await self.send_history_update()

    def cancel_pending(self) -> None:
        """Cancel in-flight background work (e.g. titling) at teardown."""
        if self._title_task is not None and not self._title_task.done():
            self._title_task.cancel()

    async def notify_settled(self, restored: bool) -> None:
        """Called whenever it's known whether the active conversation is a restore."""
        if self.on_settled is not None:
            await self.on_settled(restored)

    async def _evict_one(self, conv_id: str) -> None:
        assert self.partition is not None
        if self.on_evict is not None:
            await self.on_evict(conv_id)
        await self.store.delete(self.partition, conv_id)

    async def _evict_if_needed(self) -> None:
        if self.max_store_bytes is None or self.partition is None:
            return
        active_record = (
            self._exchange_recorder.record
            if self._exchange_recorder is not None
            else self.record
        )
        metas = await self.store.list(self.partition)
        total = sum(m.size_bytes for m in metas)
        if total <= self.max_store_bytes:
            return
        for meta in reversed(metas):  # oldest first
            if active_record is not None and meta.id == active_record.id:
                continue
            total -= meta.size_bytes
            await self._evict_one(meta.id)
            if total <= self.max_store_bytes:
                break
        if total > self.max_store_bytes and not self._over_budget_warned:
            self._over_budget_warned = True
            warnings.warn(
                "Chat history for this partition remains over the "
                f"{self.max_store_bytes}-byte limit after evicting all "
                "evictable conversations — the active conversation alone "
                "exceeds the limit.",
                stacklevel=1,
            )

    async def save(self) -> bool:
        """Persist app state for the active conversation."""
        if not await self.save_current():
            return False
        record = (
            self._exchange_recorder.record
            if self._exchange_recorder is not None
            else self.record
        )
        assert record is not None
        await self._evict_if_needed()
        if self.on_response_saved is not None:
            await self.on_response_saved(cast(ConversationRecord, record))
        await self.send_history_update()
        await self._send_sibling_metadata()
        return True

    async def save_current(self) -> bool:
        """Persist the active conversation if it has ever been saved."""
        if self._exchange_recorder is not None:
            return await self._exchange_recorder.save_current()
        if self.record is None or self.partition is None:
            return False
        turn_groups = self.adapter.get_turns_grouped()
        messages = self.chat._messages_for_bookmark()
        extend_record_linear(self.record, turn_groups, messages)
        self._capture_app_state(self.record)
        await self._put_record(self.partition, self.record)
        return True

    def _capture_app_state(self, record: ConversationRecord) -> None:
        values: dict[str, Any] = {}
        for cb in self._save_callbacks:
            cb(values)
        record.values = values

    def _restore_app_state(self, values: dict[str, Any]) -> None:
        for cb in self._restore_callbacks:
            cb(values)

    async def _notify_restore_failure(
        self, *, recovery_incomplete: bool
    ) -> None:
        from shiny import ui as shiny_ui
        from shiny.session import session_context

        message = (
            "Could not restore conversation. Recovery was incomplete; reload "
            "before starting a new chat."
            if recovery_incomplete
            else "Could not restore conversation. A fresh chat is ready."
        )
        with session_context(self.chat._session):
            shiny_ui.notification_show(
                message,
                type="error",
            )

    async def _notify_turns_unavailable(self) -> None:
        from shiny import ui as shiny_ui
        from shiny.session import session_context

        with session_context(self.chat._session):
            shiny_ui.notification_show(
                "Conversation display was restored, but model context was unavailable.",
                type="warning",
            )

    async def _clear_failed_restore(self) -> None:
        recorder = self._exchange_recorder
        assert recorder is not None

        # Local ownership is cleared synchronously before any cleanup can
        # suspend, so a subsequent accepted input always creates a fresh draft.
        recorder.reset()
        self.record = None
        self._active_id.set(None)

        cleanup_failures: list[BaseException] = []
        async def best_effort(operation: Callable[[], Any]) -> None:
            try:
                result = operation()
                if inspect.isawaitable(result):
                    await result
            except BaseException as error:
                cleanup_failures.append(error)

        await best_effort(self.chat.clear_messages)
        await best_effort(lambda: self.adapter.set_turns_json([]))
        await best_effort(lambda: self.chat.set_greeting(None))
        active_id_callback = self.on_active_id_change
        if active_id_callback is not None:
            await best_effort(lambda: active_id_callback(None))
        try:
            await self.send_history_update()
        except BaseException as error:
            cleanup_failures.append(error)
        else:
            history = getattr(self.chat, "history", None)
            if (
                history is not None
                and not history._initial_history_initialized
            ):
                history._initial_history_initialized = True
        try:
            await self._notify_restore_failure(
                recovery_incomplete=bool(cleanup_failures)
            )
        except BaseException:
            # The original restore error or cancellation remains the outcome.
            pass

    async def replay_exchange_record(
        self, record: ConversationRecordV2 | None = None
    ) -> None:
        if self._exchange_recorder is None:
            raise RuntimeError("Exchange-tree history is not enabled")
        target = self._exchange_recorder.record if record is None else record
        if target is not None:
            await self._restore_exchange_record(target)

    def _prepare_exchange_restore(
        self,
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> tuple[tuple[str, ...], RestorePlan, Literal["recorded", "live"]]:
        recorder = self._exchange_recorder
        if recorder is None:
            raise RuntimeError("Exchange-tree history is not enabled")

        # Validate the entire path before this transaction clears the current
        # display or mutates the attached client.
        node_ids = tuple(target.path_node_ids())
        if not node_ids or target.active_leaf is None:
            raise ValueError("Exchange-tree record has no active path.")
        selected_bootstrap = (
            self.restore_bootstrap if bootstrap is None else bootstrap
        )
        planned_state = recorder._preflight_restore_state(
            target, node_ids, selected_bootstrap
        )
        return node_ids, planned_state, selected_bootstrap

    async def _restore_exchange_record_locked(
        self,
        target: ConversationRecordV2,
        *,
        node_ids: tuple[str, ...],
        planned_state: RestorePlan,
        bootstrap: Literal["recorded", "live"],
        persist_active_pointer: bool = False,
    ) -> None:
        recorder = self._exchange_recorder
        assert recorder is not None

        try:
            # Live bootstrap is intentionally captured only after admission
            # and recorder serialization, but before destructive effects.
            if bootstrap == "live":
                planned_state = recorder._materialize_live_restore_turns(
                    planned_state
                )
            await self._replay_exchange_display(target, node_ids)
            await recorder._restore_state(planned_state)
            if recorder._turns_unavailable(planned_state):
                recorder._invalidate_turn_baseline()

            # `_ExchangeRecorder` remains the sole v2 record owner.
            # The controller only sequences its installation after
            # display and state consumers have accepted the target.
            self.record = None
            recorder.install_restored_record(target)
            await self._set_active_id(target.id)
            recorder.mark_active_id_published(target)
            if persist_active_pointer:
                await recorder._persist_record()
            self._restore_app_state(target.values or {})
            await self._send_exchange_metadata()
            await self._send_sibling_metadata()
            if recorder._turns_unavailable(planned_state):
                await self._notify_turns_unavailable()
            await self.send_history_update()
        except BaseException:
            await self._clear_failed_restore()
            raise

    async def _replay_exchange_display(
        self, record: ConversationRecordV2, node_ids: tuple[str, ...]
    ) -> None:
        recorder = self._exchange_recorder
        assert recorder is not None

        await self.chat.clear_messages()
        await self.chat.set_greeting(None)
        with recorder.suspend_capture():
            for node_id in node_ids:
                node = record.nodes[node_id]
                if node.input is not None:
                    await self.chat._restore_bookmark_message(
                        node.input.model_dump(mode="json")
                    )
                for message in node.messages:
                    await self.chat._restore_bookmark_message(
                        message.as_stored_message().model_dump(mode="json"),
                        icon=message.icon,
                    )

    async def _restore_exchange_record(
        self,
        target: ConversationRecordV2,
        *,
        bootstrap: Literal["recorded", "live"] | None = None,
    ) -> None:
        node_ids, planned_state, selected_bootstrap = (
            self._prepare_exchange_restore(target, bootstrap=bootstrap)
        )

        async with self._destructive_mutation():
            async with self._exchange_mutation():
                await self._restore_exchange_record_locked(
                    target,
                    node_ids=node_ids,
                    planned_state=planned_state,
                    bootstrap=selected_bootstrap,
                )

    async def _restore_initial_exchange_record(
        self,
        target: ConversationRecordV2,
        *,
        node_id: str | None = None,
    ) -> None:
        """Restore an initial target, recovering only preflight failures."""
        selected = target
        persist_active_pointer = False
        try:
            if node_id is not None:
                selected = target.model_copy(deep=True)
                selected.set_active_leaf(node_id)
                persist_active_pointer = target.active_leaf != node_id
            node_ids, planned_state, bootstrap = (
                self._prepare_exchange_restore(selected)
            )
        except BaseException:
            # Initial restore has no surrounding transaction to recover a
            # failed preflight. Keep the shared restore methods fail-closed.
            await self._clear_failed_restore()
            raise

        restore_body_entered = False
        try:
            async with self._destructive_mutation():
                async with self._exchange_mutation():
                    restore_body_entered = True
                    await self._restore_exchange_record_locked(
                        selected,
                        node_ids=node_ids,
                        planned_state=planned_state,
                        bootstrap=bootstrap,
                        persist_active_pointer=persist_active_pointer,
                    )
        except BaseException:
            if not restore_body_entered:
                await self._clear_failed_restore()
            raise

    async def restore_bookmark_pointer(
        self, target: ConversationRecordV2, node_id: str
    ) -> None:
        """Restore a validated v2 bookmark node through the normal transaction."""
        recorder = self._exchange_recorder
        if recorder is None:
            raise RuntimeError("Exchange-tree history is not enabled")

        selected = target.model_copy(deep=True)
        selected.set_active_leaf(node_id)
        node_ids, planned_state, bootstrap = self._prepare_exchange_restore(selected)
        persist_active_pointer = target.active_leaf != node_id

        async with self._destructive_mutation():
            async with self._exchange_mutation():
                await self._restore_exchange_record_locked(
                    selected,
                    node_ids=node_ids,
                    planned_state=planned_state,
                    bootstrap=bootstrap,
                    persist_active_pointer=persist_active_pointer,
                )

    # -- switch / new ----------------------------------------------------

    async def switch_to(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        if self._active_id_now() == conv_id:
            return
        # Load BEFORE mutating anything: a failed load must leave the
        # current conversation untouched.
        target = await self._get_record(self.partition, conv_id)
        if target is None:
            raise RuntimeError(f"Conversation {conv_id!r} no longer exists.")
        if isinstance(target, ConversationRecordV2):
            from shiny import reactive

            with reactive.isolate():
                stream_is_running = (
                    self.chat.latest_message_stream.status() == "running"
                )
            if stream_is_running:
                raise RuntimeError(
                    "Cannot switch conversations while a message stream is active."
                )
            recorder = self._exchange_recorder
            assert recorder is not None
            async with self._destructive_mutation(block_input=True):
                async with self._exchange_mutation():
                    await recorder.save_current_locked()
                    target = await self._get_record(self.partition, conv_id)
                    if target is None:
                        raise RuntimeError(
                            f"Conversation {conv_id!r} no longer exists."
                        )
                    assert isinstance(target, ConversationRecordV2)
                    node_ids, planned_state, bootstrap = (
                        self._prepare_exchange_restore(target)
                    )
                    await self._restore_exchange_record_locked(
                        target,
                        node_ids=node_ids,
                        planned_state=planned_state,
                        bootstrap=bootstrap,
                    )
            return

        async with self._destructive_mutation():
            await self.save_current()
            if self.on_pre_switch is not None:
                skip = await self.on_pre_switch(target)
                if skip:
                    return
            self.adapter.set_turns_json(target.path_turns())
            await self.replay_ui(target)
            await self.activate_record(target)
            self._restore_app_state(target.values or {})
            await self._send_sibling_metadata()
            await self.send_history_update()

    async def new_chat(self) -> None:
        async with self._destructive_mutation():
            async with self._exchange_mutation():
                if self._exchange_recorder is not None:
                    await self._exchange_recorder.save_current_locked()
                else:
                    await self.save_current()
                self.adapter.set_turns_json([])
                await self.chat.clear_messages()
                # Announce the cleared state even when the active ID is already None:
                # in URL/bookmark restore modes the browser may still carry a stale
                # conversation param (e.g. after a failed restore) that only
                # on_active_id_change(None) clears.
                if self._exchange_recorder is not None:
                    self._exchange_recorder.reset()
                await self.clear_active()
                if self.on_active_id_change is not None:
                    await self.on_active_id_change(None)
                # A fresh chat is never a restore: resolve the greeting the same way
                # the initial settle does, so it doesn't just rely on a stale/absent
                # cached value from that first resolution.
                await self.notify_settled(False)
                await self.send_history_update()

    async def replay_ui(self, record: ConversationRecord) -> None:
        async with self._destructive_mutation():
            await self.chat.clear_messages()
            # A restored conversation is never a "new chat" — the app's
            # greeting doesn't belong here, regardless of `persistent`.
            await self.chat.set_greeting(None)
            for node_id in record.path_node_ids():
                node = record.nodes[node_id]
                stored = node.ui or [
                    {
                        "role": node.turns[-1].get("role", "assistant"),
                        "segments": [
                            {
                                "content": turn_fallback_markdown(
                                    node.turns[-1]
                                ),
                                "content_type": "markdown",
                            }
                        ],
                    }
                ]
                for message_dict in stored:
                    await self.chat._restore_bookmark_message(message_dict)

    @staticmethod
    def _normalize_resubmit_input(message: StoredMessage) -> StoredMessage:
        if message.role != "user":
            raise ValueError("Only user inputs can be resubmitted.")
        normalized = message.model_copy(deep=True)
        validate_attachments(normalized.attachments)
        return normalized

    @staticmethod
    def _replacement_resubmit_input(
        content: str,
        attachments: list[dict[str, Any]] | None,
    ) -> StoredMessage:
        if not isinstance(content, str):
            raise TypeError("Edited message content must be a string.")
        parsed = (
            [Attachment.model_validate(attachment) for attachment in attachments]
            if attachments is not None
            else []
        )
        validate_attachments(parsed)
        return StoredMessage(
            role="user",
            segments=[StoredSegment(content=content, content_type="markdown")],
            attachments=parsed,
        )

    async def resubmit(
        self,
        exchange_id: str,
        replacement_input: StoredMessage | None = None,
        *,
        kind: str,
        request_id: str,
        message_index: int,
    ) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        recorder = self._exchange_recorder
        if recorder is None:
            raise RuntimeError("Exchange-tree history is not enabled")
        record = recorder.record
        if record is None:
            raise RuntimeError("No exchange-tree conversation is active")

        target = record.nodes.get(exchange_id)
        if target is None:
            raise ValueError(f"Unknown exchange id {exchange_id!r}")
        if target.input is None:
            raise ValueError(
                f"Exchange {exchange_id!r} has no user input to resubmit."
            )
        if exchange_id not in record.path_node_ids():
            raise ValueError(
                f"Exchange {exchange_id!r} is not on the active path."
            )
        if target.parent_id is None:
            raise ValueError(
                f"Exchange {exchange_id!r} has no parent prefix to resubmit."
            )
        if kind == "retry":
            if target.status not in ("pending", "error", "cancelled"):
                raise ValueError("Only interrupted or failed exchanges can be retried.")
        elif kind == "regenerate":
            if target.status != "ok":
                raise ValueError("Only completed exchanges can be regenerated.")
        elif kind != "edit":
            raise ValueError(f"Unknown exchange resubmit kind {kind!r}.")
        preserve_live_turns = recorder._active_path_turns_are_incompatible(record)
        submitted_input = self._normalize_resubmit_input(
            target.input if replacement_input is None else replacement_input
        )

        # Preflight against a copy so malformed rewind state cannot move the
        # persisted path after input validation has already succeeded.
        prefix = record.model_copy(deep=True)
        prefix.set_active_leaf(target.parent_id)
        node_ids = tuple(prefix.path_node_ids())
        rewind_state = recorder._preflight_rewind_state(
            prefix,
            node_ids,
            preserve_live_turns=preserve_live_turns,
        )

        async with self._destructive_mutation(block_input=True):
            async with self._exchange_mutation():
                current_leaf = record.active_leaf
                if current_leaf is None:
                    raise ValueError("Exchange-tree record has no active leaf.")
                if preserve_live_turns:
                    # The failed target and its shared parent stay immutable.
                    # Non-turn hooks still rewind the ordinary parent prefix
                    # before the accepted input opens its sibling.
                    await recorder._rewind_non_turn_state(rewind_state)
                    record.set_active_leaf(target.parent_id)
                    accepted_exchange_id = (
                        self.chat._transcript.record_accepted_input(submitted_input)
                    )
                    await recorder._accepted_resubmit_input_locked(
                        accepted_exchange_id, submitted_input
                    )
                    accepted_input_action: HistoryAcceptedInputProjectionAction = {
                        "type": "history_accepted_input_projection",
                        "index": message_index,
                        "content": str(submitted_input.content),
                        "attachments": [
                            {
                                "mime": attachment.mime,
                                "data_url": attachment.data_url,
                                "name": attachment.name,
                                "size": attachment.size,
                            }
                            for attachment in submitted_input.attachments
                        ],
                    }
                    projection_error: BaseException | None = None
                    try:
                        await self.chat._send_action(accepted_input_action)
                    except BaseException as error:
                        projection_error = error
                        raise
                    finally:
                        try:
                            self.chat._publish_accepted_user_input(
                                submitted_input
                            )
                        except BaseException as publication_error:
                            if projection_error is None:
                                raise
                            raise projection_error from publication_error
                    return
                await recorder._capture_state(current_leaf, "node_close")
                try:
                    record.set_active_leaf(target.parent_id)
                    await recorder._persist_record()
                    await recorder._rewind_state(rewind_state)
                    action: HistoryEditProjectionAction = {
                        "type": "history_edit_projection",
                        "requestId": request_id,
                        "index": message_index,
                        "content": str(submitted_input.content),
                        "attachments": [
                            {
                                "mime": attachment.mime,
                                "data_url": attachment.data_url,
                                "name": attachment.name,
                                "size": attachment.size,
                            }
                            for attachment in submitted_input.attachments
                        ],
                    }
                    await self.chat._send_action(action)
                except BaseException:
                    await self._clear_failed_restore()
                    raise

    async def retry(
        self, exchange_id: str, *, request_id: str, message_index: int
    ) -> None:
        await self.resubmit(
            exchange_id,
            kind="retry",
            request_id=request_id,
            message_index=message_index,
        )

    async def regenerate(
        self, exchange_id: str, *, request_id: str, message_index: int
    ) -> None:
        await self.resubmit(
            exchange_id,
            kind="regenerate",
            request_id=request_id,
            message_index=message_index,
        )

    # -- list mutations ----------------------------------------------------

    async def rename(self, conv_id: str, title: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        title = " ".join(title.split())[:MAX_TITLE_LEN]
        if not title:
            return
        recorder = self._exchange_recorder
        if recorder is not None:
            renamed = False
            async with self._exchange_mutation():
                if await recorder.rename_active_locked(conv_id, title):
                    renamed = True
                else:
                    record = await self._get_record(self.partition, conv_id)
                    if record is not None:
                        record.title = title
                        record.title_source = "user"
                        if isinstance(record, ConversationRecordV2):
                            await self.store.put(self.partition, record)
                        else:
                            await self._put_record(self.partition, record)
                        renamed = True
            if renamed:
                await self.send_history_update()
            return
        record = (
            self.record
            if self.record is not None and self.record.id == conv_id
            else await self._get_record(self.partition, conv_id)
        )
        if record is None:
            return
        record.title = title
        record.title_source = "user"
        if isinstance(record, ConversationRecordV2):
            await self.store.put(self.partition, record)
        else:
            await self._put_record(self.partition, record)
        await self.send_history_update()

    async def delete(self, conv_id: str) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        async with self._destructive_mutation():
            async with self._exchange_mutation():
                if self.on_evict is not None:
                    await self.on_evict(conv_id)
                await self.store.delete(self.partition, conv_id)
                exchange_record = (
                    self._exchange_recorder.record
                    if self._exchange_recorder is not None
                    else None
                )
                if (self.record is not None and self.record.id == conv_id) or (
                    exchange_record is not None
                    and exchange_record.id == conv_id
                ):
                    if self._exchange_recorder is not None:
                        self._exchange_recorder.reset()
                    await self.clear_active()
                    self.adapter.set_turns_json([])
                    await self.chat.clear_messages()
                    if self.on_active_id_change is not None:
                        await self.on_active_id_change(None)
                await self.send_history_update()

    # -- branch navigation --------------------------------------------------

    async def _send_sibling_metadata(self) -> None:
        record = (
            self._exchange_recorder.record
            if self._exchange_recorder is not None
            else self.record
        )
        if record is None:
            return
        sibling_meta = record.path_sibling_metadata()
        if not sibling_meta:
            # No "clear all badges" payload is needed. A badge only exists at a
            # fork point (a node with >1 sibling), and forks are permanent:
            # navigating between siblings keeps that node's sibling count > 1,
            # and nothing prunes nodes from a record. So a path that currently
            # has no forks never had one, meaning there is no stale badge to
            # clear — empty here always means the client already shows none.
            return
        data: dict[int, dict[str, int]] = {}
        msg_idx = 0
        if isinstance(record, ConversationRecordV2):
            for node_id in record.path_node_ids():
                node = record.nodes[node_id]
                if node.input is not None:
                    if node_id in sibling_meta:
                        idx, total = sibling_meta[node_id]
                        data[msg_idx] = {"index": idx, "total": total}
                    msg_idx += 1
                msg_idx += len(node.messages)
        else:
            for node_id in record.path_node_ids():
                n_ui = record.nodes[node_id].ui_message_count()
                if node_id in sibling_meta:
                    idx, total = sibling_meta[node_id]
                    data[msg_idx] = {"index": idx, "total": total}
                msg_idx += n_ui
        if data:
            action: UpdateSiblingsAction = {
                "type": "update_siblings",
                "data": data,
            }
            await self.chat._send_action(action)

    async def _send_exchange_metadata(self) -> None:
        recorder = self._exchange_recorder
        if recorder is None or recorder.record is None:
            return

        data: dict[int, ExchangeMetadata] = {}
        message_index = 0
        for node_id in recorder.record.path_node_ids():
            node = recorder.record.nodes[node_id]
            if node.input is not None:
                metadata: ExchangeMetadata = {
                    "status": node.status,
                    "retryable": node.status in ("pending", "error", "cancelled"),
                }
                if node.status == "error" and node.input is not None:
                    metadata["error_message"] = project_history_error_message(
                        node.error.message if node.error is not None else None
                    )
                data[message_index] = metadata
                message_index += 1
            message_index += len(node.messages)
        if data:
            action: UpdateExchangeMetadataAction = {
                "type": "update_exchange_metadata",
                "data": data,
            }
            await self.chat._send_action(action)

    async def handle_resubmit(
        self,
        message_index: int,
        kind: str,
        *,
        request_id: str | None = None,
    ) -> None:
        recorder = self._exchange_recorder
        if recorder is None:
            return
        if request_id is None or not request_id:
            raise ValueError("Exchange-tree resubmits require a request ID.")
        record = recorder.record
        if record is None:
            return
        exchange_id = record.exchange_id_for_user_message_index(message_index)
        await self.resubmit(
            exchange_id,
            kind=kind,
            request_id=request_id,
            message_index=message_index,
        )

    async def handle_navigate(
        self,
        message_index: int,
        direction: str,
        *,
        request_id: str | None = None,
    ) -> None:
        if direction not in ("prev", "next"):
            return
        recorder = self._exchange_recorder
        if recorder is not None:
            if request_id is None or not request_id:
                raise ValueError("Exchange-tree navigation requires a request ID.")
            record = recorder.record
            if record is None:
                return

            node_id = record.exchange_id_for_user_message_index(message_index)
            siblings = record.siblings_of(node_id)
            current_pos = siblings.index(node_id)
            if direction == "prev":
                if current_pos == 0:
                    return
                target = siblings[current_pos - 1]
            else:
                if current_pos == len(siblings) - 1:
                    return
                target = siblings[current_pos + 1]

            leaf = record.subtree_leaf(target)
            projection = record.model_copy(deep=True)
            projection.set_active_leaf(leaf)
            node_ids = tuple(projection.path_node_ids())
            rewind_state = recorder._preflight_rewind_state(
                projection, node_ids
            )

            async with self._destructive_mutation(block_input=True):
                async with self._exchange_mutation():
                    current_leaf = record.active_leaf
                    if current_leaf is None:
                        raise ValueError(
                            "Exchange-tree record has no active leaf."
                        )
                    await recorder._capture_state(current_leaf, "node_close")
                    try:
                        record.set_active_leaf(leaf)
                        await recorder._persist_record()
                        await self._replay_exchange_display(record, node_ids)
                        await recorder._rewind_state(rewind_state)
                        await self._send_sibling_metadata()
                        await self._send_exchange_metadata()
                        await self.send_history_update()
                    except BaseException:
                        await self._clear_failed_restore()
                        raise
            return

        if self.record is None:
            return
        node_id, _ = self.record.node_id_for_message_index(message_index)
        siblings = self.record.siblings_of(node_id)
        current_pos = siblings.index(node_id)

        if direction == "prev":
            if current_pos == 0:
                return
            target = siblings[current_pos - 1]
        else:
            if current_pos == len(siblings) - 1:
                return
            target = siblings[current_pos + 1]

        async with self._destructive_mutation():
            leaf = self.record.subtree_leaf(target)
            self.record.set_current_leaf(leaf)
            self.adapter.set_turns_json(self.record.path_turns())
            await self.replay_ui(self.record)
            await self._send_sibling_metadata()
            if self.partition is None:
                raise RuntimeError("HistoryController not initialized")
            await self._put_record(self.partition, self.record)
            await self.send_history_update()

    async def handle_edit(
        self,
        message_index: int,
        content: str,
        attachments: "list[dict[str, Any]] | None" = None,
        *,
        request_id: str | None = None,
    ) -> None:
        recorder = self._exchange_recorder
        if recorder is not None:
            record = recorder.record
            if record is None:
                return
            if request_id is None:
                raise ValueError("Exchange-tree edits require a request ID.")
            exchange_id = record.exchange_id_for_user_message_index(message_index)
            replacement = self._replacement_resubmit_input(content, attachments)
            await self.resubmit(
                exchange_id,
                replacement,
                kind="edit",
                request_id=request_id,
                message_index=message_index,
            )
            return

        if self.record is None:
            return

        node_id, _ = self.record.node_id_for_message_index(message_index)
        fork_parent = self.record.nodes[node_id].parent

        async with self._destructive_mutation():
            # Branching happens implicitly: truncating current_leaf here means the next
            # append_linear (from the resubmit's on_response) creates a sibling under
            # fork_parent, not a child of the old leaf. We don't call branch_from here
            # because there's no new turn content yet — that arrives via on_response.
            self.record.set_current_leaf(fork_parent)
            self.adapter.set_turns_json(self.record.path_turns())
            await self.replay_ui(self.record)
            await self._send_sibling_metadata()
            action: UpdateInputAction = {
                "type": "update_input",
                "value": content,
                "submit": True,
            }
            if attachments is not None:
                # Same normalize-then-validate pattern as the regular (non-edit)
                # send path in _input_handler.py and Chat.update_user_input —
                # never trust client-side attachment validation alone.
                parsed = [Attachment.model_validate(a) for a in attachments]
                validate_attachments(parsed)
                action["attachments"] = [
                    {
                        "mime": a.mime,
                        "data_url": a.data_url,
                        "name": a.name,
                        "size": a.size,
                    }
                    for a in parsed
                ]
                # Edits always replace the attachment set — the client's staged
                # tray is a single source of truth, never a delta to append.
                action["attachment_mode"] = "set"
            await self.chat._send_action(action)

    # -- protocol ----------------------------------------------------------

    async def send_navigate(
        self,
        url: str | None,
        active_id: str | None,
        *,
        reload: bool = False,
    ) -> None:
        action: HistoryNavigateAction = {
            "type": "history_navigate",
            "url": url,
            "active_id": active_id,
        }
        if reload:
            action["reload"] = True
        await self.chat._send_action(action)

    async def send_history_update(self) -> None:
        if self.partition is None:
            raise RuntimeError("HistoryController not initialized")
        metas = await self.store.list(self.partition)
        action: HistoryUpdateAction = {
            "type": "history_update",
            "enabled": True,
            "conversations": [m.model_dump(mode="json") for m in metas],
            "active_id": self._active_id_now(),
            "transition_protocol": (
                "completion-v2"
                if self._exchange_recorder is not None
                else "completion-v1"
            ),
        }
        await self.chat._send_action(action)


def title_task_done(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        warnings.warn(f"Background retitle failed: {exc}", stacklevel=1)


async def do_bookmark_with_cleanup(
    bookmark: Any, on_bookmarked: Callable[[str], Awaitable[None]]
) -> None:
    cancel = bookmark.on_bookmarked(on_bookmarked)
    try:
        await bookmark.do_bookmark()
    finally:
        cancel()


class ChatHistory:
    """Namespace for chat history configuration and lifecycle on a `Chat` instance."""

    def __init__(
        self, chat: "Chat", config: HistoryOptions | None = None
    ) -> None:
        self._chat = chat
        self._started: bool = False
        self._controller: HistoryController | None = None
        self._save_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        self._restore_callbacks: "list[Callable[[dict[str, Any]], None]]" = []
        # Session-level registrations made by `_start()`, tracked so they can
        # be released when the owning Chat is destroyed (e.g. same-id
        # reconstruction) instead of leaking until session end.
        self._effects: "list[Effect_]" = []
        self._session_end_cancel: "Callable[[], None] | None" = None
        self._on_session_end: "Callable[[], None] | None" = None
        cfg = config if config is not None else HistoryOptions()
        self._store: "ConversationStore | Literal['auto', 'memory', 'file']" = (
            cfg.store
        )
        self._scope: "str | Callable[..., str] | None" = cfg.scope
        self._title: "TitleFn | Literal['auto'] | None" = cfg.title
        self._restore_mode: "Literal['browser', 'url', 'none', 'bookmark']" = (
            cfg.restore_mode
        )
        self._max_store_mb: float | None = cfg.max_store_mb
        self._restore_bootstrap: "Literal['recorded', 'live']" = (
            cfg.restore_bootstrap
        )
        # This is the initial history effect's existing completion fact. V2
        # admission reads it synchronously at its three entry points.
        self._initial_history_initialized = False

    def enable(self) -> None:
        """Enable chat history for the current session. No-op if already started."""
        if not self._started:
            self._start()

    def _teardown(self) -> None:
        """
        Release session-level registrations when the owning `Chat` is destroyed
        or replaced by a same-id reconstruction.

        Destroys the history input effects — which otherwise keep answering the
        shared input ids and retain the old controller for the rest of the
        session — unregisters the session-end callback, and runs the cleanup
        that session end would have run. No-op if history never started; safe
        to call more than once.
        """
        for effect in self._effects:
            effect.destroy()
        self._effects.clear()
        cancel = self._session_end_cancel
        self._session_end_cancel = None
        if cancel is not None:
            cancel()
        on_end = self._on_session_end
        if on_end is not None:
            on_end()
        self._on_session_end = None

    def conversation_id(self) -> str | None:
        """
        Reactive read of the active conversation ID.

        Returns ``None`` when history is disabled (or hasn't started for this
        session) or the active conversation is an empty draft; otherwise the
        ID allocated at the first user submission, which the saved
        conversation record carries. The ID is stable across client swaps
        (``chat.client.set()``) and is retained when a response fails or is
        cancelled, so a retry keeps the same identity.

        Like any reactive read, this must be called inside a reactive context
        (e.g. a ``@reactive.effect`` or ``@render.*`` function); non-reactive
        callers must wrap it in ``shiny.reactive.isolate()``.
        """
        controller = self._controller
        if controller is None:
            return None
        return controller.conversation_id()

    async def save(self) -> bool:
        """
        Persist the active conversation and its app state.

        Returns ``False`` before history has started or when there is no saved
        active conversation. Storage and bookmark errors propagate to the caller.
        """
        controller = self._controller
        if controller is None:
            return False
        return await controller.save()

    def on_save(
        self, fn: "Callable[[dict[str, Any]], None]"
    ) -> "Callable[[dict[str, Any]], None]":
        """
        Decorator. Register a callback fired whenever the active conversation is saved.

        The callback receives a mutable ``values`` dict; write any per-conversation
        app state you want to persist into it. Fires on each LLM response (to
        capture fresh state) and when the user switches to a different conversation::

            @chat.history.on_save
            def _(values):
                values["selected_tab"] = current_tab()

        Multiple callbacks can be registered and run in registration order.
        Safe to call before ``enabled = True``.
        """
        self._save_callbacks.append(fn)
        return fn

    def on_restore(
        self, fn: "Callable[[dict[str, Any]], None]"
    ) -> "Callable[[dict[str, Any]], None]":
        """
        Decorator. Register a callback fired when a conversation is loaded.

        Fires on page-load restores in every ``restore_mode``, including
        ``"bookmark"``, and on in-session conversation switches. The target
        conversation is active before callbacks run. Use it to sync auxiliary
        UI state — active tabs, model selectors, etc. — to match the restored
        conversation. Raw Shiny input values are not synced automatically;
        call the appropriate ``ui.update_*()`` functions here.

        The callback receives the ``values`` dict that was captured by the
        corresponding ``on_save`` callback::

            @chat.history.on_restore
            def _(values):
                ui.update_navs("tabs", selected=values.get("selected_tab"))

        Multiple callbacks can be registered and run in registration order.
        Safe to call before ``enabled = True``.

        """
        self._restore_callbacks.append(fn)
        return fn

    def setup_greeting(
        self,
        greeting: "str | HTML | Tag | TagList | ChatGreeting | Callable[..., Any]",
    ) -> None:
        """
        Wire `greeting` resolution to fire once history's restore decision is
        settled (at startup, and again on every `new_chat()`), instead of
        racing the client's independent `{id}_greeting_requested` request.

        Only call this when `self._controller is not None` (i.e. history has
        actually started for this session).
        """
        from ._chat_client import resolve_greeting

        chat = self._chat
        controller = self._controller
        assert controller is not None

        async def _on_settled(restored: bool) -> None:
            if not restored:
                await resolve_greeting(chat, greeting)

        controller.on_settled = _on_settled

    def _start(self) -> None:
        chat = self._chat
        chat_client = chat.client
        if chat_client is None:
            raise ValueError(
                "Chat history requires a client. Pass one to Chat(client=...)."
            )

        from shiny import reactive, req
        from shiny.session import get_current_session, session_context

        session = get_current_session()
        if session is None or session.is_stub_session():
            return

        root_session = session.root_scope()
        restore_mode = self._restore_mode

        ids = HistoryInputIds.for_chat(chat.id)
        root_session.bookmark.exclude.extend(ids.all_ids())

        adapter = as_turns_adapter(chat_client)
        resolved_store = resolve_store(self._store)
        title = self._title
        scope_key = self._scope
        max_store_bytes = (
            int(self._max_store_mb * 1024 * 1024)
            if self._max_store_mb is not None
            else None
        )
        controller = HistoryController(
            chat=chat,
            adapter=adapter,
            store=resolved_store,
            title_fn=title if callable(title) else None,
            title_enabled=title is not None,
            client=chat_client,
            save_callbacks=self._save_callbacks,
            restore_callbacks=self._restore_callbacks,
            max_store_bytes=max_store_bytes,
            use_exchange_tree=_EXCHANGE_TREE_HISTORY_V2,
            restore_bootstrap=self._restore_bootstrap,
        )
        self._controller = controller

        if controller._exchange_recorder is not None:
            chat._transcript.set_capture_callbacks(
                on_accepted_input=controller._exchange_recorder.accepted_input,
                on_message_committed=controller._exchange_recorder.message_committed,
                on_stream_started=controller._exchange_recorder.stream_started,
                on_stream_updated=controller._exchange_recorder.stream_updated,
                on_stream_finished=controller._exchange_recorder.stream_finished,
            )

        if restore_mode == "url":

            async def _update_url(conv_id: str | None) -> None:
                url = (
                    f"?shinychat_conversation_id={conv_id}"
                    if conv_id is not None
                    else None
                )
                await controller.send_navigate(url, conv_id)

            controller.on_active_id_change = _update_url

        if restore_mode == "bookmark":
            if root_session.bookmark.store != "server":
                raise ValueError(
                    "restore_mode='bookmark' requires bookmark_store='server' in the Shiny app."
                )

            async def _on_response_saved(record: ConversationRecord) -> None:
                recorder = controller._exchange_recorder
                if recorder is not None:
                    pointer = await recorder.bookmark_pointer(
                        cast(ConversationRecordV2, record)
                    )
                    if pointer is None:
                        return
                    conversation_id, node_id = pointer

                    async def _on_bookmarked(url: str) -> None:
                        new_state_id = extract_state_id(url)
                        if new_state_id is None:
                            return
                        try:
                            current, cleanup_state_id = (
                                await recorder.settle_bookmark_state_id(
                                    conversation_id, node_id, new_state_id
                                )
                            )
                        except BaseException:
                            await delete_bookmark_state(new_state_id)
                            raise
                        if cleanup_state_id is not None:
                            await delete_bookmark_state(cleanup_state_id)
                        if current:
                            await controller.send_navigate(
                                f"?_state_id_={new_state_id}", conversation_id
                            )

                    await do_bookmark_with_cleanup(
                        root_session.bookmark, _on_bookmarked
                    )
                    return

                captured_id = record.id

                async def _on_bookmarked(url: str) -> None:
                    new_state_id = extract_state_id(url)
                    if new_state_id is None:
                        return
                    if (
                        controller.record is None
                        or controller.record.id != captured_id
                    ):
                        return  # switched away
                    old_state_id = record.bookmark_state_id
                    record.bookmark_state_id = new_state_id
                    if old_state_id is not None:
                        await delete_bookmark_state(old_state_id)
                    if controller.partition is not None:
                        await controller._put_record(
                            controller.partition, record
                        )
                    await controller.send_navigate(
                        f"?_state_id_={new_state_id}", captured_id
                    )

                await do_bookmark_with_cleanup(
                    root_session.bookmark, _on_bookmarked
                )

            controller.on_response_saved = _on_response_saved

            async def _on_pre_switch(target: ConversationRecord) -> bool:
                if target.bookmark_state_id is not None:
                    await controller.send_navigate(
                        f"?_state_id_={target.bookmark_state_id}",
                        target.id,
                        reload=True,
                    )
                    return True
                return False

            controller.on_pre_switch = _on_pre_switch

            async def _on_evict(conv_id: str) -> None:
                if (
                    controller.record is not None
                    and controller.record.id == conv_id
                ):
                    state_id = controller.record.bookmark_state_id
                else:
                    if controller.partition is None:
                        rec = None
                    else:
                        rec = await controller._get_record(
                            controller.partition, conv_id
                        )
                    state_id = (
                        rec.bookmark_state_id if rec is not None else None
                    )
                if state_id is not None:
                    await delete_bookmark_state(state_id)

            controller.on_evict = _on_evict

            async def _update_url_bookmark(conv_id: str | None) -> None:
                if conv_id is None:
                    await controller.send_navigate(None, None, reload=True)

            controller.on_active_id_change = _update_url_bookmark

        # Stamp the active history pointer into any Shiny server bookmark.
        # V2 records need the selected leaf as well as the conversation ID;
        # v1 keeps its existing conversation-only value.
        stamp_key = (
            f"{chat.id}_history_exchange_pointer"
            if controller._exchange_recorder is not None
            else f"{chat.id}_history_conversation_id"
        )
        stamp_cancel: Callable[[], None] | None = None
        if root_session.bookmark.store == "server":

            recorder = controller._exchange_recorder
            if recorder is not None:

                async def stamp_exchange_pointer(state: Any) -> None:
                    pointer = await recorder.bookmark_pointer()
                    if pointer is None:
                        return
                    conversation_id, node_id = pointer
                    state.values[stamp_key] = {
                        "conversation_id": conversation_id,
                        "node_id": node_id,
                    }

                stamp_callback = stamp_exchange_pointer
            else:

                def stamp_conversation_id(state: Any) -> None:
                    if controller.record is not None:
                        state.values[stamp_key] = controller.record.id

                stamp_callback = stamp_conversation_id

            stamp_cancel = root_session.bookmark.on_bookmark(stamp_callback)

        @reactive.calc
        def scope() -> str:
            # For restore_mode "browser"/"url", the active conversation id
            # arrives from the client only after Shiny's first reactive flush
            # (dispatched inside initializedPromise.then(), same microtask as
            # browser_token). If scope resolved immediately (session.user or
            # a caller scope_key), the init effect would run on that first
            # flush and read current_id/url_id as None permanently.
            # Requiring browser_token here — even when unused for the
            # returned value — forces scope() to wait for the second flush,
            # by which point all three inputs have arrived.
            # Temporary: some session types raise AttributeError on .user;
            # remove this getattr once the pending py-shiny PR lands.
            user = getattr(chat._session, "user", None)
            if restore_mode in ("browser", "url") and (
                scope_key is not None or user is not None
            ):
                token = chat._session.input[ids.browser_token]()
                req(token)
            if isinstance(scope_key, str):
                return scope_key
            if callable(scope_key):
                return scope_key(chat._session)
            if user is not None:
                # session.user is expected to be a stable, per-identity
                # string by Shiny convention; two users whose str(user)
                # values collide would share a history scope.
                return str(user)
            token = chat._session.input[ids.browser_token]()
            return str(req(token))

        async def notify_error(prefix: str, e: Exception) -> None:
            import warnings

            from shiny import ui as shiny_ui

            warnings.warn(f"{prefix}: {e}", stacklevel=1)
            with session_context(session):
                shiny_ui.notification_show(f"{prefix}: {e}", type="error")

        async def finish_initial(restored: bool) -> None:
            # Every initial path sends its authoritative history_update before
            # calling this helper.
            self._initial_history_initialized = True
            await controller.notify_settled(restored)

        @reactive.effect(
            priority=10_000 if controller._exchange_recorder is not None else 0
        )
        async def _init_history():
            if self._initial_history_initialized:
                return

            async def restore_initial_v2(
                target: ConversationRecordV2,
                *,
                node_id: str | None = None,
            ) -> None:
                try:
                    await controller._restore_initial_exchange_record(
                        target, node_id=node_id
                    )
                except BaseException:
                    try:
                        await controller.notify_settled(False)
                    except BaseException:
                        # Settlement is advisory; preserve the restore error.
                        pass
                    raise

            owner_scope = scope()  # req() retries until token arrives
            controller.partition = ConversationPartition(
                chat_id=str(chat.id), scope=owner_scope
            )

            # Priority 1: restore from a Shiny bookmark context (any mode).
            restore_ctx = root_session.bookmark._restore_context
            restored_conv_id: str | None = None
            bookmark_pointer: tuple[str, str] | None = None
            bookmark_pointer_invalid = False
            if restore_ctx is not None and restore_ctx.active:
                raw_pointer = restore_ctx.values.get(stamp_key)
                if controller._exchange_recorder is not None:
                    if raw_pointer is not None:
                        if (
                            isinstance(raw_pointer, dict)
                            and set(raw_pointer) == {"conversation_id", "node_id"}
                            and isinstance(raw_pointer["conversation_id"], str)
                            and raw_pointer["conversation_id"]
                            and isinstance(raw_pointer["node_id"], str)
                            and raw_pointer["node_id"]
                        ):
                            bookmark_pointer = (
                                raw_pointer["conversation_id"],
                                raw_pointer["node_id"],
                            )
                        else:
                            bookmark_pointer_invalid = True
                else:
                    restored_conv_id = str(raw_pointer) if raw_pointer else None

            if bookmark_pointer_invalid:
                await notify_error(
                    "Could not load conversation",
                    ValueError("Bookmark pointer is invalid."),
                )
                await controller.send_history_update()
                await finish_initial(False)
                return

            if bookmark_pointer is not None:
                conversation_id, node_id = bookmark_pointer
                try:
                    target = await controller._get_record(
                        controller.partition, conversation_id
                    )
                    if not isinstance(target, ConversationRecordV2):
                        raise ValueError("Bookmark conversation is unavailable.")
                    if node_id not in target.nodes:
                        raise ValueError("Bookmark node is unavailable.")
                except Exception as e:
                    await notify_error("Could not load conversation", e)
                    await controller.send_history_update()
                    await finish_initial(False)
                    return

                await restore_initial_v2(target, node_id=node_id)
                await finish_initial(True)
                return

            if restored_conv_id is not None:
                try:
                    target = await controller._get_record(
                        controller.partition, restored_conv_id
                    )
                except Exception as e:
                    await notify_error("Could not load conversation", e)
                    target = None
                if target is not None:
                    if isinstance(target, ConversationRecordV2):
                        await restore_initial_v2(target)
                    else:
                        async with controller._destructive_mutation():
                            adapter.set_turns_json(target.path_turns())
                            await controller.replay_ui(target)
                            await controller.activate_record(target)
                            controller._restore_app_state(target.values or {})
                            await controller._send_sibling_metadata()
                            await controller.send_history_update()
                    await finish_initial(True)
                    return

            # Priority 2: restore from the mode-specific ID source.
            # Reading these inputs may raise SilentException if the browser
            # hasn't sent them yet (they're delivered after Shiny's
            # initializedPromise resolves, which is after the first flush).
            # Keep the initial readiness false until after send_history_update()
            # so the effect retries correctly on the next flush rather than
            # exiting early via the guard above.
            if restore_mode == "url":
                raw = chat._session.input[ids.url_id]()
                current_id: str | None = str(raw) if raw else None
            elif restore_mode == "browser":
                raw = chat._session.input[ids.current_id]()
                current_id = str(raw) if raw else None
            else:
                current_id = None

            if current_id:
                try:
                    pointed = await controller._get_record(
                        controller.partition, current_id
                    )
                except Exception as e:
                    await notify_error("Could not load conversation", e)
                    pointed = None
                if pointed is not None:
                    if isinstance(pointed, ConversationRecordV2):
                        await restore_initial_v2(pointed)
                        await finish_initial(True)
                        return
                    else:
                        async with controller._destructive_mutation():
                            adapter.set_turns_json(pointed.path_turns())
                            await controller.replay_ui(pointed)
                            await controller.activate_record(pointed)
                            controller._restore_app_state(pointed.values or {})
                            await controller._send_sibling_metadata()
            await controller.send_history_update()
            await finish_initial(
                controller._active_id_now() is not None
            )

        async def _save_on_response():
            if controller.partition is None:
                return
            try:
                await controller.on_response()
            except Exception as e:
                await notify_error("Could not save conversation", e)

        cancel_response_settlement = chat._on_response_settled(
            _save_on_response
        )

        @reactive.effect
        @reactive.event(chat._session.input[ids.select])
        async def _on_select():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.select]()
            try:
                await controller.switch_to(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not open conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.new])
        async def _on_new():
            request_id = _history_transition_request_id(
                chat._session.input[ids.new]()
            )
            try:
                if controller.partition is None:
                    return
                await controller.new_chat()
            except Exception as e:
                await notify_error("Could not start a new chat", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.rename])
        async def _on_rename():
            if controller.partition is None:
                return
            payload = chat._session.input[ids.rename]()
            try:
                await controller.rename(
                    str(payload["id"]), str(payload["title"])
                )
            except Exception as e:
                await notify_error("Could not rename conversation", e)

        @reactive.effect
        @reactive.event(chat._session.input[ids.delete])
        async def _on_delete():
            payload = chat._session.input[ids.delete]()
            request_id = _history_transition_request_id(payload)
            try:
                if controller.partition is None:
                    return
                await controller.delete(str(payload["id"]))
            except Exception as e:
                await notify_error("Could not delete conversation", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_edit])
        async def _on_edit():
            payload = chat._session.input[ids.message_edit]()
            request_id = _history_transition_request_id(payload)
            try:
                if controller.partition is None:
                    return
                if not isinstance(payload, dict):
                    raise TypeError("Edited message payload must be an object.")
                index = payload.get("index")
                content = payload.get("content")
                if not isinstance(index, int):
                    raise TypeError("Edited message index must be an integer.")
                if not isinstance(content, str):
                    raise TypeError("Edited message content must be a string.")
                await controller.handle_edit(
                    index,
                    content,
                    payload.get("attachments"),
                    request_id=request_id,
                )
            except Exception as e:
                await notify_error("Could not edit message", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_navigate])
        async def _on_navigate():
            payload = chat._session.input[ids.message_navigate]()
            request_id = _history_transition_request_id(payload)
            try:
                if controller.partition is None:
                    return
                if not isinstance(payload, dict):
                    raise TypeError("Navigation payload must be an object.")
                index = payload.get("index")
                direction = payload.get("direction")
                if not isinstance(index, int):
                    raise TypeError("Navigation index must be an integer.")
                if not isinstance(direction, str):
                    raise TypeError("Navigation direction must be a string.")
                await controller.handle_navigate(
                    index,
                    direction,
                    request_id=request_id,
                )
            except Exception as e:
                await notify_error("Could not navigate messages", e)
            finally:
                if (
                    request_id is not None
                    and controller._exchange_recorder is not None
                ):
                    await _complete_history_transition(chat, request_id)

        @reactive.effect
        @reactive.event(chat._session.input[ids.message_resubmit])
        async def _on_resubmit():
            payload = chat._session.input[ids.message_resubmit]()
            request_id = _history_transition_request_id(payload)
            try:
                if controller.partition is None:
                    return
                if not isinstance(payload, dict):
                    raise TypeError("Resubmit payload must be an object.")
                index = payload.get("index")
                kind = payload.get("kind")
                if not isinstance(index, int):
                    raise TypeError("Resubmit message index must be an integer.")
                if not isinstance(kind, str):
                    raise TypeError("Resubmit kind must be a string.")
                await controller.handle_resubmit(
                    index, kind, request_id=request_id
                )
            except Exception as e:
                await notify_error("Could not retry message", e)
            finally:
                if request_id is not None:
                    await _complete_history_transition(chat, request_id)

        def _on_session_end() -> None:
            if self._on_session_end is None:
                return
            # The session consumed the registration by firing it; keep the
            # tracked state truthful so a later `_teardown()` won't re-run.
            self._session_end_cancel = None
            self._on_session_end = None
            if stamp_cancel is not None:
                stamp_cancel()
            cancel_response_settlement()
            controller.cancel_pending()

        self._effects.extend(
            [
                _init_history,
                _on_select,
                _on_new,
                _on_rename,
                _on_delete,
                _on_edit,
                _on_navigate,
                _on_resubmit,
            ]
        )
        self._on_session_end = _on_session_end
        self._session_end_cancel = session.on_ended(_on_session_end)
        self._started = True
