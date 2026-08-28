# Phase 3 mechanism: exchange record, capture, and store (Python)

**Status:** agreed 2026-08-28; store layout blocked on Q2 benchmark
**Phase:** plan.md §4, Phase 3
**Kata:** parent `shinychat#qf2r` under epic `shinychat#6d0d`
**Context:** `phase-2-mechanism.md` is closed historical context. This note is
the Phase 3 gate and the only phase-local mechanism reference for new work.

## Objective

Replace Python's response-settlement reconstruction with a persistent tree of
exchanges captured at write time. The first vertical slice is one accepted
input → one exchange node → eager captured output → atomic store write →
minimal display replay through the live message pipeline.

Phase 3 establishes the record, capture, and persistence mechanism. Phase 4
adds complete restore, client-state replay, branching, rewind, retry, and
bookmark pointers. Phase 5 adds the init-window guard, unreplayable-turn
degradation, and the adversarial hard-core audit.

## Entry gate

No feature code starts until all of these are recorded on `shinychat#qf2r`:

1. The Python Playwright suite runs at the Phase 3 branch point.
2. A temporary deliberately broken shared history-behavior fixture fails both
   the Python and R matrix consumers; the repository remains unchanged.
3. History tests contain no vacuous pin, xfail, or unconditional skip.
   Dependency-presence skips are acceptable only when the full gate installs
   the dependency and therefore executes them.
4. Shared store fixtures cover doubles and malformed JSONL lines. Add an
   unreplayable-turn fixture shape now so both languages preserve the value
   class; Phase 5 owns degrade-with-warning behavior and must not be pulled
   forward.
5. Q2's layout benchmark is complete and its result is written into this note
   and plan.md §3.10/§5.

Gate items 1–4 passed on 2026-08-28 in `shinychat#ztvz`:

- the full Python Playwright suite passed (191 tests);
- temporary broken-fixture checks failed at the intended assertion in both
  consumers (Python: 1 failed, 12 passed; R: 1 failed, 30 passed);
- no vacuous history pins remain; dependency-presence skips executed in the
  full environment;
- shared fixtures now cover doubles, malformed JSONL, and opaque
  unreplayable-turn values in both languages (`b36373ba`, review fix
  `deb691a9`).

The Python non-browser suite passed 651 tests with one skip and one unrelated
failure: the known platform-dependent Markdown MIME assertion tracked by
`shinychat#4z6p`. Q2 remains the only incomplete entry-gate item.

## Record schema

Phase 3 writes `schema_version: 2`. It does not overwrite a v1 record. Until
Phase 7 adds the committed v1 import, a v1 record at the v2 read gate fails
visibly as a legacy unsupported record.

The v2 path stays behind one private, default-off feature flag through
Phases 3–6. With the flag off, the released v1 path remains unchanged. With
the flag on, a session writes only v2 and never dual-writes or mutates v1.
Phase 7 adds the v1 import, removes the flag and old reconstruction path, and
makes v2 the default. This keeps every intermediate phase mergeable without
creating two authorities for one conversation.

`ConversationRecord` keeps the existing conversation metadata and tree
operations, with these v2 fields:

```python
class ConversationRecord(BaseModel):
    schema_version: Literal[2] = 2
    id: str
    title: str
    title_source: Literal["llm", "user"] | None
    response_count: int
    created_at: datetime
    updated_at: datetime
    client_info: dict[str, str]
    nodes: dict[str, ExchangeNode]
    next_node_seq: int
    active_leaf: str | None
    values: dict[str, Any]
    bookmark_state_id: str | None

class ExchangeNode(BaseModel):
    parent_id: str | None
    children: list[str]
    selected_child: str | None
    created_at: datetime
    status: Literal["pending", "ok", "error", "cancelled"]
    input: StoredMessage | None
    messages: list[CapturedMessage]
    state: dict[str, StateEntry]
    error: ErrorEntry | None

class CapturedMessage(BaseModel):
    role: Literal["user", "assistant"]
    segments: list[StoredSegment]
    icon: str | None
    attachments: list[Attachment] | None

class StateEntry(BaseModel):
    kind: str
    version: int
    mode: Literal["delta", "snapshot"]
    data: JsonValue

class ErrorEntry(BaseModel):
    message: str
```

The node id is the key in `nodes`; it is not duplicated inside the node.
`active_leaf` replaces v1's `current_leaf`. `input` owns the accepted user
submission, including attachments. `messages` owns only content the server
successfully emitted after that input; restore renders `input` first, then
`messages`. This resolves the worked example's intentionally non-schema shape
without duplicating user content.

The generic `state` map is present from the first v2 fixture. `messages` never
becomes a state entry. Extra error fields require a later requirement and
schema decision; Phase 3 stores the stable message only.

## Ownership and event flow

Keep two owners with non-overlapping responsibilities:

- `ChatTranscript` remains the in-memory owner of accepted and successfully
  emitted display messages, send transactions, stream assembly, and stream
  attribution.
- One new private `_ExchangeRecorder`, owned by `HistoryController`, owns the
  active v2 record, capture baselines, internal state hooks, and store writes.

Do not add a second transcript, settlement revision, response queue, cursor,
or reconciliation pass. The top-level Phase 3 addition is one recorder; the
schema models and hook callables are data contracts, not lifecycle owners.

The Phase 2 transcript transaction emits awaited post-commit events:

```python
accepted_input(exchange_id, message)
message_committed(exchange_id, message, icon)
stream_started(stream_id, exchange_id, message, icon)
stream_updated(stream_id, message, icon)
stream_finished(stream_id, status, error)
```

These events are the post-send side of the existing `_send_action` choke
point: a failed transport send emits no event, and the event carries the
assembled, server-authored `StoredMessage`, not raw rendered HTML. The private
`stream_id → exchange_id` association remains in memory only. A stream update
replaces its one captured message spec atomically; it does not append raw
chunks or add a persistent message id.

The callbacks are awaited before the originating mutation returns. A store
failure therefore fails openly instead of reporting durable success. The
already-committed transcript remains truthful about content that reached the
browser; retrying persistence writes the current node projection
idempotently. Do not roll back browser-visible content or transcript state.

Bookkeeping and ambient actions emit no capture event. In particular,
`history_*`, drawer, slash-command synchronization, `update_cancel`,
loading, and every `greeting_*` action remain excluded. An echoed slash
command still uses `accepted_input` and therefore opens an exchange.

## Node lifecycle and status

The implicit root is created with the conversation record. It has no input,
starts `pending`, and receives pre-input complete/streamed content. A
successful complete append can mark it `ok`; an active stream keeps it
`pending` until that stream terminates.

- **First accepted input:** capture root state as a snapshot, leave an active
  root stream `pending`, otherwise mark the root `ok`, then create a pending
  child with that input. A later root-stream terminal event still writes to
  the root by explicit exchange id.
- **Later accepted input:** run catch-up state capture on the current node,
  leave its existing terminal status unchanged, then create a pending child.
  A node with no terminal response remains `pending` and reloads as
  interrupted.
- **Content without an open exchange:** create an input-less pending child at
  the active leaf before recording the content.
- **Successful complete assistant append:** mark its owning node `ok` and
  persist the message. It does not trigger state capture; synchronous turn
  mutations are recorded by the node-close catch-up.
- **Stream start/update:** retain `pending` and persist the assembled message
  after every successful send.
- **Stream finish:** capture state verbatim, set `ok`, `error`, or
  `cancelled`, set `error` only for `error`, and persist.
- **Lazy close:** edit, navigate, switch, and new-chat hooks call the same
  catch-up capture before their Phase 4 mutations. In Phase 3 only the next
  accepted input exercises this close path.

An older stream always writes to its captured exchange after newer input
opens another node. Status and state capture take an explicit exchange id;
they never consult only the mutable active leaf.

There is no exchange-settled event. The Phase 2 response-settlement pump may
remain temporarily for legacy bookmark/history consumers, but v2 record
durability does not depend on it. The default-off flag selects either the v1
bridge or v2 recorder for a session, never both; Phase 7 deletes the bridge.

## State capture

The internal registry is keyed by state-entry name:

```python
CaptureReason = Literal["root_close", "stream_finish", "node_close"]
CaptureHook = Callable[
    [CaptureContext],
    Awaitable[StateEntry | None] | StateEntry | None,
]
```

Returning an entry upserts that key; returning `None` removes it. Hooks run in
registration order and receive the explicit node id and reason. Capture is
internal in Phase 3; the public registration API remains deferred. Phase 4
adds and executes the parallel restore/rewind hook contracts.

The blessed Python hook is registered as `shinychat:turns`:

- `kind: "chatlas"` for chatlas and `kind: "turns"` for the generic
  `ClientWithTurns` adapter;
- `version: 1`;
- root close always writes `mode: "snapshot"`;
- later captures write `mode: "delta"` when the previous serialized baseline
  is still an exact prefix, otherwise `mode: "snapshot"`;
- after either result, the full current serialized sequence becomes the new
  baseline.

The baseline stores per-turn canonical JSON fingerprints plus the serialized
turn count. Prefix comparison checks every baseline fingerprint; checking
only the last turn is insufficient when an earlier turn is rewritten. This
is measured with the store benchmark before adding caching.

For chatlas, root capture calls `get_turns(include_system_prompt=True)` so the
system prompt is included. Later captures use the same sequence, which keeps
delta arithmetic stable. Generic clients receive whatever their `get_turns()`
contract exposes; shinychat does not invent unavailable system state.
Errored and cancelled streams capture the client exactly as it exists.

## Persistence and Q2 benchmark

`ConversationStore` retains `list`, `get`, `put`, and `delete`; custom stores
continue to receive a complete logical `ConversationRecord`. The file-store
layout is the only open mechanism decision.

Benchmark both candidates using the same deterministic v2 record:

- at least 140k tokens of message/state content;
- multiple content segments and tool-call turns per exchange;
- at least 200 exchanges and five forks;
- hot writes for accepted input, 100 stream updates, terminal state capture,
  and a pointer-only tree update;
- cold full-record read and process-restart write;
- median and p95 wall time plus bytes written, measured on the same local
  filesystem with at least 20 repetitions after warm-up.

Candidates:

1. **Single document:** serialize to a temporary file and `os.replace()` the
   whole record.
2. **Split:** atomically replace the tree/metadata document; append immutable
   message/state revisions and resolve latest revisions on read. Failure
   injection must prove that a killed or failed write exposes either the old
   coherent record or the new coherent record. Orphans are allowed and never
   swept.

Selection rule: choose single-document unless split improves median hot-write
latency by at least 2× **and** p95 by at least 1.5× without worsening cold read
by more than 2×. This deliberately charges the split layout for its additional
write-state, rollback, and recovery machinery. Record raw results, environment,
and the selected layout here, then update plan.md Q2. Delete the losing
prototype before feature code.

**Q2 result:** pending.

## Keystone and stacked work

After the gate and Q2 sign-off, create stacked child issues in this order:

1. **Gate + benchmark.** Verify instruments, add the unreplayable-turn fixture
   shape, benchmark both layouts, decide Q2, and delete the losing prototype.
   This is documentation/test-instrument work, not feature hardening.
2. **Keystone v2 slice.** Land the v2 schema and one flag-guarded production
   path for accepted input, one complete assistant message, atomic persistence,
   and minimal active-path display replay through `_restore_bookmark_message`.
3. **Streaming durability + attribution.** Persist stream start/update/finish,
   partial error/cancellation, old-stream attribution, and process-kill
   recovery.
4. **State hooks + baseline.** Add the internal registry, root snapshot,
   chatlas system prompt, delta capture, snapshot fallback, and node-close
   catch-up.
5. **Phase 3 acceptance.** Round-trip the worked example, run failure
   injection and kill/reload coverage, prove the default-off flag does not
   dual-write, complete the deletion pass, and collect review evidence.

Each schema or store-format change is a single-session atom. Review coherent
units, not individual commits. Human review is required before closing any
child or the phase.

## Verification

- Focused unit tests for schema graph operations, capture events, each status,
  root/input-less nodes, delta/snapshot fallback, and store failure injection.
- Production-path integration tests for complete and streaming capture; no
  test-only persistence bypass.
- Process-kill tests after accepted input, stream start, each stream update,
  and terminal status.
- Worked-example v2 fixture round-trips through memory and file stores.
- `make py-check-format`, `make py-check-types`, focused
  `make py-check-tests FILTER=...`, then the applicable full Python gate.
- No JS/SCSS or R packaged-asset change in Phase 3.

## Initial handoff

- **Landed:** Phase 2 is closed; Phase 3 parent `shinychat#qf2r` is claimed;
  the driver approved this mechanism on 2026-08-28; gate items 1–4 passed in
  `shinychat#ztvz`.
- **Next:** execute the Q2 benchmark, record the layout decision, then create
  the remaining stacked child issues.
- **Provisional:** only the file-store layout remains provisional. No feature
  code starts until Q2 is recorded here and in the durable plan.
