# Phase 5 mechanism: hard core and adversarial review (Python)

**Status:** proposed for driver sign-off · 2026-09-01
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
selection, but it does not make that send durable. Phase 5 must prevent every
capture-eligible initial action until selection has resolved: accepted user
input, complete appends, stream start/update/finish, and input-less appends.
Greeting and bookkeeping actions remain excluded exactly as in Phase 3.

Before feature code, implement two disposable, production-shaped demo probes
against the actual Python initialization/restore flow:

1. **Disabled-until-decision:** block user dispatch in the existing input
   surface and hold capture-eligible server emission at the existing history
   boundary until partition selection completes.
2. **Defer-one-submission:** let only the first racing user submission reach
   a single deferred continuation after selection, while independently
   preventing capture-eligible server emission.

The probes must measure restore-decision latency and prove the same cases:
recorded and live bootstrap, no saved target, successful restore, malformed
target failure, cancellation, a seeded browser draft, a first raw input, and
a complete and streaming initial append. They must use the production
transcript/recorder paths and leave no retained prototype code.

Choose the smallest candidate that:

- creates no durable preselection record, recorder buffer, or merge state;
- admits no capture-eligible event into a `partition is None` window;
- preserves the browser draft/attachments without synthetic rollback;
- releases on success, handled failure, and cancellation; and
- composes with the existing `completion-v2` marker rather than introducing
  another marker.

The expected preference is disabled-until-decision because it avoids deferred
submission state. The deferred candidate may retain only the browser-owned
original raw input long enough to re-enter the existing accepted-input path
after selection; it may not add a history-owned payload, record, or queue.
It is not selected until the evidence is recorded here and in Kata. If neither
candidate meets the constraints, stop for a plan amendment; do not invent a
third scheduling mechanism.

## P5.1: Clear, switch, and abort audit

The audit is an evidence matrix, not a new lifecycle subsystem. For each item
below, add a production-path regression or record a requirement-grounded
disposition on `shinychat#fg70`:

| Boundary | Required outcome |
|---|---|
| Generic clear with no active stream | Drain existing terminal settlement exactly once before mutation; no recorder consumer is invented. |
| Generic clear with active stream | Reject before display, recorder, turns, active ID, or store mutation. |
| Switch/new/active delete | Preserve the Phase 4 destructive boundary and fail-to-fresh-draft outcome; input blocking releases on success, error, and cancellation. |
| Inactive delete and failed target preflight | Retain existing no-target-mutation behavior; do not expand the active-transition protocol. |
| Stream cancellation/error before and after sent chunks | Persist every sent message, record the terminal status and verbatim committed turns, and preserve the original cancellation/error through capture cleanup. |
| Session teardown/abort while a stream is open | Preserve only the already committed display and turns; reload classifies the node as pending/interrupted or its recorded terminal state. No synthetic settlement sweep is added. |
| Catch-up at the next user action | Capture only through the existing explicit exchange/node-close path; an older stream retains its opening exchange attribution. |

The audit must not change abort to discard-on-reload. A failed or cancelled
node stays immutable; retry continues to rewind to its parent and create a
sibling through `resubmit()`.

## P5.2: Unsupported-turn degradation

Phase 4 remains strict for invalid graph structure, unknown state keys,
malformed state envelopes, invalid modes, and restore transport/persistence
errors. Phase 5 narrows degradation to a classified failure while materializing
the registered `shinychat:turns` entry: an otherwise valid stored entry cannot
be replayed because its known kind/version or serialized provider content is
unsupported by the current provider integration.

The turns restore hook must report that classified condition to the controller
without mutating the stored record. The controller:

1. completes normal graph validation and display replay;
2. leaves the displayed exchange path and its retry eligibility intact;
3. does not call `set_turns` with a partial, guessed, or reconstructed turn
   sequence; and
4. sends one bounded visible warning that model context could not be restored.

The resulting state is explicitly **display-restored, model-context-unavailable**.
The warning must tell the user that continuing starts from the app's live
client state, not from an inferred historical context. In recorded-bootstrap
mode, that means the empty/app-initialized client state after restore entry;
in live-bootstrap mode, it is the app's live initialized prefix. It may not
expose raw provider payloads or stack traces. A later valid turns snapshot
still follows the existing materialization contract; Phase 5 does not invent
selective state-entry skipping for arbitrary hooks.

Tests distinguish classified unsupported turn content from corruption:
unsupported version/content preserves display and warns; malformed entry,
unknown state key, graph invalidity, and restore-send failure remain
fail-closed through the approved fresh-draft recovery.

## P5.3: Detailed error on reload

The v2 schema already stores only `ErrorEntry.message`. On restored
input-bearing `status == "error"` nodes, extend the existing ephemeral
exchange-status projection with that exact bounded message and render it
adjacent to the existing Retry affordance. Pending/interrupted and cancelled
nodes retain their current status/retry behavior and do not receive error
detail.

No new persisted error fields, traceback, provider response, attachment
metadata, or error-derived client state are added. The projection is
ephemeral: it is regenerated from the selected record path, does not mutate
the failed node, and does not affect sibling navigation or `resubmit()`.
Tests cover an errored node with and without partial assistant content,
message escaping/safe rendering, retry immutability, and the absence of
detailed text for pending/cancelled nodes.

## Sequencing and task graph

Do not create Phase 5 implementation children until this note is approved.
After approval, create sequential children under `shinychat#fg70`:

1. **P5.0 Q1 prototype and selected init guard.** It is the entry slice and
   must land before the audit hardening.
2. **P5.1 lifecycle audit.** Exercise clear/switch/abort against the selected
   guard and existing transaction boundaries.
3. **P5.2 degradation and detailed error reload affordance.** Keep strict
   corruption behavior separate from compatibility degradation; run
   `make update-dist` if JS/SCSS changes.
4. **P5.3 acceptance, deletion pass, and adversarial review.** Review the
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
for initial restore, clear/switch/abort, degradation, and restored-error
states; JS lint/test/build and `make update-dist` when client code changes;
the R shared-client hook check for shared bundle compatibility; and the full
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
`feat/history-exchange-tree`; this note and the Phase 5 reference in
`plan.md` are proposed planning artifacts only.

Next: driver review of this mechanism note. After approval, create and claim
only P5.0, run the required green baseline, and compare the two Q1 probes.

Provisional decision: Q1 is intentionally unresolved pending the required
prototype evidence. No Phase 5 feature code, child task, R port, legacy work,
or new scheduling/ownership mechanism has started.
