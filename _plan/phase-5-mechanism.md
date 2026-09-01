# Phase 5 mechanism: hard core and adversarial review (Python)

**Status:** authorized gate corrections incorporated; pending final self-review
and driver sign-off · 2026-09-01
**Phase:** plan.md §4, Phase 5
**Kata:** parent `shinychat#fg70` under epic `shinychat#6d0d`
**Context:** `phase-4-mechanism.md` is completed context only. This note is
the Phase 5 gate and the only phase-local mechanism reference for new work.

## Objective and boundary

Bring the Python v2 exchange-tree path to shape-stability at the remaining
hard boundaries:

1. resolve Q1 with a small production-shaped prototype and install the
   selected init/restore-window guard;
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
work.

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

The Phase 3 no-op while `HistoryController.partition is None` is deliberate
only until Phase 5. It avoids failing an originating send before history
selection, but it does not make that send durable. `partition` is assigned
before target lookup and restore, so it is not the restore-decision boundary.
Decision completion means either a successful selected-target restore or an
approved fresh-draft recovery, in both cases followed by required metadata
completion. Capture-eligible work remains closed until that completion even
when `partition` is non-null.

The selected server gate sits before `ChatTranscript.record_accepted_input`,
before complete-append reservation, and before root-stream reservation; a
post-commit recorder callback is too late. It never gates the generic
`_send_action` wire choke point. Restore replay bypasses the gate only within
the existing destructive-history transaction; greeting and bookkeeping remain
excluded exactly as in Phase 3. The gate releases on every initialization
success, handled error, and cancellation.

Current code has no `HistoryStore` seed API: the store starts with
`initialized == false` and no protocol, and `updateHistory()` is currently the
only protocol input. Therefore P5.0 must prove and name a private,
initialization-only delivery path for static Python-v2
`completion-v2` capability/protocol configuration before the first runtime
`history_update`; it must not assume that the existing store can already be
seeded. This configuration input may not be persisted or exposed as a public
API, owner, provenance field, lifecycle marker, completion signal, release
action, or second client marker. If the production path cannot deliver this
configuration without one of those additions, stop for a plan amendment.
Once delivered, the client reuses that capability with the existing
`HistoryStore.initialized` state and `submissionBlocked` input surface: a
seeded v2 client remains blocked while `initialized` is false or the existing
transition marker is pending. The initial runtime `history_update` remains the
authoritative decision-completion publication; an update that withdraws
capability replaces the seed and clears pending state under the existing Phase
4 protocol-change rule. History-disabled chats, Python v1, and R emit no
Python-v2 seed and retain their current admission behavior.

The existing ChatInput guards must cover Enter, send-button, attachment-only,
slash-command, suggestion, and imperative submissions while preserving the
uncontrolled draft and staged attachments; the ChatApp `submitUserInput`
handler must recheck the same condition before optimistic `INPUT_SENT` or
transport dispatch. The server admission predicate remains owned by the
existing transcript/history boundary; it is not a second client marker or a
new scheduling owner. A live-session cancellation must complete fresh-draft
cleanup and publish the same release metadata before admitting input;
teardown cancellation may end with no client to release.

Before feature code, implement two disposable, production-shaped demo probes
against the actual Python initialization/restore flow:

1. **Disabled-until-decision:** block user dispatch in the existing input
   surface and hold capture-eligible server emission at the existing history
   boundary until restore decision completion.
2. **Defer-one-submission:** a production feasibility/rejection probe that
   attempts to let only the first racing user submission reach the existing
   accepted-input path after decision completion, while independently
   preventing capture-eligible server emission.

The probes must measure restore-decision latency and prove the same cases:
recorded and live bootstrap, no saved target, successful restore, malformed
target failure, cancellation, a seeded browser draft, a first raw input, and
a complete and streaming initial append. They must use the production
transcript/recorder paths and leave no retained prototype code.

The probes must establish whether disabled-until-decision is viable in the
actual production paths. Defer-one-submission is not an eligible retained
mechanism if it requires any holder, payload field, release action, marker,
continuation, or queue. It exists only to reject or demonstrate that boundary;
it cannot authorize a third mechanism. Select disabled-until-decision only
after the required evidence is recorded here and in Kata.

The selected guard must:

- create no durable preselection record, recorder buffer, or merge state;
- admit no capture-eligible event before restore decision completion;
- preserve the browser draft/attachments without synthetic rollback;
- release on success, handled failure, and cancellation; and
- compose with the existing `completion-v2` marker rather than introducing
  another marker.

If disabled-until-decision cannot meet the constraints, stop for a plan
amendment; do not retain a deferred submission or invent a third scheduling
mechanism.

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

Do not create Phase 5 implementation children until this note is approved.
After approval, create sequential children under `shinychat#fg70`:

1. **P5.0 Q1 prototype and selected init guard.** It is the entry slice and
   must land before the audit hardening.
2. **P5.1 lifecycle audit.** Exercise clear/switch/abort against the selected
   guard and existing transaction boundaries.
3. **P5.2 unsupported-turn degradation.** Keep strict corruption behavior
   separate from effective-suffix compatibility degradation.
4. **P5.3 detailed error reload affordance.** Add only the bounded
   input-bearing error projection and its plain-text React rendering; run
   `make update-dist` if JS/SCSS changes.
5. **P5.4 acceptance, deletion pass, and adversarial review.** Review the
   coherent Phase 5 subsystem in critical-review format. Every P1 is fixed
   with a regression or dispositioned in Kata before closure.

Each child is blocked by its predecessor. A review finding outside R2-R5/R7
receives the standing `real, out of scope -> backlog` disposition.

## Verification

Before P5.0 code, run the current history/transcript focused suite, the
existing transition/browser coverage, format, and Pyright. The prototype
must demonstrate discriminating behavior for both Q1 candidates and is
deleted before implementation.

For implementation, require focused controller and production browser tests
for initial restore, the pre-`history_update` Python-v2 gate and unaffected
history-disabled/v1/R admission, clear/switch/abort, effective-suffix
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
the three hook registries counted as one extension surface. The selected Q1
guard may reuse one of these, but may not become an additional owner or
ordering subsystem. The final pass must name any retained guard and show its
requirement trace, or delete it.

## Current handoff

Landed: Phase 5 parent `shinychat#fg70` is created and claimed on
`feat/history-exchange-tree`; authorized gate corrections are incorporated in
this note. This note and the Phase 5 reference in `plan.md` remain planning
artifacts pending final self-review and driver sign-off.

Next: complete final self-review and driver sign-off. After approval, create
and claim only P5.0, run the required green baseline, and compare the two Q1
probes.

Provisional decision: Q1 is intentionally unresolved pending the required
prototype evidence. Implementation remains unstarted: no Phase 5 feature
code, child task, R port, legacy work, or new scheduling/ownership mechanism
has started.
