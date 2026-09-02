# Phase 5 mechanism: hard core and adversarial review (Python)

**Status:** P5.0 replacement approved; implementation may resume · 2026-09-02
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
work. P5.0 adds no initialization barrier or reactive-context adapter.

## Existing ownership remains authoritative

The phase does not replace the Phase 4 shape:

- `_ExchangeRecorder.record` is the sole active v2 record owner.
- `ChatTranscript` remains the owner of accepted input, successfully sent
  display specs, and stream attribution.
- `Chat._destructive_history_mutation()` remains the one destructive history
  transaction. Its existing input-block mode remains the only server-side
  destructive admission mechanism.
- `historyTransitionPending` remains the one client lifecycle marker.
- `resubmit()` remains the only branch-producing primitive.
- The existing capture, restore, and rewind registries remain the three
  state-hook registries.

Each Phase 5 behavior maps directly to R2 (resume and client state), R3
(durable failed/cancelled exchanges), R4/R5 (display archive independently of
model state), or R7 (reuse existing primitives).

## P5.0: Q1 decision gate

**Q1 resolved 2026-09-01 and replacement approved 2026-09-02:** select
**disabled-until-restore-decision** for `shinychat#fbhe`, but do not defer
startup work. Preserving a first user submission or app append for later
execution requires exactly the payload, continuation, barrier, or scheduling
machinery this effort excludes.

The product contract is admission, not eventual delivery:

- While Python v2 history selection is unresolved, every browser submission
  path remains disabled and preserves the browser-owned draft and attachments.
  Rejected attempts produce no optimistic `INPUT_SENT`, transport dispatch,
  draft clearing, or attachment clearing. A direct or forged submission that
  nevertheless reaches the server is rejected before transcript, recorder,
  turns, active-ID, or store mutation and is not retained for later execution.
  After the authoritative `history_update`, the preserved draft remains
  available for an ordinary submission.
- Capture-eligible complete appends and root-stream starts attempted while
  selection is unresolved are suppressed. They are not displayed, captured,
  buffered, delayed, replayed, or assigned provisionally. Their callers do not
  wait for history initialization. The suppression boundary precedes display
  dispatch, transcript/recorder reservation, turn capture, and store mutation;
  it leaves no continuation, task, buffer, or replay obligation that can send
  later.
- Greeting remains the ambient startup-presentation mechanism. The new
  admission guard applies only to user-input admission and app-owned,
  capture-eligible append entry points. It must not be placed at
  `_send_action` or another shared lower-level send path. Restore replay
  remains allowed during initialization through
  `_replay_exchange_display()` -> `Chat._restore_bookmark_message()`, creates
  no new exchange, and is not captured as a new startup append.
- After a no-target result, successful selected-target restore, or approved
  fresh-draft recovery completes its authoritative `history_update`, normal
  appends and submissions are admitted. An append accepted after that point
  but before the first user input is still captured by the root exchange.

This narrows R2/R4 to accepted server work: shinychat durably records every
append it accepts after conversation selection, but does not claim durability
for work attempted while no conversation is authoritative. No reconciliation
or second startup-content model is introduced.

The disposable ambient `_capture_admission` predicate and the committed
one-shot barrier/context adapter are **DELETE/REPLACE**. Remove the shared
barrier, its waiters/outcome, browser-token reactive-context probing, private
`DenialContext` import, generic `RuntimeError` classification, and tests whose
only purpose is delayed startup delivery. No Py Shiny
`reactive.can_read_reactive_sources()` API is required.

Deprecated `Chat(messages=...)` is not removed by P5.0. Its initialization
effect is subject to the same unresolved-v2 suppression contract, so it does
not create a compatibility exception or delayed path. `shinychat#mcbp` owns
removal of that argument and its startup-seeding machinery after the Python
core is shape-stable. That task also decides whether
`chat_ui(messages=...)` and `Chat.ui(messages=...)` belong in the same
compatibility change, and owns migration guidance and release compatibility.
Historical predecessor tasks `shinychat#1wmb` and `shinychat#yx3c` are not
current specifications.

Server-side startup-append suppression applies only to Python v2 chats with
history enabled. Python v1 and history-disabled Python retain their existing
constructor-message and append behavior; their only new behavior is the brief
conservative client-seed withdrawal documented below. R emits no seed, adds no
server guard, and remains unchanged.

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
transport dispatch. The server independently rejects premature input without
retaining it.

### Superseded Q1 evidence

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

This evidence established the browser gate and exposed the cost of delayed
startup delivery. The barrier and browser-token context adapter are historical
evidence only and are superseded by the admission contract above. Do not
retain deferred submission or invent another scheduling mechanism.

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
for initial restore; the pre-`history_update` Python-v2 client gate; a
suppressed complete append absent from display and history; a suppressed root
stream with no later continuation; a post-`history_update`, pre-first-input
append captured in the root node; direct/forged early input with no mutation;
restore replay before client release; immediate v1/history-disabled
withdrawal and unchanged append behavior; unchanged R admission;
clear/switch/abort; effective-suffix degradation; and restored-error
catalogue/legacy-fallback states; JS
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
the three hook registries counted as one extension surface. The rejected
`ChatHistory` initialization barrier and reactive-context adapter must be
deleted in P5.0. The final pass must confirm that no delayed startup-delivery
mechanism remains.

## Current handoff

### Superseded history

Earlier Phase 5 work implemented a one-shot initialization barrier, then found
three review findings and a post-valve private Py Shiny context-adapter
problem. Those experiments and their test results are historical evidence
only. Garrick resolved the escalation on 2026-09-02 by replacing delayed
startup delivery with admission suppression.

### Current replacement handoff

Decision: Garrick selected **DELETE/REPLACE** for delayed startup delivery.
Keep the static client seed and submission guards. Delete the one-shot barrier
and context adapter. Suppress capture-eligible startup appends and reject
premature server input until authoritative initialization completes. No
Py Shiny API change is required.

Final plan self-review scored 100/100 (25/25 each for clarity,
comprehensiveness, feasibility, and consistency) with no remaining
deficiencies.

Readiness decision (2026-09-02): relocate the existing `_init_history`
closure-local `initialized` fact to private `ChatHistory` state. It flips only
after the authoritative initial `history_update` send completes and is checked
synchronously at complete-append, root-stream-start, and user-input admission.
`HistoryController.partition` is not a proxy because it is set before target
selection and publication. This is the same initialization fact made
accessible to its three consumers, not a barrier, awaitable, callback,
payload holder, queue, client marker, second owner, or generic admission
adapter. It must not grow any of those responsibilities.

P5.0 implementation landed in `631c97e9` and correction `0e019a61`.
The private readiness fact now suppresses unresolved v2 complete appends,
public streams, and root `message_stream_context()` streams without a task,
continuation, display, transcript, recorder, or store mutation; post-update
pre-input appends remain root-captured. The barrier/context adapter is gone.
Focused history tests, R history hooks (22), and the final `make py-check`
are green (209 Playwright, 916 Python, 1 existing skip). Roborev 1176 found
the root-context gap; `0e019a61` fixes it with regression coverage. Roborev
1177's proposed restored-outcome constructor suppression is declined: it
would add prohibited outcome state and conflicts with P5.0's admitted
post-update pre-input append contract. `shinychat#bj1n` and later children
remained blocked during the correction review.

Independent review then raised three findings against readiness admission plus
one client-route finding, firing the replacement mechanism's three-findings
valve. Decision: **PATCH**. The readiness fact remains necessary and has no
scheduling or ownership behavior to replace. Fix the invariant so readiness
cannot become true unless an authoritative `history_update` send succeeds;
if that send raises, readiness remains false and no client release is claimed.
Add a post-update `append_message_stream()` root-capture regression and a
successful bookmark-pointer suppression/admission boundary test. Make
slash-command dispatch perform the same live admission recheck as normal
submission. Delete/replace would remove the only truthful publication fact
without simplifying the shape. The corrections remained blocking until they
passed review.

Correction evidence (2026-09-02): the client-route fix landed in `175ea3ba`
with generated assets in `c4124a8b`; Roborev 1178 found no issues. Python
readiness correction `83869e5f` preserves the original restore/cancellation
outcome, records a failed cleanup publication as incomplete, and leaves
readiness false unless that cleanup's authoritative `history_update` returns.
Test correction `aec34c8d` proves the public post-update stream is stored in
the inputless root node and that the bookmark boundary restores `c_target` at
`n_0000` before admitting the append. Python evidence: focused readiness and
bookmark tests 9 passed, controller/history suite 305 passed, full
history/transcript gate 52 Playwright plus 541 Python passed, the final
history module run 83 passed, and format/Pyright passed with 0 errors. The
focused `make py-check-tests` invocation is not a unit-test selector in this
repository and exits after deselecting all browser tests; direct `uv run
pytest pkg-py/tests/test_chat_history.py` supplied the focused unit evidence.
Roborev 1179's claimed Ruff E306 failure was declined after the repository
formatter passed; Roborev 1180 found no issues. Independent re-review passed
after `aec34c8d`.

Final integrated verification passed at `e7a6d2cf`: `make py-check` ran 209
Playwright and 918 Python tests with one existing skip; JS lint and 1,262
tests passed with 23 skips; R history hooks passed 22 tests; and `js/dist`
bundle/map assets are byte-identical to both package copies. The only ordinary
diff-check reports are established whitespace in generated minified bundles;
the source/non-generated diff check passes. At verification, no tracked
implementation changes remained; this paragraph is the documentation-only
evidence update.

P5.0 closure (2026-09-02): Garrick accepted the completed Roborev and
independent review evidence as the required human review. `shinychat#fbhe` is
complete. P5.1 `shinychat#bj1n` is the next sequential task and must preserve
the finalized synchronous readiness/suppression contract; the deleted
initialization barrier is historical and must not return.

Boundary: `Chat(messages=...)` removal is follow-up `shinychat#mcbp`, not P5.0.
Do not begin R, legacy, degradation/error-affordance work, or another
scheduling/ownership mechanism.

### P5.1 entry audit (2026-09-02)

`shinychat#bj1n` is claimed. The entry baseline is green: the focused
history/transcript gate passed 593 tests, the transition/edit browser
selection passed 15 tests, and format and Pyright passed with no tracked
changes.

The row-by-row production-path audit accepts existing discriminating evidence
for inactive delete and failed-target preflight, explicit node-close catch-up,
and older-stream attribution. Session teardown uses the contract already
approved above: retain only display and state persisted before teardown, leave
an open stream pending unless terminal state was already recorded, and add no
synthetic settlement, sweep, queue, or discard behavior. This is a recorded
R3/R4 disposition, not a new mechanism decision.

Three bounded evidence units remain, in order:

1. a v2 generic-clear keystone covering one terminal drain, active-stream
   no-mutation, and ownership of a tail accepted after the clear send begins;
2. a compact controller matrix joining stream error/cancellation before and
   after sent chunks with durable display, status, verbatim turns, original
   outcome, and switch error release; and
3. production transition evidence that active New/Delete error and
   cancellation release only their matching existing client marker.

No production defect is established by the entry audit. Later Phase 5
implementation remains blocked.

The clear keystone landed in `5d37f77c` and bounded follow-up `a70a5c4d`.
Its three production-path cases pass, but Roborev 1181/1182 identified three
recurring wait/cleanup defects in the held-clear test tasks. The escalation
decision is **DELETE/REPLACE the duplicated test cleanup only**: use one
bounded, failure-aware helper for task completion and cancellation. The
production clear lifecycle and its assertions remain unchanged; this decision
adds no runtime mechanism or scope.

The replacement converged in `78285ea8` with unrelated formatter churn removed
by `beacbbdb`; Roborev 1183 passed the complete clear slice with no findings.
The compact stream/switch matrix landed in `7e1e1444`: it covers error and
cancellation before and after a sent chunk, verbatim committed turns, original
outcome identity, and switch admission release after error. Its current
exception-text assertion is expected to change under P5.3's already-approved
safe-catalogue write boundary; it is not a P5.1 error-detail contract.

The attempted active New/Delete browser error/cancellation matrix produced
red evidence only because the fixture's release input is serialized behind the
awaited handler and its error event recorder ran after the injected throw.
No production defect is established. Accept the existing production handler
matrix for New/Delete success, error, and cancellation together with the
client store's exact-match/stale-completion tests. Deterministic browser
provenance remains backlog `shinychat#n5d3`; P5.1 adds no synchronization or
runtime mechanism for it.

P5.1 closure (2026-09-02): Roborev 1184's sole persistence-discrimination
finding was fixed in `1435e4ff` by replacing an aliasing in-memory test store
with a deep-copying snapshot store. Roborev 1186 passed the complete amended
task range with no findings. The final full gate before that test-only
correction passed 209 Playwright and 927 Python tests with one existing skip;
the corrected matrix passed all four cases, the full controller module passed
227 tests, and format, Pyright, and diff checks passed. Every P5.1 row now has
discriminating evidence or the requirement-grounded disposition recorded
above. `shinychat#yebr` is next; later Phase 5 children remain blocked.

### P5.2 retry degradation escalation (2026-09-02)

The degradation keystone landed in `eca9d5a7` and its first retry correction
in `d65710af`. Focused tests and the history/transcript gate were green, but
review found two further defects in the same retry/degradation mechanism:
when only the failed target has an incompatible entry, parent-prefix preflight
reapplies stored parent turns over the advertised live baseline, and
node-close capture rewrites the incompatible failed target before branching.
Together with the first retry finding, the three-findings valve fires.

Decision: **DELETE/REPLACE the narrow parent-prefix degradation rule.** Before
any retry mutation, classify the current active restored path using the same
private effective-suffix compatibility logic as restore. If that active path
is degraded:

1. do not run node-close capture on the immutable failed target;
2. prepare the parent rewind so the turns hook preserves the current attached
   live baseline and resets its capture baseline without applying stored
   parent turns; and
3. continue to run every non-turn rewind hook against the ordinary parent
   prefix before creating the sibling.

The classification is recomputed from the current record and path. It is not
stored lifecycle state, a new hook contract, owner, queue, reconciliation
mechanism, or inferred turn sequence. Compatible retries retain the existing
parent-prefix rewind and catch-up behavior. Required regressions cover an
incompatible target over a compatible parent in recorded and live bootstrap,
target immutability, retained live baseline, non-turn rewind execution, and
unchanged compatible retry behavior.

Plan self-review: 100/100 (clarity 25, comprehensiveness 25, feasibility 25,
consistency 25). No deficiencies remain: the replacement names its
pre-mutation input, exact turn and non-turn behavior, compatibility fallback,
tests, and prohibited mechanisms.

The replacement landed in `a823c745`. One additional effective-suffix case is
resolved in `8071eae9`: when a compatible target snapshot supersedes an
incompatible parent, restore remains ordinary because the parent entry is
irrelevant. Retry removes that target snapshot, making the incompatible parent
effective. It must reject before mutation. Preserving current live turns would
retain the abandoned target's context, while applying or reconstructing the
parent is prohibited. The rejection leaves record, display, turns, capture,
and persistence untouched. This is a narrow retry preflight outcome, not a
new corruption class or degradation mode.

Decision self-review remains 100/100: the superseded-entry rule and retry
transition now cover both possible effective suffixes without inferred turns,
target mutation, or new state.

P5.2 review found two valid PATCH items in the replacement. First, active-path
classification must run strict envelope and turn-data validation before
compatibility classification so malformed target state cannot enter
degradation. Second, classification belongs inside the shared `resubmit()`
primitive, not only `retry()`, so retry, edit, and regenerate all preserve a
degraded live baseline and immutable target consistently. The complete order
is: validate the active path; classify its effective turn suffix; preflight the
parent prefix; then mutate. Structurally valid incompatibility may degrade;
malformed state still fails closed before capture or mutation.

Self-review: 100/100 (25/25 each). The patch reuses the one branch primitive,
closes every resubmit entry point, preserves strict/degraded classification,
and adds no state, hook, owner, or lifecycle behavior.

P5.2 resubmit hardening landed in `a252e9ac`: `resubmit()` now validates every
active-path envelope and turn payload before classifying the effective turn
suffix. Retry, edit, and regenerate consequently share immutable degraded
target handling, retained live baseline, reset capture baseline, and ordinary
non-turn parent rewind; compatible paths and the pre-mutation
incompatible-parent rejection remain unchanged. Focused and full controller
and chat-history tests, the history/transcript gate, format, Pyright, and diff
checks passed. Independent review found no defects; no further P5.2 mechanism
decision is pending.

Roborev 1191 found the third issue against the replacement: a degraded restore
reset the ordinary turn baseline, so a later continuation wrote a delta behind
the still-incompatible snapshot and degraded again on reload. Valve decision:
**PATCH through the existing snapshot fallback.** After degraded restore
hooks apply, invalidate the recorder's existing turn fingerprint baseline;
the next ordinary capture must therefore write a compatible snapshot that
supersedes the incompatible suffix. Rewind uses its separate execution path,
so degraded retry/edit/regenerate retains its valid live baseline and does not
rewrite the shared parent. Add a continue -> capture -> reload regression.
No persistent degraded flag, new capture mode, or lifecycle state is added.

Self-review: 100/100. The patch is requirement-traced to R2, uses the
already-designed snapshot escape hatch, distinguishes restore from rewind,
and closes cross-session continuation without changing branch ownership.

The snapshot correction landed in `32a2828b`. A degraded restore now
invalidates the existing in-memory turn fingerprint only after restore hooks
finish, so the next ordinary capture takes the existing snapshot fallback.
The persisted FileConversationStore regression proves a compatible continuation
supersedes the incompatible suffix and reloads without warning; rewind and
degraded retry/edit/regenerate baseline behavior remain unchanged. Focused and
full controller/chat-history tests, the history/transcript gate, format,
Pyright, and diff checks passed. Independent review found no defects.

Roborev 1192 invalidated the final sentence above for degraded resubmit.
Preserving the live baseline across rewind still lets the later accepted-input
callback capture on the shared parent before opening its sibling. A delta can
therefore merge with stale parent turn state; forcing a snapshot there would
instead overwrite the old branch's inherited context. The failed target and
shared parent's payload and state must remain unchanged. Creating the sibling
may update only required graph metadata (`children`, `selected_child`, and the
active pointer).

Valve decision: **DELETE/REPLACE the degraded-resubmit continuation path.**
Compatible resubmit keeps the Phase 4 capture-parent-then-open-sibling order.
Only after `resubmit()` has strictly classified a degraded active path and
preflighted the parent prefix, it server-accepts the already validated
retry/edit/regenerate input in the same call. The private recorder path:

1. applies the preflighted non-turn rewind hooks before graph mutation;
2. opens the new sibling under the parent without capturing parent turn state;
3. invalidates the turn fingerprint and captures a full compatible snapshot
   from the preserved live adapter turns on that sibling; and
4. persists through the existing recorder owner and accepted-input path.

The browser receives a private render-only projection of that accepted input
and must not issue the ordinary duplicate input send. This is a stack-local
handoff, not deferred lifecycle state: no directive survives `resubmit()`, and
no field, request correlation, timeout, queue, owner, schema, or public hook is
added. Validation and rewind-hook failures occur before sibling creation;
post-accept transcript or persistence failures remain visible and propagate
without invented rollback.

Regressions cover retry/edit/regenerate in recorded and live bootstrap with a
persisted store. They assert unchanged failed-target and parent payload/state,
only required parent graph-edge changes, a first full compatible snapshot on
the new sibling, reload without degradation, no duplicate browser input, and
unchanged compatible resubmit ordering.

Self-review: 100/100 (clarity 25, comprehensiveness 25, feasibility 25,
consistency 25). No deficiencies remain. The replacement preserves retry
eligibility and branch payload/state while isolating the ordering exception to
the already-classified degraded call; rejected alternatives required hidden
cross-request lifecycle state.

### P5.2 replacement handoff (2026-09-02)

The approved replacement landed in `cb7358f5`, with generated assets in
`28dad6ae`. Degraded retry, edit, and regenerate now run only preflighted
non-turn rewind hooks, server-accept the validated input into a new sibling,
and persist a full live-turn snapshot without mutating the failed target or
shared parent payload/state. The browser renders that accepted input without a
second input send; compatible resubmit ordering is unchanged.

Focused controller and JS history tests, full controller/history/transcript
tests, JS lint/test, `make update-dist`, Pyright, source diff checks, and the
full `make py-check` gate passed (209 Playwright; 940 Python, 1 existing skip).

Independent review then raised three findings against the landed replacement,
firing the escalation valve. Decision: **PATCH**. The same-call sibling
mechanism remains coherent; the defects are admission and publication ordering,
not a second ownership or lifecycle problem.

Once the degraded sibling and its compatible live-turn snapshot are durable,
send the private render-only projection before publishing the accepted-input
signal. Publication runs exactly once in a `finally`: success orders provider
work after projection enqueue; projection failure still publishes the durable
accepted input, then propagates the original exception through the transition
wrapper. This avoids both assistant-before-projection truncation and a durable
pending sibling with no provider execution. There is no post-accept rollback
or fresh-draft recovery.

`resubmit()` is the sole retry/edit/regenerate admission boundary. Before
classification, transcript mutation, or persistence it requires an initialized
partition and an input-bearing target on the current active path; ancestors are
valid targets. Retry permits pending/error/cancelled, regenerate requires ok,
and edit permits any input-bearing active-path node. The accepted-resubmit
helper may not silently return after mutation.

Self-review: 100/100 (clarity 25, comprehensiveness 25, feasibility 25,
consistency 25). No deficiencies remain. The patch names exact ordering,
failure behavior, admission rules, and the pre-mutation partition boundary
without changing compatible resubmit behavior or adding state.

### P5.2 degraded-resubmit PATCH handoff (2026-09-02)

The P5.2 **PATCH** is complete in `f4d906f3`, `19b5703a`, `051a9e00`, and
`b096715a`. Production now projects the durable degraded sibling before
exactly-one publication and preserves projection failure with publication
failure chained. Evidence covers projection-only failure, both failure, and
publication-only failure with the sibling persisted. Focused/full controller
tests, format, Pyright, diff, and independent closing review are green with
no findings. No new decision was required.

Task review 1193 proposed making degraded-warning delivery best-effort. This
finding is declined because it conflicts with the approved P5.2 boundary:
restore-send failures remain fail-closed through fresh-draft recovery, and
the warning is part of successful degraded restore before authoritative gate
release. A failed warning send therefore remains a restore transport failure;
it must not silently publish a display-restored state that omitted its required
model-context warning.

### P5.3 implementation handoff (2026-09-02)

Python catalogue selection, normalization, persistence, and ephemeral error
projection landed in `a89b035c`. Plain-text React rendering adjacent to Retry
landed in `9b7a2a97`; shared Python/R assets were rebuilt in `645f35d0`.
Focused Python and JS tests, full Python tests (960 passed, one existing skip),
Ruff, Pyright, JS lint, format, and worktree diff checks passed. Task-level
Roborev review remains before closure.

Self-review: 100/100. The implementation handoff records landed scope and
verification without changing the settled P5.3 mechanism or acceptance
boundary.

Roborev 1194 found and the branch fixed two P5.3 defects: successful stream
completion now preserves `error=None`, and restored error detail uses a
normal-flow wrapping footer rather than the absolute single-control layout.
Roborev 1195 then found the third P5.3 issue, firing the escalation valve.

Valve decision: **PATCH**. The closed catalogue and projection mechanism remain
coherent. The alternate `append_message_stream()` root-start path must classify
a failure from its initial `chunk="start"` call as
`HISTORY_ERROR_STREAM_START`, matching `message_stream_context()`. Failures
after start succeeds, including generator and later chunk failures, remain
generic unless they are the already-classified terminal send outcome. Add a
production-path regression that discriminates initial-start failure from a
later stream failure.

Self-review: 100/100 (clarity 25, comprehensiveness 25, feasibility 25,
consistency 25). No deficiencies remain. This is a bounded missing outcome in
an existing core path, not a catalogue, schema, or ownership replacement.

The valve patch landed in `e4d1b822`; normal completion remains error-free,
the alternate root-start path now persists the start catalogue literal, and
later failures retain their existing generic/terminal classification. Final
task review 1196 found no issues. Full Python tests pass (961 passed, one
existing skip), full JS tests pass (1,272 passed, 23 skipped), and Ruff,
format, Pyright, JS lint, asset distribution, and diff checks are green.
P5.3 is complete.

### P5.4 adversarial review

The required single adversarial pass found one blocking readiness gap.
Restored Retry, Edit, and sibling-navigation controls could dispatch while the
initial v2 selection was unresolved, and their private server action handlers
did not independently reject forged arrivals before mutation.

Decision: **PATCH through the existing readiness fact and client predicate.**
Branch-action eligibility and message-control disabling must include the
existing v2-only `isHistorySubmissionBlocked()` result. The private Python
Edit, Navigate, and Resubmit action handlers must reject unresolved v2
initialization before controller mutation. V1, history-disabled, and R behavior
remain unchanged because they do not enter the seeded completion-v2 unresolved
state. Add a held-`history_update` browser regression for all three controls and
a forged server-action regression proving no transcript, record, turns,
active-ID, or store mutation.

Self-review: 100/100 (clarity 25, comprehensiveness 25, feasibility 25,
consistency 25). No deficiency remains: the fix reuses both existing readiness
representations, covers UI and forged admission, and adds no marker, owner,
queue, timer, or public API.

P5.4 landed in `70dcdc7f`, `f91d4db7`, and `5647605d`.
Next state: P5.4 repair complete and ready to proceed.
Verification caveat: raw `git diff --check` across the `f91` asset refresh flags a pre-existing embedded tab in regenerated minified JS; no generated assets were hand-edited, and the source/test diff is clean.
