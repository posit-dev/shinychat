# Plan: exchange-tree conversation history

**Status:** committed · Phase 0 complete, Phase 1 in review, Phases 2–4
complete; Phase 5 mechanism approved, with Q1 selecting
disabled-until-restore-decision; Q2 selects single-document atomic layout
after split rejection · 2026-09-01
**Kata:** epic `shinychat#6d0d` · Phase 1 `shinychat#g49a` · Phase 2
`shinychat#kjyt` · Phase 3 `shinychat#qf2r` · Phase 4 `shinychat#azvt`
· Phase 5 `shinychat#fg70` (the `kata` CLI issue tracker).
All abbreviated Kata IDs below belong to the `shinychat` project;
planning history in closed issue `kvhc`
**Predecessor:** `feat/turn-history-sync-redesign` (stopped; see the
[retrospective report](../_dev/todos/pending/2026-08-13_client-turns-history-sync/retrospective/report.md))
**Companions:** [rationale.md](rationale.md) — why this design, what was
considered and rejected, and the answers to each team concern ·
[process.md](process.md) — the normative working process for this effort.
**Lifecycle:** `_plan/` is a tracked working directory for this feature
branch. Keep these documents current throughout implementation and remove the
directory in the final cleanup before merging the completed effort to `main`.

---

## 1. The mechanism

> A conversation is a tree of exchanges. An exchange opens when the user
> submits input; everything the server sends to that chat until the next user
> action belongs to it. Each exchange node records two facts, captured at
> write time and never reconciled afterward: **`messages`** — the wire-format
> content specs the server actually sent to the browser (always) — and
> **`state`** — named app-state entries written by registered capture hooks,
> the blessed one being the delta of client turns the exchange produced
> (when an ellmer/chatlas client is attached). Restore replays each fact to
> its own consumer: messages re-render through the standard pipeline; turns
> return to the client via `set_turns`. What the user saw and what the model
> saw are allowed to differ; the node is their correlation.

### Node lifecycle — no settlement event

There is deliberately no "exchange settled" event. The lifecycle is: eager
writes at moments the server already observes, plus a lazy close.

1. **Open** at user input. A content send with no open exchange (a timer, a
   background notice) creates an input-less node at the current leaf. The
   *first* user input additionally closes the implicit **root node**:
   everything that existed before it — pre-input UI appends and the client's
   pre-existing turns (system prompt, app-attached history) — is snapshotted
   into an input-less node at the tree root (§3.4, baseline snapshot).
2. **Write eagerly.** Message specs are appended to the open node at send
   time. State capture (the turn delta) and the node status (`ok` / `error`
   / `cancelled`) are written when an asynchronous `chat_append()` input — a
   stream generator or promise — closes; the trigger is the append closing,
   not any particular task API (today that signal is the `ExtendedTask`
   status in both languages). Synchronous appends need no capture trigger of
   their own: their message write is already eager at send, and turn
   mutations alongside them are recorded by the catch-up capture at node
   close (§3.4). These are bookkeeping writes,
   not lifecycle gates — nothing waits on them, nothing sweeps them.
   Durability requires eagerness here: the most common end-of-conversation
   state is "user reads the answer and closes the tab," and error status
   must be durable at failure time for the retry affordance.
3. **Close lazily** at the next user *action* — input, edit, navigate,
   switch-conversation, or new-chat all return control and close the open
   leaf. Closing does nothing except start the next node.
4. **Attribution rule:** stream chunks are attributed to the stream's own
   node, never "whichever node is open." If input arrives while a stream
   still runs, the running stream keeps writing to its node. (Requires
   per-stream correlation; see §3.3.)
5. **Restore:** a node whose final stream completed restores as complete,
   closed or not. A node that died mid-stream restores as interrupted:
   partial content shown, retry offered.

## 2. Requirements

Committed here per process.md §2. Every mechanism in §3
must trace to a line below; reviewer-proposed hardening that traces to
nothing gets the disposition **"real, out of scope → backlog,"** not
fixed-on-branch.

### Hard requirements

- **R1 — Branching conversations:** edit a user message, navigate siblings,
  fork at any exchange boundary.
- **R2 — Cross-session resume:** a conversation restores with both its
  display and its client state (the model can continue where it left off),
  including state established *before* the first user input — the system
  prompt, app-attached turns, and pre-input UI appends (§3.4 baseline
  snapshot; capture is unconditional, restore behavior is configurable).
- **R3 — Durable failures:** a failed or cancelled exchange survives reload —
  the user's input, any partial response, and a retry affordance.
- **R4 — Display fidelity:** what was shown restores as shown, including
  UI-only appends and content with custom display. (History is an archive:
  restore shows what was shown *then*; changed display code affects future
  exchanges, not past ones.)
- **R5 — Display/model divergence:** what the model sees and what the user
  sees may differ and must be free to evolve independently. The mechanism
  for divergence remains ellmer/chatlas content types with custom display
  methods; history must make whatever divergence they produce durable.
- **R6 — One mental model across R and Python.** Parity is enforced by
  shared JSON fixtures and structurally parallel error messages (same
  conditions, same information — not byte-identical strings), not
  commit-lockstep.
- **R7 — Roadmap-ready:** editing, conversation forking, failed-message
  retries, and message-specific actions must map to primitives of this
  design, not to new subsystems. (§3.6 shows the mapping.)

### Explicitly out of scope

- **Multi-writer tolerance / CAS** (single-writer store assumption;
  kata `63kh` stays backlog).
- **Greeting/history coupling.** One greeting, N histories. The greeting is
  an ambient slot; `greeting_*` wire actions are excluded from capture.
- **Cross-language history loading** (an R-written record is not loadable
  by Python, and vice versa — turn state entries are provider-serialized).
- **MarkdownStream capture.** `output_markdown_stream()` is a separate
  component on a separate wire channel and is not part of the transcript.
- **Bookmark fidelity beyond the history pointer** (§3.8).
- **Retroactive re-render** of stored history under new display code (R4).

## 3. Design

### 3.1 Record model

`ConversationRecord` = conversation metadata + a tree of `ExchangeNode`s +
an active-leaf pointer. This evolves `main`'s existing v1 node record — it
already has the graph and positional navigation — rather than introducing a
parallel schema with migration machinery. Legacy v1 history records exist in
the wild (Python released, plus internal dev users), so legacy handling is a
committed read-gate import (Phase 7), decided 2026-08-27.

`ExchangeNode` envelope:

| Field | Contents |
|---|---|
| `id`, `parent_id`, `created_at` | Tree identity. Siblings under one parent are alternatives (edit, retry, regenerate). |
| `status` | `pending` (open/in-flight) · `ok` · `error` · `cancelled` |
| `input` | The user's submitted content (text + attachments), or absent for system-initiated nodes. |
| `messages` | Captured wire specs, in send order: `{role, segments: [{content, content_type}], icon?, attachments?}`. Source content, pre-render — never rendered HTML. |
| `state` | Keyed map of app-state entries written by registered capture hooks (§3.7): `{"<entry-name>": {kind, version, mode: "delta"\|"snapshot", data}}`. The blessed entry is `shinychat:turns` — the client-turn delta this exchange produced, or a full snapshot where the delta baseline no longer holds (§3.4). |
| `error` | Optional `{message, ...}` when status is `error`. |

`state` is a **generic surface from day one**: entries are written and read
only through the extension hooks (§3.7), and the blessed turns integration
is itself a registered consumer of those hooks — shinychat uses no private
channel. `messages` is not a state entry — it is universal and automatic.

#### Worked example (shape, not schema — field names finalized in Phase 3)

```jsonc
{
  "conversation_id": "c_9f2e",
  "title": "Quarterly report help",
  "active_leaf": "x_04",
  "nodes": [
    { "id": "x_00", "parent": null, "status": "ok",          // root: closed by the first user input
      "input": null,
      "messages": [],                                        // pre-input chat_append()s would be captured here
      "state": { "shinychat:turns": { "kind": "chatlas", "version": 1, "mode": "snapshot",
                 "data": ["<system turn>"] } } },            // baseline: system prompt + app-attached turns

    { "id": "x_01", "parent": "x_00", "status": "ok",
      "input": { "text": "Summarize the attached CSV", "attachments": ["…"] },
      "messages": [
        { "role": "user", "segments": [{ "content": "Summarize the attached CSV", "content_type": "markdown" }] },
        { "role": "assistant", "segments": [
          { "content": "…", "content_type": "thinking" },
          { "content": "Here are the highlights…", "content_type": "markdown" } ] }
      ],
      // one exchange = whole tool loop: 4 provider turns, 1 node
      "state": { "shinychat:turns": { "kind": "chatlas", "version": 1, "mode": "delta",
                 "data": ["<user turn>", "<assistant turn w/ tool request>",
                          "<tool-result turn>", "<assistant turn>"] } } },

    { "id": "x_02", "parent": "x_01", "status": "error",
      "input": { "text": "Now plot revenue by month" },
      "messages": [ { "role": "user", "segments": ["…"] } ],
      "error": { "message": "Provider timeout" } },          // no turns here — failed nodes MAY carry partial turns (§3.4)

    { "id": "x_03", "parent": "x_01", "status": "ok",        // retry = SIBLING of x_02, same input
      "input": { "text": "Now plot revenue by month" },
      "messages": ["…"],
      "state": { "shinychat:turns": { "kind": "chatlas", "version": 1, "mode": "delta", "data": ["…"] } } },

    { "id": "x_04", "parent": "x_03", "status": "ok",        // system-initiated: no input, not editable
      "input": null,
      "messages": [ { "role": "assistant", "segments": [{ "content": "Reminder: export closes Friday", "content_type": "markdown" }] } ] }
  ]
}
```

This is the *logical* record shape; the on-disk layout (single document vs.
split tree/messages/state files) is Q2's benchmark decision (§3.10).

Restore of this record with `active_leaf: x_04`: replay messages of
`x_00 → x_01 → x_03 → x_04` through the live pipeline (x_02 is off-path;
navigating to it shows the failed input with a retry affordance), and
`set_turns(x_00 snapshot + x_01 delta + x_03 delta)` on the client — or,
under the live-bootstrap restore option (§3.4), skip x_00's snapshot and
layer the deltas on the app's own initialization.

### 3.2 Capture (messages)

One hook per language at the existing wire choke point:

- Python: `Chat._send_action` (`_chat.py:2024`) — every chat action funnels
  through it before the single `send_custom_message` call.
- R: `send_chat_action()` (`utils-shiny.R:17`) — same property, 21 call
  sites funnel in.

The hook allowlists content actions (`message`, `chunk_start`, `chunk`,
`chunk_end`) and ignores bookkeeping (`history_update`, drawer, slash-command
sync, `update_cancel`, …) and `greeting_*`. Chunks are assembled into message
specs (Python already accumulates `_current_stream_segments`; R assembles at
the hook) and appended to the owning node.

Known edges, decided here:

- **`system`-role appends and pre-input state** are captured by the baseline
  snapshot: at the first user input, everything already in the display and
  in the client's turns — system prompt, app-attached turns, pre-input UI
  appends — is recorded into the root node (§3.4). Mid-conversation
  `system`-role messages still never reach the wire (Python drops them at
  `_chat.py:1463-1464`); they surface in the record only through turn capture,
  not through `messages`.
- **HTML dependencies** are session-scoped after serialization; the record
  stores specs pre-processing and restore re-sends through the live-session
  pipeline (exactly what bookmark restore does today in both languages).
- **UI-only appends are durable** — anything sent through the choke point is
  captured, whether or not a turn corresponds to it. This is R4/R5 working
  as designed, and it's what dissolves the old "fidelity cap" concern.

### 3.3 Boundaries, attribution, and admission

- **Exchange-open signal:** the history layer registers its *own* observer
  on the user-input value (Python: alongside the priority-9999 effect at
  `_chat.py:414`; R: an observer on `input[[<id>_user_input]]`), so exchange
  boundaries work for hand-rolled apps too — `chat_server()` is not
  required for history, only for the blessed auto-wiring.
- **Stream-finish signals (for eager writes):** Python
  `latest_message_stream.status()` / the stream task's `finally`
  (`_chat.py:1435`); R the `on_stream_complete` observer on
  `append_stream_task$status()` (`chat_app.R:565`).
- **Per-stream correlation** (required by the attribution rule, §1.4):
  Python has `_current_stream_id` — keep the stream-id correlation. Its
  pending queue does not survive Phase 2 either way: the admission decision
  (decided 2026-08-27) removes it, and even a queueing fallback —
  acceptable only if implementation proves it strictly simpler — would be a
  fresh mechanism, not this queue. The queue's latent stranding bug
  (appends queued behind a bare `message_stream_context()` are never
  flushed) ships on `main` today and is fixed in Phase 1 (kata `zhh9`). R
  has **no** guard today — concurrent streams can interleave
  `chunk_start`/`chunk_end` with no id on the wire. R gets a stream id; the
  record-side attribution uses it.
- **Admission and display attribution are separate contracts:** an admitted
  input closes the previous node and opens a new one; an already-running
  display stream keeps writing to its own node through its explicit stream
  correlation. Neither decision makes concurrent mutations of one shared
  attached turn client attributable. The built-in chatlas handler therefore
  rejects a second lazy provider stream before it is consumed or mutates the
  client, under the existing one-display-stream wire contract. No queue or
  custom concurrent-client mutation support is added; a future overlapping
  submission workflow must choose response scheduling separately.

### 3.4 State capture: the blessed turns integration

State entries are written by capture hooks (§3.7). The blessed integration —
registered automatically when a chat has an ellmer/chatlas client attached —
records the client's turns under the `shinychat:turns` entry:

- **Delta by default.** When capture fires, compare the recorded baseline
  (turn count + cheap identity check as of the last capture on the active
  path) against the client's current turns. If the baseline is still a
  prefix, record only the new turns as a `mode: "delta"` entry.
- **Snapshot fallback.** If the baseline is no longer a prefix — the app
  rewrote client history (e.g. via `set_turns()`) between inputs — record
  the full current turn list as `mode: "snapshot"`, which resets the
  baseline. Restore concatenates from the most recent snapshot forward.
  Deltas are an optimization with a defined escape hatch, never an
  assumption that turn history is append-only.
- **Baseline snapshot (root node).** The first user input closes the
  implicit root node with a `mode: "snapshot"` entry of everything already
  in the client's turns — the system prompt and any app-attached history —
  plus, in `messages`, any pre-input UI appends. (The greeting stays an
  ambient slot excluded from capture, per §2 — it is the one pre-input
  display element the root node does *not* own.) Capture is unconditional;
  what is configurable is restore (§3.5): replay the recorded bootstrap
  (default), or let the app's live initialization supply the prefix and
  layer the recorded user-driven deltas on top. The live option is a
  deliberate, root-node-scoped exception to R4's archive semantics.
- **Capture points.** Capture fires when an asynchronous `chat_append()`
  input closes (stream generator / promise — the stream-finish signals in
  §3.3), and again as a catch-up at node close, which records turn
  mutations no stream reported.
- **One shared client:** admitted inputs and explicit display-stream
  attribution may span node boundaries, but turn-state capture remains a
  serial operation over the one attached client. The built-in chatlas second
  lazy provider stream is rejected before consumption/mutation by §3.3, so
  this contract is not asked to reconcile two provider mutations.
- **Snapshot limitation:** a generic `ClientWithTurns` exposes only a current
  snapshot and cannot attribute arbitrary concurrent client mutations to an
  exchange. An exchange-owned provider journal is future backlog
  `shinychat#m3q6`; no queue or reconciliation is added here.
- **Record verbatim ("shinychat records, it doesn't decide").** Capture
  asserts nothing about client commit behavior. ellmer/chatlas store
  partial results on interruption, so a cancelled or errored node's turns
  entry is whatever the client holds at capture — nothing, a partial
  assistant turn, or completed tool turns plus a partial — recorded
  verbatim. Restore replays it verbatim, reproducing exactly the context a
  user who never reloaded would have; retry excludes it naturally (the
  rewind hook's prefix `set_turns` stops at the parent). Abort semantics
  follow from this principle: partials are preserved, never discarded.

All the machinery exists on `main`:

- Grouping/boundary logic: `_group_chatlas_turns` (`_history_client.py:78`),
  `group_ellmer_turns` + effective-role (`contents_shinychat.R:920-927`).
- Serialization: chatlas `model_dump(mode="json")` / `model_validate`;
  ellmer `contents_record()` / `contents_replay(tools=)`.
- Delta-by-count pattern: `extend_record_linear`'s
  `record_turn_count` diff — reused as arithmetic, freed from its
  echo-trigger and positional-alignment context, and extended with the
  prefix check above.

Entries are version-stamped (`kind`, `version`). A stored turn that can no
longer replay (removed tool, changed content class, provider skew) degrades
with a warning rather than failing the restore.

### 3.5 Restore

1. Read record (fail-closed graph validation with the same contract as
   #311's `validate_graph()`, written fresh per the re-derive decision).
2. **UI:** replay each node on the active path — input, then captured
   messages — through the live send pipeline (same path bookmark restore
   uses today). Nothing stored is ever trusted as HTML; everything re-renders
   through the standard sanitizing pipeline. Error/interrupted nodes render
   partial content plus a retry affordance (R3).
3. **Client:** `set_turns` of the active path's turn entries — the most
   recent snapshot on the path plus every delta after it. Under the
   live-bootstrap option (§3.4) the root snapshot is skipped and the deltas
   layer on whatever prefix the app's own initialization produced.
4. **Init/restore race:** Q1 resolved 2026-09-01: use
   disabled-until-restore-decision and reject defer-one-submission, which
   requires prohibited retained payload/continuation state. While
   `HistoryController.partition is None`, Phase 3 recorder callbacks are
   inert and must not fail the originating capture-eligible send. Phase 5
   blocks user dispatch and capture-eligible initial sends until the restore
   decision and its authoritative metadata publication complete; it admits no
   preselection capture. Every Python `chat_ui()` emits a private,
   conservative static initialization seed before React/input activation, so
   the client starts submission-blocked. V2 history's first authoritative
   runtime `history_update` resolves that seed and releases admission; Python
   v1 and history-disabled initialization immediately withdraw it, accepting
   that brief initial delay. R emits no seed. There is no public API,
   Chat-tag registry, post-mount action, second marker or owner, persistence,
   deferred submission, preselection buffer, provisional record or merge,
   queue, timer, or reconciliation.

### 3.6 Branching, editing, retries, actions (R1, R3, R7)

One primitive: **create a sibling at node X** — truncate the active path to
X's parent, fire the rewind hook, then submit.

- **Edit** = sibling with modified input.
- **Retry** (of a failed exchange) = sibling with the same input.
- **Regenerate** = sibling with the same input, re-requested.
- **Fork a conversation** = copy the path up to X into a new record.
- **Navigate** = move the active-leaf pointer; replay the selected path.
- **Input-less nodes** (system-initiated) are not editable and not branch
  points — there is no input to edit or resubmit.
- **Rewind hook:** the blessed implementation is
  `set_turns(prefix deltas)`; manual apps get the same hook to fix their own
  state. First consumer is our own integration, so it ships exercised.
- **Message-specific actions:** the exchange id is the stable handle.
  User-message actions target the node's `input`; assistant-group actions
  target the node's response. No separate message-id contract, no cursor.

### 3.7 Extension contract (generic hooks, blessed first consumer)

For any given app there is some state worth recording at each snapshot
point. It may be the chat client's turn history — ellmer/chatlas or any
third-party SDK — or other app state: input settings, artifacts,
selections. The mechanism is a callback registry over the node lifecycle:
registered callbacks may add, update, or remove named entries in a node's
`state` map at these points —

- **capture** — write entries when an async append closes and at node close
  (blessed: the turn delta/snapshot, §3.4).
- **restore** — consume the active path's entries (blessed: `set_turns`).
- **rewind** — react to path truncation (blessed: `set_turns` on prefix).

The blessed ellmer/chatlas integration registers its callbacks through this
same mechanism — no private channel — so the generalization is exercised
from day one by our own in-tree consumers. `messages` capture is universal
and automatic — every app, including fully manual and multi-agent apps,
gets durable display history and branching with zero integration. What
automatic capture does *not* give a manual app is state resume; that is
what a custom `state` entry is for, and the *public* registration API is
deferred until the contract has been proven by the in-tree consumers
(turns; and the hooks' use by restore/rewind themselves).

Accepted input and explicit display-stream attribution are not state
ownership. The blessed turns hook serially observes one shared attached client;
the built-in chatlas second lazy provider stream is rejected before
consumption/mutation under the one-display-stream contract. A snapshot-only
`ClientWithTurns` hook cannot attribute arbitrary concurrent client mutations.
An exchange-owned provider journal is future backlog `shinychat#m3q6`; this
contract adds no queue or reconciliation.

### 3.8 Bookmarking subsumed

A bookmark stores `{conversation_id, node_id}` — a pointer into the tree.
Restore goes through §3.5. One restore mechanism replaces two
(`chat_restore()` / `enable_bookmarking` become deprecated shims over the
pointer). This is the "exceptional implementation" bar for replacing the
legacy path: bookmarks become branch pointers for free.

This deprecates URL-encoded chat state outright: shinychat bookmarking
becomes **server-side only**, with the bookmark carrying the pointer and the
server holding the record. URL-encoded history already collapses at any
meaningful conversation length, so this is a net improvement — but it
requires record lifecycle management (a bookmark can outlive its
conversation record, and restore must fail visibly and gracefully when it
does) and clear user way-pointing through the deprecation window.

### 3.9 Trust

- The echo is deleted (#311): the server persists only what it accepted as
  input or emitted as output, so captured specs are server-authored by
  construction.
- Restore re-renders everything through the standard pipeline; no stored
  HTML is trusted (the legacy-`ui` question from the retrospective resolves
  the same way: legacy display fields are re-rendered, not replayed).
- The island-escape scanner + trust-on-wire provenance (harvested, Phase 1)
  closes the model-output raw-HTML vector independently.

### 3.10 Persistence

`main`'s `ConversationStore` plus the Phase 1 durability batch is the
starting point. This path is overwhelmingly write-hot: optimize for fast,
correct writes and reasonable reads. Q2 compared two candidate layouts:

- **(a) Single document** — the whole record rewritten atomically per save.
- **(b) Split layout** — the exchange tree (small by construction: ids,
  pointers, statuses, inputs) rewritten atomically as a whole;
  `messages` and `state` appended as immutable revisions and resolved from
  the latest revisions referenced by the tree.

The benchmark must be realistic to count: 140k+-token transcripts with many
tool calls and several forks, measured on the hot write path. This is a
testable, quantifiable decision — do not pre-optimize for a problem the
benchmark may show doesn't exist. The mandatory selection gate is atomic
coherence under killed or failed writes, including interrupted immutable
revision writes. Latency cannot select a candidate that fails correctness or
requires unbenchmarked tail-repair/recovery machinery. Store formats stay
independent per language (already decided); the shared contract is fixture
matrices over the record shape, not bytes.

**Q2 resolved (2026-08-28): choose single-document; reject split.** The
deterministic v2 workload had 153,348 message/state-content tokens, 200
exchanges, five forks, and the implicit root (206 nodes total). With three
warm-ups and 25 measured repetitions on APFS, split met the latency thresholds:
the smallest median improvement was 6.90x, the smallest p95 improvement was
2.50x, and cold reads were 1.38x slower. Its 100-stream-update path was
723.305 ms median / 750.249 ms p95 for single versus 103.388 ms median /
299.660 ms p95 for split.

Split nevertheless failed the mandatory coherent-recovery prerequisite:
after an interrupted immutable JSONL append, a later append can concatenate
with the unterminated tail and make the newly referenced revision unreadable.
Repairing or isolating that tail would be unbenchmarked recovery machinery,
so the latency result cannot select split. Single-document atomic
temp-file-plus-`os.replace()` therefore wins Q2; its failure stages expose old
before replacement and new after replacement. The concise split measurements
and escalation evidence are retained in `phase-3-mechanism.md`.

### 3.11 Conversation management and client-side work

The conversation-list surface (drawer, `history_update`, `update_siblings`
wire actions) is unchanged in concept and rides the new record — it renders
conversation metadata and the sibling structure the tree already carries.
Client-side (JS) work in this plan is deliberately small: delete the echo
reporter (Phase 2, from #311), render interrupted/error nodes with a retry
affordance (Phase 4), and keep the existing sibling-navigation UI pointed at
exchange ids. No client-side transcript state machine is added.

### 3.12 What this deletes from `main`

- The client echo (`${id}_messages` input + handlers) in both languages, and
  its guard family: R `is_replaying` / `suppress_next_save`; Python's
  stale-report dedup and `SilentException`-until-first-report behavior;
  `ui_offset` arithmetic. `Chat.messages()` becomes synchronous,
  record-sourced, with exchange status visible so apps can recognize
  cancelled/errored partials (§3.4 record-verbatim).
- Echo-triggered save observers (`message_response_effect`,
  `HistoryController`'s `@reactive.event(chat.messages)`).
- `extend_record_linear`'s positional turn↔UI alignment heuristic —
  alignment is recorded at write time, never reconstructed.
- The `chat_restore()` vs history duality (§3.8).

## 4. Phases

Python first to shape-stability, then the R port (process.md §3.2).
Keystone-first inside each phase: the end-to-end data flow lands
flag-guarded before hardening (process.md §3.1).

**Starting point:** a new branch off `main`. Everything is written fresh
against this plan; #311 serves as the design reference for Phase 2's core,
re-derived rather than rebased (decided 2026-08-27). Each phase opens with a
one-page mechanism note (the deferred design decisions for that phase)
signed off by the driver before code (process.md §3.4).

- **Phase 0 — decisions and alignment (complete, 2026-08-27).** All
  decisions are recorded:
  re-derive #311's core rather than rebase it; v1 records exist in the
  wild, so the read-gate import is committed; admission for mid-stream
  input; the other maintainer has signed off on the plan (all 2026-08-27);
  abort semantics decided 2026-08-27 as **preserve-partial,
  record-verbatim** (§3.4) — a cancelled/errored node keeps its captured
  messages and whatever turns the client committed. Discard would lose
  server-sent content the durability model treats as real, and cannot
  un-commit the partial turn the client SDK already stored; the
  re-derived Phase 2 core therefore deliberately departs from #311's
  `abort()` (which drops accumulated segments) and settles aborted streams
  into a status-marked entry.
  *Done:* the decisions above are recorded and the Phase 1 kata issues are
  filed (`bxwf`, `fshf`, `zhh9`).
- **Phase 1 — independent fix PRs against `main`** (mergeable in any
  order), each specified by its own self-contained kata issue — symptom,
  location, acceptance criteria — so a fresh agent needs no other context
  to work them:
  (a) store durability batch + failure-injection tests (kata `bxwf`);
  (b) island-escape scanner + trust-on-wire rendering provenance
  (kata `fshf`);
  (c) the Python pending-flush stranding bug, a `main` bug regardless of
  this plan (kata `zhh9`).
  (Verified 2026-08-27: `main`'s test instruments need no repair PR — the
  Playwright suite is green, the shared history-behavior matrix harness is
  real and CI-checked for drift, and no vacuous pins exist. Two process.md
  §5.1 items remain deliberately unverified for now: the deliberately-
  broken-fixture discrimination check runs at the §5.1 gate before Phase 3,
  and fixture value-class coverage is an acceptance criterion of kata
  `bxwf`.)
  *Done when:* the three PRs merged (or in review) on `main`.
- **Phase 2 — server-authoritative core (Python; complete 2026-08-28).**
  Echo deletion,
  transactional send-then-commit, synchronous `messages()` — #311's core,
  re-derived cleanly from the draft's design (decided: no rebase attempt).
  Land the exchange-open signal and stream attribution here. The client
  source and `js/dist` advance, but only the Python package receives the
  new bundle (`make js-build py-update-dist`); R keeps its existing packaged
  bundle and echo until its Phase 6 port. The shared transcript fixture is
  re-derived and revised, not copied unchanged: admitted user intent is not
  rejected by an active stream, and cancellation/error preserve content
  already sent. See `phase-2-mechanism.md`.
  *Done when:* no Python `${id}_messages` consumer or reporter exists;
  `Chat.messages()` is synchronous in the same flush; the revised shared
  transcript fixture passes in Python; a forged messages input cannot
  mutate transcript or history (hard transport rejection is acceptable).
- **Phase 3 — exchange record + capture + store (Python; `shinychat#qf2r`;
  complete and closed 2026-08-31).**
  Node schema,
  choke-point capture, baseline snapshot at first input, delta/snapshot
  turn capture, eager writes + lazy close, statuses, incremental atomic
  saves. Q2 selected single-document atomic persistence after rejecting split
  recovery. Keystone commit first: one flag-guarded path
  from submit → captured node → stored record → restored display, however
  ugly.
  See `phase-3-mechanism.md`; no feature code starts before the recorded Q2
  decision and updated phase note are reviewed.
  *Done when:* kill the process mid-stream at any point and reload — the
  record contains the user's input, all specs sent so far, and a coherent
  status; the worked example in §3.1 round-trips through the store.
- **Phase 4 — restore + branching + bookmark pointer (Python;
  `shinychat#azvt`).** Replay,
  `set_turns`, rewind hook, the sibling primitive, retry affordance. Port
  the predecessor branch's edit/navigate Playwright suite to this base (Q3).
  Begin with integration gate `shinychat#ykxh`: merge `main`'s stable
  conversation-ID work from PR #343 and settle its v2 identity semantics
  before the restore keystone touches record activation.
  See `phase-4-mechanism.md`; Phase 3's mechanism note is completed context,
  not a live source for Phase 4 decisions.
  *Done when:* the ported suite is green (or Q3's narrow upgrade is scoped);
  edit, retry, and regenerate all go through the one sibling primitive; a
  restored client continues the conversation correctly (turn count and
  content verified).
- **Phase 5 — hard core + adversarial review (Python; `shinychat#fg70`).**
  Q1 is resolved: P5.0's selected disabled-until-restore-decision guard may
  proceed under `shinychat#fbhe`; defer-one-submission is rejected. Later
  children remain blocked. Then audit clear/switch/abort, unreplayable-turn
  degradation, and the error-on-reload affordance, followed by one adversarial
  review pass in the critical-review format on exactly this subsystem. See
  `phase-5-mechanism.md`; Phase 4's mechanism note is completed context only.
  *Done when:* the audit checklist has a test or a recorded decision per
  item, and the adversarial pass's P1s are fixed or dispositioned.
- **Phase 6 — R port.** After Python shape-stability (reviewed, chains
  terminated). Shared JSON fixture matrices + structurally parallel error
  messages as the parity contract. R stream-correlation work lands here (or
  earlier if the R port of Phase 2 needs it).
  *Done when:* shared fixture matrices pass in both languages with
  structurally parallel errors; the R port introduces no mechanism absent
  from Python.
- **Phase 7 — legacy and release.** Legacy-record import at the read gate
  (committed 2026-08-27: v1 records exist in the wild): v1 nodes map to
  exchange nodes (`ui` → messages via re-render, turns carried over).
  Deprecations (`chat_restore`, echo-dependent APIs, URL-encoded bookmark
  state, §3.8 — with user way-pointing). Docs.

## 5. Open questions and cheapest checks

| # | Question | Cheapest check |
|---|---|---|
| Q1 | **Resolved 2026-09-01:** disabled-until-restore-decision; defer-one-submission rejected because it needs prohibited retained payload/continuation state. The prototype found the current path fail-open (a real browser accepted and cleared in 35 ms while its first update was held); disposable client checks preserved a draft plus attachment and blocked every submission route; server checks covered 12 recorded/live, no-target/success, raw/complete/stream cases plus live cancellation. Across 31 samples/path, no-delay medians were about 0.08-0.40 ms; with 25 ms per store operation, no-target medians were about 27.2 ms and target medians 54.2-54.4 ms, with p95 at most 54.9 ms. | Retained P5.0 implementation under `shinychat#fbhe`; see `phase-5-mechanism.md`. |
| Q2 | Resolved 2026-08-28: single-document atomic layout; split rejected on coherent-recovery failure (§3.10). | 153,348-token deterministic workload; 25 repetitions after three warm-ups. Split met latency thresholds (minimum 6.90x median, 2.50x p95; cold reads 1.38x slower) but failed interrupted-append recovery. |
| Q3 | Does the *client wire* need node ids, or does `main`'s positional edit/navigate addressing survive adversarial use? (Record nodes have ids regardless.) | Port the predecessor branch's edit/navigate Playwright tests; upgrade the wire narrowly only on red. |
| Q4 | Provider version skew tolerance? | Save turns under current ellmer/chatlas, replay under the adjacent release (half a day). |

Four further questions were resolved during Phase 0 (2026-08-27) and are
recorded inline where they apply: re-derive #311 rather than rebase (§4),
v1 legacy records exist → read-gate import committed (§3.1, Phase 7),
admission for mid-stream input (§3.3), and maintainer sign-off on the plan
(Phase 0). Abort semantics (preserve-partial, record-verbatim) is recorded
in §3.4 and Phase 0.

## 6. Process guardrails

How agents work through this plan — scope discipline, sequencing, the
review-loop escalation valve, verification prerequisites, and context
hygiene — lives in **[process.md](process.md)**, which is normative for this
effort. Headlines: requirements (§2) are the boundary with "real, out of
scope → backlog" as a standing disposition; keystone-first per phase;
Python to shape-stability before the R port; three findings against one
mechanism forces a shape consult; no feature code on unverified instruments.
