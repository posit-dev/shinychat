# Phase 5 mechanism: hard core and adversarial review (Python)

**Status:** Q1 resolved and authorized for P5.0 retained implementation ·
2026-09-01
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
individual cancellation cannot cancel it. Session teardown cancels/releases
all barrier waiters. A post-commit recorder callback is too late. The barrier
never wraps `_send_action`; greeting and bookkeeping remain excluded exactly
as in Phase 3. Restore replay bypasses naturally because its internal replay
path does not enter these admission paths, never because an arbitrary
destructive transaction owner is exempt.

Resolve the barrier only after the no-target/success result or approved
fresh-draft cleanup **and** the authoritative `history_update`. A live-session
error or cancellation completes cleanup and that update before releasing
waiters; teardown cancellation ends the barrier without a client release.
This preserves the existing fresh-draft failure contract and gives the client
one authoritative release path.

Manual startup `chat.append_*()` calls wait at the relevant reservation and
then execute after either live decision. Deprecated `Chat(messages=...)`
observes the one-shot result: it runs for no-target/fresh-draft and is
suppressed after successful target restore, preserving its previous
no-duplicate behavior. Python v1 and history-disabled modes create no server
barrier; their existing first `history_update` withdraws the conservative
client seed, with the authorized brief initial delay. R creates no seed or
barrier and remains unchanged.

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
P5.0 must add the remaining initial-only catch for recorded
`_prepare_exchange_restore()` failures at the three `_init_history` restore
call sites: bookmark pointer (`_history.py:2487`), bookmark conversation
(`_history.py:2502`), and browser/URL target (`_history.py:2541`). Each
ordinary preflight failure must use `_clear_failed_restore()`, publish its
single authoritative release update, and settle initialization false; a
cancellation must propagate unchanged. Do not move this catch into the
shared preflight helper or the general restore method. Switch preflight
remains unchanged: it retains the Phase 4 no-target-mutation behavior.

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

Do not create Phase 5 implementation children until this note is approved.
After approval, create sequential children under `shinychat#fg70`:

1. **P5.0 selected init guard (`shinychat#fbhe`).** It is the entry slice and
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
must not land.

Next: after self-review, `shinychat#fbhe` may replace the rejected predicate
with the selected one-shot `ChatHistory` barrier and add the bounded initial
recorded-preflight recovery. P5.1-P5.4 remain blocked by P5.0. Do not begin R,
legacy, or another scheduling/ownership mechanism.
