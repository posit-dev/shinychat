# Phase 3 mechanism: exchange record, capture, and store (Python)

**Status:** agreed 2026-08-28; Q2 selects single-document atomic layout after
split rejection
**Phase:** plan.md §4, Phase 3
**Kata:** parent `shinychat#qf2r` under epic `shinychat#6d0d`
**Review base:** `175d9acffc0f7e31e65fbeb3c3ba079f20f00972`
(`docs: close Phase 2 mechanism`). Review all Phase 3 work as
`175d9acffc0f7e31e65fbeb3c3ba079f20f00972..HEAD`.
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
   and plan.md §3.10/§5. Passed on 2026-08-28; result below.

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
`shinychat#4z6p`. Q2 was the only incomplete entry-gate item.

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
continue to receive a complete logical `ConversationRecord`. Q2 resolves the
file-store layout below as single-document atomic replacement.

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
by more than 2× **and** proves coherent old-or-new visibility for killed or
failed writes, including interrupted immutable-revision writes. This
correctness prerequisite is mandatory; latency cannot select a candidate that
fails it or requires unbenchmarked tail-repair/recovery machinery. Record raw
results, environment, and the selected layout here, then update plan.md Q2.
Delete all disposable benchmark prototypes before feature code.

### Q2 result (2026-08-28): select single-document; reject split

The disposable benchmark used one deterministic v2 logical record with 206
nodes: the implicit root, 200 mainline exchanges, and five fork siblings.
Each exchange has a multi-segment assistant message and a four-turn
user/tool-call/tool-result/assistant state entry. The generated
message/state content totals 153,348 whitespace-delimited tokens
(`3,863,027` bytes as the single JSON document).

The single prototype serialized the whole record to a temporary file and
used `os.replace()`. The split prototype atomically replaced a tree/metadata
document, appended immutable message/state revisions, and had the tree
reference the revisions to resolve on read. A revision written before a tree
replacement but never referenced is an allowed orphan. Both prototypes were
deleted after this result was recorded; no production store code was added.

Measurements used `time.perf_counter_ns()` around only the stated operation,
after three warm-ups and across 25 sequential repetitions on the same local
filesystem. p95 is the nearest-rank 95th percentile. The cold read creates a
fresh store object and fully reconstructs the record without an application
cache; macOS filesystem cache remains outside the benchmark's control.
`hyperfine 1.20.0` separately cross-checked the 100-stream-update command
with the same three warm-ups and 25 runs: 835.2 ms mean for single and 315.4
ms mean for split (2.65x faster for split, including process setup).

| Operation | Single median / p95 (ms) | Split median / p95 (ms) | Bytes written (single / split) |
|---|---:|---:|---:|
| Accepted-input write | 7.151 / 7.853 | 0.948 / 1.088 | 3,863,772 / 186,218 |
| 100 stream-update writes | 723.305 / 750.249 | 103.388 / 299.660 | 386,273,900 / 19,425,784 |
| Terminal state capture | 7.200 / 7.681 | 1.043 / 1.395 | 3,864,052 / 195,425 |
| Pointer-only tree update | 7.195 / 8.289 | 0.910 / 1.218 | 3,863,042 / 185,466 |
| Cold full-record read | 3.861 / 4.954 | 5.315 / 6.412 | n/a |
| Process-restart pointer write | 69.541 / 88.842 | 67.956 / 129.266 | 3,863,042 / 185,466 |

Raw measured samples in milliseconds, in run order:

```text
single accepted-input: 7.186, 6.913, 6.967, 7.092, 6.963, 7.226, 7.405, 7.413, 7.292, 7.151, 7.127, 6.995, 7.044, 6.839, 7.133, 7.006, 7.209, 7.196, 7.176, 7.371, 7.063, 7.853, 7.212, 7.068, 7.930
split accepted-input: 0.917, 1.011, 0.917, 0.985, 0.910, 0.933, 1.088, 1.023, 1.065, 1.102, 0.903, 0.948, 0.959, 1.040, 0.943, 0.944, 0.989, 0.915, 0.946, 0.933, 0.922, 0.955, 1.085, 0.937, 0.948
single 100 stream updates: 714.188, 724.149, 719.005, 721.495, 713.765, 711.784, 715.800, 721.510, 750.249, 715.394, 732.219, 723.193, 723.305, 716.873, 728.164, 727.319, 726.167, 724.237, 761.695, 729.836, 732.705, 719.967, 717.903, 732.315, 729.416
split 100 stream updates: 107.228, 107.363, 103.860, 102.225, 107.248, 299.660, 104.123, 99.381, 99.746, 102.162, 228.319, 99.295, 99.203, 119.877, 100.116, 98.939, 317.416, 103.388, 102.050, 107.139, 100.427, 278.090, 105.535, 99.128, 101.353
single terminal capture: 6.848, 7.025, 7.389, 8.626, 7.200, 7.307, 7.341, 7.254, 7.184, 7.084, 6.961, 6.781, 7.052, 7.278, 7.331, 6.714, 7.681, 7.406, 7.128, 7.142, 7.446, 6.802, 7.162, 7.359, 7.296
split terminal capture: 1.283, 1.026, 1.062, 1.067, 1.018, 1.033, 1.395, 1.033, 1.010, 1.043, 1.040, 1.060, 1.270, 1.020, 1.215, 1.000, 1.079, 1.200, 1.040, 1.016, 1.018, 1.008, 1.132, 1.491, 1.177
single pointer update: 7.155, 6.930, 7.140, 7.199, 7.326, 7.081, 7.291, 6.961, 7.049, 6.963, 7.086, 6.964, 6.940, 7.119, 7.952, 7.322, 8.037, 7.456, 7.719, 8.289, 9.626, 7.258, 7.417, 7.150, 7.195
split pointer update: 0.911, 0.936, 0.932, 0.884, 0.895, 0.910, 0.894, 0.896, 1.008, 0.887, 0.892, 1.218, 0.987, 0.889, 0.978, 1.045, 0.891, 1.167, 0.882, 0.920, 1.278, 0.902, 0.901, 0.892, 0.948
single cold read: 3.362, 3.603, 4.107, 3.456, 3.749, 4.048, 3.884, 4.028, 4.292, 3.336, 4.087, 5.605, 3.353, 3.595, 4.092, 3.909, 3.685, 4.088, 3.454, 4.954, 3.739, 3.456, 3.568, 3.944, 3.861
split cold read: 6.140, 5.100, 6.412, 5.082, 5.247, 5.600, 5.260, 5.073, 5.249, 5.490, 5.437, 4.798, 5.640, 5.095, 5.543, 4.846, 5.328, 5.241, 5.315, 4.877, 5.525, 4.976, 5.615, 5.458, 6.539
single restart write: 59.155, 57.391, 74.233, 69.541, 78.252, 71.863, 59.861, 82.612, 69.885, 88.842, 62.447, 71.454, 71.538, 64.970, 94.444, 87.140, 77.725, 63.999, 88.157, 57.026, 56.259, 69.320, 57.577, 56.358, 60.851
split restart write: 54.386, 129.266, 73.926, 69.447, 65.610, 64.280, 66.784, 68.908, 67.469, 71.139, 62.734, 67.956, 70.067, 73.579, 68.209, 232.134, 64.021, 69.228, 64.396, 63.896, 63.190, 58.702, 55.127, 68.760, 70.615
```

Environment: macOS 26.5.2 (25F84), Darwin 25.5.0 arm64, Python 3.10.21,
APFS on `/System/Volumes/Data`, 4 KiB filesystem blocks, and 93 GiB free at
measurement time. No benchmark commands ran concurrently.

Failure injection used `SIGKILL` on a child process at each named write stage,
then instantiated a fresh store and reconstructed the complete logical
record. This is process-kill evidence, not a power-loss/fsync claim:

| Candidate and injection point | Visible revision after fresh read |
|---|---|
| Single: injected failure before `os.replace()` | old |
| Single: kill before `os.replace()` | old |
| Single: kill after `os.replace()` | new |
| Split: injected failure after message-revision append | old |
| Split: kill after message-revision append | old |
| Split: kill after state-revision append | old |
| Split: kill after atomic tree replacement | new |

#### Split result and escalation (2026-08-28; roborev jobs 1028 and 1029)

The partial-append check recreated a narrow disposable harness inline with
Python's standard library. Each temporary store started with complete
`old-message` and `old-state` JSONL revisions and an atomic tree document
referencing both. A child process appended only a prefix of one new immutable
revision, flushed the bytes, and was killed with `SIGKILL` before the tree
could be replaced. The fresh reader parsed complete JSONL records, ignored an
incomplete unreferenced tail, and resolved only the revisions referenced by
the tree.

The message payload was 43 bytes and the state payload was 58 bytes. They were
interrupted independently at offsets `1`, midpoint, two bytes before the end,
and one byte before the JSONL newline: messages at `1`, `21`, `41`, `42`;
state at `1`, `29`, `56`, `57`. The last offset is complete JSON without its
record terminator; the other end-near offsets exercise incomplete JSON. These
were eight partial-prefix cases in total, and every case exposed the complete
old logical record. A second check completed the message revision, interrupted
the state revision at offset `56`, and still exposed old message plus old
state; no mixed projection was visible. A control check completed both
revisions and atomically replaced the tree, exposing the complete new logical
record.
The child processes exited from `SIGKILL` as expected. All temporary
directories and the inline harness were removed after the run; no benchmark
or failure harness was retained.

The partial-prefix cases all exposed the old record, but roborev job `1029`
found that appending a later revision after an unterminated tail can
concatenate records and make the newly referenced revision unreadable. This
is the third finding against split persistence. Under the escalation valve,
the orchestrator chose **REPLACE**: no tail-repair or split-recovery
prototype will be built, and split is rejected regardless of its latency.

Review dispositions: job `1028`'s partial-append finding was accepted and
verified by the disposable check above. Its prototype-retention finding was
declined because `shinychat#98jz` requires all disposable benchmark code to be
deleted. Job `1029`'s follow-on recovery finding triggered the 3/3 valve and
the split replacement decision. The rejected split performance evidence and
full raw measured samples remain above; only the executable prototypes and
harnesses were disposable.

Split had the required hot-write latency improvements and a 1.38x cold-read
penalty; the summary table above preserves those rejected performance
measurements.

Single-document therefore wins Q2. Its temporary-file write exposes the old
record before `os.replace()` and the new record after it, without an append
tail or a separate recovery protocol. Both disposable prototypes were
deleted after the measurements; no production store code was added.

## Keystone and stacked work

After the gate and Q2 sign-off, create stacked child issues in this order:

1. **Gate + benchmark (complete).** Instruments and shared fixtures passed in
   `shinychat#ztvz`; Q2 selected the single-document layout in
   `shinychat#98jz` after split failed the recovery prerequisite. Both
   disposable store prototypes are deleted. This was documentation/test-
   instrument work, not feature hardening.
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

## Current handoff

- **Landed:** `shinychat#vdhn` keystone commits `c5e33a62` and `75791d96`
  add the v2 exchange schema, default-off private flag, single-document
  atomic file-store path, awaited accepted-input and complete-message capture,
  and minimal active-path display replay through
  `_restore_bookmark_message`. Flag-on sessions skip the v1 response-
  settlement saver, so they do not dual-write. Streaming persistence, state
  hooks, baseline capture, full restore/bootstrap behavior, and branching
  remain untouched.
- **Next:** roborev review the coherent keystone range
  `c5e33a62..75791d96`, disposition findings under the escalation valve, then
  leave `shinychat#vdhn` open with `needs-review` for the human round.
- **Provisional:** no Phase 3 mechanism decision remains open. The
  single-document atomic temp-file plus `os.replace()` layout remains
  selected; split recovery/tail-repair remains explicitly rejected. The
  keystone’s narrow replay method deliberately does not enter the
  init/restore window; Phase 4 and Phase 5 retain full restore semantics and
  its guard decision.
