# Phase 5 mechanism: hard core and adversarial review (Python)

**Status:** P5.0 blocked on a supported Py Shiny reactive-context capability ·
2026-09-02
**Phase:** plan.md §4, Phase 5
**Kata:** parent `shinychat#fg70` under epic `shinychat#6d0d`
**Context:** `phase-4-mechanism.md` is completed context only. This note is
the Phase 5 gate and the only phase-local mechanism reference for new work.

## Objective and boundary

Bring the Python v2 exchange-tree path to shape-stability at the remaining
hard boundaries:

1. install Q1's selected init/restore-window guard;
2. audit clear, switch, and abort/cancellation against the existing
   transcript, recorder, and destructive-mutation contracts;
3. degrade an explicitly unsupported stored turns payload without losing its
   captured display archive; and
4. show the bounded persisted error message for a restored errored exchange,
   while retaining the existing retry sibling path.

The phase ends with one adversarial critical review over exactly these
mechanisms, followed by the deletion/scope pass. It is Python-only. Phase 6
ports the stable shape to R; Phase 7 owns legacy import, public hook exposure,
and deprecations.

Phase 5 adds no queue, preselection buffer, provisional record or merge,
timer, reconciliation pass, cursor, CAS, second record owner, second client
transition marker, client transcript state machine, rendered-HTML storage,
Q3 addressing expansion, bookmark-fidelity change, R server work, or legacy
work. The sole approved exception is P5.0's private one-shot Python-v2
initialization barrier owned by `ChatHistory`, defined below; it is not a
payload queue, recorder buffer, second marker, public API, or persistence.

## Existing ownership remains authoritative

The phase does not replace the Phase 4 shape:

- `_ExchangeRecorder.record` is the sole active v2 record owner.
- `ChatTranscript` remains the owner of accepted input, successfully sent
  display specs, and stream attribution.
- `Chat._destructive_history_mutation()` remains the one destructive history
  transaction. Its existing input-block mode remains the only server-side
  destructive admission mechanism.
- `ChatHistory` may own P5.0's one private, one-shot initialization barrier.
  It is scoped to the initial v2 restore decision, not a general admission
  predicate or lifecycle subsystem.
- `historyTransitionPending` remains the one client lifecycle marker.
- `resubmit()` remains the only branch-producing primitive.
- The existing capture, restore, and rewind registries remain the three
  state-hook registries.

Each Phase 5 behavior maps directly to R2 (resume and client state), R3
(durable failed/cancelled exchanges), R4/R5 (display archive independently of
model state), or R7 (reuse existing primitives).

## P5.0: Q1 decision gate

**Q1 resolved 2026-09-01:** select
**disabled-until-restore-decision** for `shinychat#fbhe`. Reject
**defer-one-submission**: preserving its first raw input and attachments for
later re-entry requires prohibited retained payload/continuation state. There
is no third mechanism.

The Phase 3 no-op while `HistoryController.partition is None` is deliberate
only until Phase 5. It avoids failing an originating send before history
selection, but it does not make that send durable. `partition` is assigned
before target lookup and restore, so it is not the restore-decision boundary.
Decision completion means either a successful selected-target restore or an
approved fresh-draft recovery, in both cases followed by required metadata
completion. Capture-eligible work remains closed until that completion even
when `partition` is non-null.

The disposable ambient `_capture_admission` predicate is **DELETE/REPLACE**
and must not land. `partition`, record/controller state, and destructive
transaction ownership cannot distinguish an unresolved restore from an
ordinary fresh draft, and a task-owned destructive transaction cannot safely
span construction plus reactive reruns. They therefore cannot supply the
selected guard without either overblocking or introducing forbidden state.

The sole approved server mechanism is one private, shared, one-shot
initialization barrier owned by `ChatHistory`. Create it immediately after
v2 recorder installation, before input activation can admit capture-eligible
work. Its outcome contains only the initial-message decision needed by
startup append behavior: `fresh` after a no-target result or approved
fresh-draft recovery, and `restored` after a successful selected-target
restore. It holds no input, attachment, message, continuation, recorder
buffer, provisional record, merge state, or persisted state.

Await that shared barrier immediately before each capture reservation:

1. `Chat._record_accepted_user_input_with_capture()`, before accepted-input
   capture;
2. `Chat._append_complete_message()`, before complete-append reservation; and
3. `Chat._append_message_chunk(..., chunk="start")`, before root-stream
   reservation.

Each waiter must shield (or equivalently isolate) the shared barrier so an
individual cancellation cannot cancel it. Session teardown must terminate the
shared barrier itself and cancel/release its blocked waiter tasks; shielding
does not keep teardown-owned tasks alive. No teardown path may publish a
client release after the session is gone. A post-commit recorder callback is
too late. The barrier never wraps `_send_action`; greeting and bookkeeping
remain excluded exactly as in Phase 3. Restore replay bypasses naturally
through the existing `_replay_exchange_display()` ->
`Chat._restore_bookmark_message()` route: that private restore append uses the
existing destructive transaction and direct transcript reservation rather than
any of the three admission methods above. Do not route replay through public
`_append_complete_message()` or root-stream start, and do not infer a bypass
from arbitrary destructive-transaction ownership.

Resolve the barrier only after the no-target/success result or approved
fresh-draft cleanup **and** the authoritative `history_update`. A live-session
error or cancellation completes cleanup and that update before releasing
waiters; teardown cancellation ends the barrier without a client release.
This preserves the existing fresh-draft failure contract and gives the client
one authoritative release path.

For Python v2, manual startup `chat.append_*()` calls wait at the relevant
reservation and then execute after either live decision. The v2
`Chat(messages=...)` initialization effect must likewise wait for the
one-shot result: it runs for no-target/fresh-draft and is suppressed after
successful target restore, preserving its previous no-duplicate behavior.
Python v1 and history-disabled modes create no server barrier and retain their
existing constructor-message ordering; their existing first
`history_update` withdraws the conservative client seed, with the authorized
brief initial delay. R creates no seed or barrier and remains unchanged.

Every Python `chat_ui()` emits the private static attribute
`data-shinychat-history-transition-protocol="completion-v2"` before
React/input activation. This is intentionally an unconditional, conservative
Python seed: `chat_ui()` has no `Chat` or history-mode context at tag
construction time. The client parses the attribute in `chat-entry.ts` and
seeds only the existing `HistoryStore.transitionProtocol`; it leaves
`initialized` false, with empty conversations/active ID and no pending
marker. The seed starts submission blocked. It is configuration, not a
lifecycle marker, owner, completion signal, release action, or persistence.
V2 history's first authoritative runtime `history_update` resolves the
configuration and releases admission; capability withdrawal remains
authoritative and clears pending state under the Phase 4 protocol-change rule.
Python v1's existing `history_update` withdraws the seed to `completion-v1`;
history-disabled Python uses the existing `history_update` action type with
`enabled=false` as its initial withdrawal, accepting the authorized brief
initial delay. R emits no seed and retains its current behavior. This adds no
public API, Chat-tag registry, new post-mount action, second marker or owner,
deferred submission, payload field, continuation, queue, buffer, provisional
record, merge state, or persistence.

The existing ChatInput guards must cover Enter, send-button, attachment-only,
slash-command, suggestion, and imperative submissions while preserving the
uncontrolled draft and staged attachments; the ChatApp `submitUserInput`
handler must recheck the same condition before optimistic `INPUT_SENT` or
transport dispatch. The `ChatHistory` barrier is neither a second client
marker nor a general scheduling owner.

### Completed Q1 evidence

On 2026-09-01, the current path was shown fail-open: a real browser accepted
and cleared while its first `history_update` was held, in 35 ms. Disposable
client checks preserved a seeded draft and attachment while blocking Enter,
send-button, attachment-only, slash-command, suggestion, and imperative
submission routes. The production-shaped server probe passed all 12
recorded/live bootstrap, no-target/successful-restore, and
raw/complete/stream combinations; the streaming case covered root start,
update, and finish. It also passed live cancellation cleanup/release.

The server probe measured actual `_init_history` decision work from immediately
before its call through store lookup, restore/materialization/replay,
metadata, `history_update`, and settlement. It used 31 samples per
bootstrap/path: no-delay medians were about 0.08-0.40 ms; with a realistic
25 ms injected delay per store operation, no-target medians were about
27.2 ms and successful-target medians about 54.2-54.4 ms, with p95 no greater
than 54.9 ms. Target paths perform target `get()` plus the authoritative
metadata `list()`. The prototypes were deleted.

`bdd5089b` (`fix(history): recover live restore materialization`) is the
bounded prerequisite that moved live-bootstrap turn materialization into the
existing restore failure contract. Its focused regressions independently PASS.
`e07c6c57` (`fix(history): recover cancelled initial preflight`) completes
the remaining initial-only preflight boundary in
`_restore_initial_exchange_record()`, shared by the bookmark-pointer,
bookmark-conversation, and browser/URL `_init_history` target paths. Its
`BaseException` catch runs `_clear_failed_restore()` exactly once before the
existing outer initializer settles false/fresh, so it publishes the one
authoritative release `history_update` and re-raises the exact cancellation.
The production-init regression injects cancellation from
`_prepare_exchange_restore()`, proves replay never begins, the stored target
is untouched, cleanup and false settlement each occur once, and a later
initialization call is a no-op. Do not move this catch into the shared
preflight helper or the general restore method. Switch preflight remains
unchanged: it retains the Phase 4 no-target-mutation behavior.

Roborev 1174 HIGH is the second independent P1 against the one-shot barrier
mechanism, after the root-stream identity correction. In browser/URL restore,
the browser sends `browser_token` only after the first server reactive flush.
An initial constructor message or ordinary startup append awaiting the barrier
during that sequential flush therefore prevented the input which lets
`_init_history` settle the barrier from arriving. The existing private
`_await_initial_v2_decision()` now reactively requires the existing
`browser_token` before shielding the barrier only for browser/URL callers that
can read reactive sources. Initial effects then suspend and rerun when the
token arrives instead of parking the flush. Nonreactive/manual callers and
Shiny `ExtendedTask`s cannot safely register that dependency and continue to
await the same shielded barrier directly; extended tasks do not participate in
the sequential initial flush, and normal user-originated work cannot reach
them before the existing client gate releases. This adds no state, queue,
marker, owner, or second barrier.

Production-browser regressions cover both previously deadlocking shapes:
browser/no-target renders the constructor message and an ordinary startup
append after token/init; URL/selected-target replays the stored input,
suppresses the constructor message, and records the startup complete append
as its existing inputless child (`n_0002` parent `n_0001`). The focused
nonreactive unit regression proves a browser-mode manual caller still waits
for and receives the one shared fresh result without a browser token. The new
startup-barrier browser suite (2 tests), focused history unit selection (10
tests), and adjacent v2 restore browser suite (7 tests) pass.

The third finding against the barrier mechanism triggered the required
three-findings valve. The selected PATCH keeps the one-shot barrier but
deletes the `bdea58c3` RuntimeError message matching. A settled barrier now
returns through the same shielded await before any browser-token read. For an
unsettled browser/URL barrier, only the `browser_token` reactive read is
guarded: a caller with no reactive context or Shiny's `DenialContext` falls
back to that same shielded await, while `req(token)` remains outside the
guard so token validation errors propagate unchanged. Ordinary initial effects
still subscribe to the existing token and suspend until it arrives. This is a
context distinction, not another barrier, queue, marker, owner, or admission
state.

The startup fixture now uses a per-process temporary store, matching adjacent
isolated Playwright fixtures rather than a repository-local directory.
Its browser/no-target case also submits through normal `Chat(client=...)`
automatic streaming and receives the expected assistant response, proving a
post-initialization Shiny `ExtendedTask` neither reads the token nor fails.
The unit regression separately proves a pre-settled barrier returns from a
real `ExtendedTask` without a token read.

The selected guard must:

- create no durable preselection record, recorder buffer, or merge state;
- admit no capture-eligible event before restore decision completion;
- preserve the browser draft/attachments without synthetic rollback;
- release on success, handled failure, and cancellation; and
- compose with the existing `completion-v2` marker without introducing
  another marker, owner, queue, or public surface.

The completed evidence selects this guard. Do not retain deferred submission
or invent a third scheduling mechanism.

## P5.1: Clear, switch, and abort audit

The audit is an evidence matrix, not a new lifecycle subsystem. For each item
below, add a production-path regression or record a requirement-grounded
disposition on `shinychat#fg70`:

| Boundary | Required outcome |
|---|---|
| Generic clear with no active stream | Drain existing terminal settlement exactly once before mutation; no recorder consumer is invented. |
| Generic clear with active stream | Reject before display, recorder, turns, active ID, or store mutation. |
| Generic-clear concurrent tail | Retain input accepted after the clear send has begun, along with its subsequent transcript ownership, rather than deleting that concurrent tail. |
| Switch | Preserve the Phase 4 destructive boundary and fail-to-fresh-draft outcome. The switch path uses its existing server-side input block, which releases on success, error, and cancellation. |
| New and delete | Preserve their existing destructive transaction and fail-to-fresh-draft outcome. Their client coordination is the existing `historyTransitionPending` marker, not the switch server block and not a new marker. |
| Inactive delete and failed target preflight | Retain existing no-target-mutation behavior; do not expand the active-transition protocol. |
| Stream cancellation/error before and after sent chunks | Persist every sent message, record the terminal status and verbatim committed turns, and preserve the original cancellation/error through capture cleanup. |
| Session teardown/abort while a stream is open | Preserve only committed display messages and state already persisted before teardown. Do not claim that unpersisted partial turns survive; the open stream remains pending on reload unless its terminal state was already recorded. No synthetic settlement sweep is added. |
| Catch-up at the next user action | Capture only through the existing explicit exchange/node-close path; an older stream retains its opening exchange attribution. |

The audit must not change abort to discard-on-reload. A failed or cancelled
node stays immutable; retry continues to rewind to its parent and create a
sibling through `resubmit()`.

## P5.2: Unsupported-turn degradation

Phase 4 remains strict for invalid graph structure, unknown state keys,
malformed state envelopes, invalid modes, and restore transport/persistence
errors. Phase 5 narrows degradation to a private classified compatibility
result, computed before any restore mutation, while materializing the
effective `shinychat:turns` suffix. Materialize from the most recent effective
snapshot and its following effective deltas. A structurally valid incompatible
entry superseded by that snapshot is irrelevant. Any incompatible effective
entry means the effective suffix cannot be restored.

The turns integration reports that private classified result to the controller
without mutating the stored record or generalizing a public hook contract. The
controller:

1. completes normal graph validation and display replay;
2. leaves the displayed exchange path and its retry eligibility intact;
3. makes no `set_turns` call with data derived from an incompatible stored
   entry, a partial sequence, a guessed sequence, or a reconstructed
   sequence; and
4. sends one bounded visible warning that model context could not be restored.

The resulting state is explicitly **display-restored, model-context-unavailable**.
The warning must tell the user that continuing starts from the app's live
client state, not from an inferred historical context. In recorded-bootstrap
mode, that means the empty/app-initialized client state after restore entry;
in live-bootstrap mode, it is the app's live initialized prefix. It may not
expose raw provider payloads or stack traces. Phase 5 does not invent
selective state-entry skipping for arbitrary hooks.

Tests distinguish classified unsupported turn content from corruption:
an incompatible effective kind/version/content preserves display and warns
once, while an incompatible superseded entry is ignored; malformed entry,
unknown state key, invalid mode, graph invalidity, and restore-send failure
remain fail-closed through the approved fresh-draft recovery.

When degradation is selected, the controller completes the ordinary target
activation and metadata publication without entering fresh-draft recovery. It
must establish the advertised live baseline before input is released:
recorded bootstrap deterministically calls `set_turns([])` solely to clear
stale attached context, while live bootstrap leaves the app's live initialized
prefix untouched. The recorded reset contains no data from an incompatible
stored entry. No `set_turns` data may derive from an incompatible stored entry,
and neither path applies a stored partial, guessed, or reconstructed sequence.
The one fixed warning is bounded and provider-neutral:
`Conversation display was restored, but model context was unavailable.` It is
emitted once as part of the successful degraded restore, before the initial
`history_update` releases the client gate.

## P5.3: Detailed error on reload

The v2 schema already stores only `ErrorEntry.message`. Define
`MAX_HISTORY_ERROR_MESSAGE = 256` Unicode code points and this closed,
core-owned catalogue of fixed safe summaries:

- `The response could not be completed.` (generic fallback)
- `The response stream could not be started.` (known root-stream start
  failure)
- `The response stream could not be completed.` (known terminal stream-send
  failure)

At the error write boundary, a core outcome selects one exact catalogue value.
Exception-derived text, including every existing `str(exception)` path, maps
to the generic fallback; it is never a summary source. Normalize the selected
value to NFC; replace control characters and line separators with spaces;
collapse whitespace; trim; use the generic fallback when it is empty; and
truncate to 253 code points plus `...` when it exceeds the limit. This
normalization is a bound and presentation cleanup, not a secret or
provider-body scrubber: no regex redaction or traceback filtering is treated
as sufficient. Store only the resulting plain-text message, never a `repr`,
traceback, or structured provider payload.

On restored input-bearing `status == "error"` nodes, extend the existing
ephemeral exchange-status projection with the bounded message and render it
as plain text through React adjacent to the existing Retry affordance.
Projection applies the same cap and normalization without mutating records,
then displays a value only when it exactly matches the fixed catalogue; every
unknown or unrecognized legacy value becomes the generic fallback. A legacy
value that happens to equal a catalogue literal contains only that safe
literal and projects as it. Pending/interrupted and cancelled nodes retain
their current status/retry behavior and do not receive error detail.

No new persisted error fields, provenance field, public trust API, sanitizer
subsystem, regex sanitizer, provider response, attachment metadata, or
error-derived client state are added. The projection is ephemeral: it is
regenerated from the selected record path, does not mutate the failed node,
and does not affect sibling navigation or `resubmit()`. Tests cover an errored
node with and without partial assistant content, normalization/truncation and
plain-text React rendering, generic fallback for exception-derived,
unknown, and legacy values, catalogue-specific core outcomes, retry
immutability, and the absence of detailed text for pending/cancelled nodes.

## Sequencing and task graph

All Phase 5 children are now instantiated under `shinychat#fg70`. Their
implementation dependency chain is explicit:

1. **P5.0 selected init guard (`shinychat#fbhe`).** It is the entry slice and
   is the only active implementation task.
2. **P5.1 lifecycle audit (`shinychat#bj1n`).** Blocked by
   `shinychat#fbhe`; exercise clear/switch/abort against the selected guard
   and existing transaction boundaries.
3. **P5.2 unsupported-turn degradation (`shinychat#yebr`).** Blocked by
   `shinychat#bj1n`; keep strict corruption behavior separate from
   effective-suffix compatibility degradation.
4. **P5.3 detailed error reload affordance (`shinychat#bfq8`).** Blocked by
   `shinychat#yebr`; add only the bounded input-bearing error projection and
   its plain-text React rendering; run `make update-dist` if JS/SCSS changes.
5. **P5.4 acceptance, deletion pass, and adversarial review
   (`shinychat#xt5q`).** Blocked by `shinychat#bfq8`; review the coherent Phase
   5 subsystem in critical-review format. Every P1 is fixed with a regression
   or dispositioned in Kata before closure.

Only implementation is blocked by these links; independent read-only
investigation, test design, verification, and review may run ahead. A review
finding outside R2-R5/R7 receives the standing
`real, out of scope -> backlog` disposition.

### Velocity and concurrency policy

Use parallel agents proactively for independent read-only investigation, test
design, verification, and review. Parallel code changes are allowed only when
the dependency state permits them and write scopes are disjoint. Never start
blocked implementation, or trade away required reviews, verification, or
phase gates for speed. Later-task investigations may run ahead, but every
decision and finding must be revalidated against that task's eventual baseline
before implementation or disposition.

## Verification

Before P5.0 code, run the current history/transcript focused suite, the
existing transition/browser coverage, format, and Pyright. The prototype
must demonstrate discriminating behavior for both Q1 candidates and is
deleted before implementation.

For implementation, require focused controller and production browser tests
for initial restore, the pre-`history_update` Python-v2 gate, immediate
v1/history-disabled withdrawal, unchanged R admission, clear/switch/abort,
effective-suffix
degradation, and restored-error catalogue/legacy-fallback states; JS
lint/test/build and `make update-dist` when client code changes; the R
shared-client hook check for shared bundle compatibility; and the full
`make py-check` gate. Record any unrelated failure by Kata ID.

The final adversarial review must assess:

- the requirements trace and pre-refused scope;
- all `partition is None` and restore-decision paths;
- destructive transaction, terminal settlement, and cancellation ordering;
- fail-open versus fail-closed classification for turn replay;
- user-visible error/warning text and safe rendering;
- the Phase 4 ownership/deletion baseline.

## Initial deletion pass

Phase 5 begins with five top-level lifecycle/state abstractions: transcript,
recorder, destructive history transaction, one client transition marker, and
the three hook registries counted as one extension surface. The sole approved
exception is the private, one-shot `ChatHistory` initialization barrier above.
It may carry only the fresh-versus-restored initial-message outcome and must
not become a general admission predicate, queue, marker, public surface, or
ordering subsystem. The final pass must name that barrier, show its
requirement trace, or delete it.

## Current handoff

Landed: Phase 5 parent `shinychat#fg70` is created and claimed on
`feat/history-exchange-tree`; the authorized Q1 seed amendment and probe
evidence are incorporated in this note. `bdd5089b` independently repaired
live materialization failure recovery. Client seed `ad177514` is committed.
The uncommitted ambient `_capture_admission` predicate is parked/rejected and
must not land. All Phase 5 children are instantiated:
`shinychat#fbhe`, `shinychat#bj1n`, `shinychat#yebr`, `shinychat#bfq8`, and
`shinychat#xt5q`.

Current: `0e3ecd1a` corrects the three `1826d8f6` P1s. Root-stream exchange
selection now occurs after the one-shot barrier; elevated initialization
priority is completion-v2-only; history-disabled withdrawal follows
constructor messages; and `shinychat.playwright.Chat.send_user_input()` is
literal again. Production-path coverage includes a held root stream attaching
below the restored exchange, real restored-target `Chat(messages=...)`
suppression, v1/history-disabled message-before-withdrawal ordering, and
held-WebSocket Send-button, attachment-only, suggestion, and real
slash-command blocking. `e07c6c57` fixes the independent initial-preflight
cancellation P1: the initial-only `BaseException` boundary executes approved
fresh-draft cleanup and one release update before false/fresh barrier
settlement, preserves the exact cancellation, and cannot rerun initialization.
Its focused history/controller suite passed 303 tests; format and Pyright are
clean.

Roborev 1174 HIGH is incorporated as the second independent P1 against the
barrier mechanism. The existing barrier awaiter now makes browser/URL initial
effects require the existing `browser_token` before waiting, which lets the
first flush suspend and rerun instead of deadlocking. Nonreactive/manual and
`ExtendedTask` callers retain the direct shielded wait because they cannot
subscribe to reactive input; this preserves normal post-release streaming.
New real-browser coverage passes for browser/no-target constructor plus
startup append and URL/target restore, constructor suppression, and the
startup append's existing inputless-child targeting. The focused history
selection (10 tests), full history unit module (82 tests), and adjacent v2
restore browser suite (7 tests) pass; the new startup-barrier browser suite
passes 2 tests. `make py-check-format`, `make py-check-types`, and
`git diff --check` pass. Self-review is 100/100: the browser-token dependency
is limited to the existing barrier awaiter and browser/URL reactive effects,
the `ExtendedTask` exception is documented and covered by the adjacent
streaming browser suite, and the fixture discriminates both no-target and
selected-target outcomes. This bounded correction is pending commit and the
existing independent P5.0 review; downstream children remain blocked.

The three-findings valve is now resolved by the authorized PATCH above:
`bdea58c3`'s RuntimeError text matching is removed. The barrier fast-path
returns before reactive access, and unresolved browser-token access falls
back only for absent reactive context or Shiny `DenialContext`; `req(token)`
and all other errors propagate. The startup fixture now has a per-process
temporary store and proves normal automatic streaming succeeds through the
real Shiny `ExtendedTask` after initialization, while the existing browser
no-target and URL-target startup cases remain intact. Focused unit selection
(11 tests), startup-barrier browser suite (2 tests), and adjacent v2 restore
browser suite (7 tests) pass. The full history unit module passes 83 tests;
`make py-check-format`, `make py-check-types`, and `git diff --check` pass.
Self-review is 100/100: the fallbacks are restricted to the token read, the
settled path preserves cancellation/result behavior through the same shielded
future, and the production regression covers the former ExtendedTask failure.
This follow-up is pending commit and the existing independent P5.0 review.
Downstream children remain blocked.

Post-valve independent review supersedes the preceding self-review conclusion:
`49572407` closes the observed ExtendedTask failure, but it is not an accepted
final shape. It imports Py Shiny's private `DenialContext`, and the fallback
cannot distinguish an expected unavailable reactive read from an unrelated
`RuntimeError` using supported APIs. No further incremental barrier patch is
authorized.

P5.0 is blocked pending Garrick's decision. The recommended replacement is a
narrow typed public Py Shiny predicate, conceptually
`reactive.can_read_reactive_sources()`, that is true only where a reactive read
is legal and registers a useful dependency, and false outside reactive
execution and inside `ExtendedTask`. Shinychat would then delete all private
context imports and exception classification, require `browser_token` only
when that predicate is true, and otherwise await the same one-shot barrier.
This retains the approved owner and outcomes without a queue, continuation,
payload holder, marker, or new shinychat public API. Caller flags cannot cover
arbitrary app startup effects; isolation loses invalidation; post-flush
continuations reintroduce prohibited retained scheduling; and moving browser
input delivery earlier requires a broader client/Shiny lifecycle contract.
`shinychat#fbhe` and all downstream Phase 5 children remain blocked.

The test contract is resolved by the 2026-09-02 `shinychat#fbhe` orchestrator
decision: no global/helper/fixture readiness wait. Ordinary existing browser
tests explicitly wait for a nonempty `loc_input_button` immediately before
their raced send; initial-gate, initial-seed-withdrawal, and stale-completion
evidence deliberately retain their direct blocked submissions. The full
browser gate identified the ordinary sites, including page-chat fixtures, and
they are now explicit rather than hidden behind controller behavior.

The P2 imperative-route review request is dispositioned: the mounted
`ChatInput` and `ChatApp.submitUserInput` transport integration is the
production boundary, and existing unit coverage exercises the imperative
recheck there. No test-only imperative browser hook will be added.

Verification is green: `make py-check` passed with 207 Playwright tests and
915 Python tests (one skipped, 34 established warnings); JS lint and 1,260
tests passed with 23 skips and two existing React `act()` warnings; 22 R
history-hook tests passed; and all package asset copies are equal. This task
is pending its required independent review; `shinychat#bj1n` remains blocked
by `shinychat#fbhe`, `shinychat#yebr` by `shinychat#bj1n`,
`shinychat#bfq8` by `shinychat#yebr`, and `shinychat#xt5q` by
`shinychat#bfq8`. Do not begin R, legacy, or another scheduling/ownership
mechanism.

Status-only self-review: 98/100 (clarity 25/25, comprehensiveness 24/25,
feasibility 25/25, consistency 24/25). P5.0 remains pending independent
review; `shinychat#bj1n` and later children remain blocked. No mechanism
decision is open.
