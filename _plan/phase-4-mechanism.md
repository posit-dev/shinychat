# Phase 4 mechanism: restore, branching, and bookmark pointer (Python)

**Status (current and authoritative):** P4.0 through P4.4 are complete.
Restore/continuation, branching/edit/navigation, retry/regenerate, and
pointer-only bookmarks are implemented, verified, reviewed, and closed in
Kata. P4.5 final acceptance and deletion review is active on
`shinychat#pvjx`; one bounded partial-display retry evidence correction is
pending. `shinychat#azvt` remains open and attention-blocked during that
correction (2026-09-01).
**Phase:** plan.md §4, Phase 4
**Kata (current):** `shinychat#ykxh`, `shinychat#5r50`,
`shinychat#6drf`, `shinychat#72ee`, and `shinychat#g6tt` are closed.
`shinychat#pvjx` is claimed with `work.attention="blocked"` under open parent
`shinychat#azvt` and epic `shinychat#6d0d`.
**Context:** `phase-3-mechanism.md` is closed historical context. This note is
the Phase 4 gate and the only phase-local mechanism reference for new work.

## Objective and boundary

Complete the Python v2 path from a stored exchange tree to a usable resumed
conversation: restore the active path's display and client state, continue
from that state, navigate existing branches, and create edit/retry/regenerate
siblings through one primitive. A Shiny bookmark contributes only a
`{conversation_id, node_id}` pointer into the server-side record.

Phase 4 does not add the init-window admission guard, unreplayable-turn
degradation, or the clear/switch/abort hard-core audit (Phase 5); R parity
(Phase 6); or v1 import, public-hook migration, and deprecations (Phase 7).
It adds no queue, cursor, reconciliation pass, rendered-HTML storage, CAS, or
second record owner.

## Entry integration gate (complete)

`shinychat#ykxh` completed in merge commit
`e27e7278981e061864cc1fdf81d5c7c6fa5d3ca8`, which merged `origin/main`
`2b249764` into this branch. The current-head integration re-derived the
historical conflict recipe and settled record creation, activation, new-chat,
deletion, URL restore, bookmark restore, lifecycle, and OTel paths before the
restore keystone.

The task's 2026-08-28 conflict recipe is historical evidence, not an
executable recipe: both heads advanced and Phase 3 is complete. The current
integration gate `shinychat#ykxh` is closed; do not reopen or re-run that gate
for the restore keystone. Preserve its semantic decisions:

- allocate the stable conversation id before the first v2 root/input capture;
- use that id for `ConversationRecordV2.id`, with no second allocator;
- retain the stale-URL clearing behavior of `new_chat()`;
- leave the overlapping-stream OTel scalar issue dispositioned to its existing
  future owner rather than adding Phase 4 scheduling machinery;
- leave the seeded-draft/init-restore race to the Phase 5 guard and Phase 6 R
  port, as already recorded.

The full Python gate must pass after integration. Only then may the restore
keystone begin; that gate is now satisfied.

Integration decisions and preserved behavior:

- `HistoryController` allocates the stable conversation ID before v2 root,
  input, or input-less record creation. `_ExchangeRecorder` remains the sole
  v2 record owner.
- The existing destructive-mutation wrappers, active-ID paths, stale-URL
  clearing, and v1 first-save adoption remain intact.
- Lifecycle integration keeps reactive effects homogeneous. Response-settlement
  cancellation remains owned by `Chat`/the session.
- OTel scalar overlap and the seeded-draft/init-restore race remain deferred to
  their existing future owners.

## Ownership and path operations

`_ExchangeRecorder` remains the sole v2 record owner. `HistoryController`
orchestrates destructive mutations and wire actions but does not acquire a
second v2 `record` field. Loading or switching installs the validated target
into the recorder only after its display and state consumers have applied
successfully.

Add these graph operations to `ConversationRecordV2`, mirroring the useful v1
tree behavior without carrying over turn/UI reconstruction:

- `children_of(node_id)`, `siblings_of(node_id)`;
- `set_active_leaf(node_id)`, which validates membership and rewrites
  `selected_child` along the selected path;
- `subtree_leaf(node_id)`, which follows remembered `selected_child` pointers
  and otherwise chooses the newest child;
- active-path projection from a displayed user-message index to its exchange.

Input-less nodes remain on replay paths but are not editable, retryable,
regeneratable, or user-visible branch points.

Every pointer mutation runs under the recorder's existing lock, performs the
current leaf's `node_close` catch-up before moving, and atomically persists the
complete record. The lock remains persistence serialization only; transcript
admission and `_destructive_mutation()` continue to reject conflicting live
display operations.

## Restore and rewind hooks

Add internal registries keyed by state-entry name, parallel to capture:

```python
@dataclass(frozen=True)
class StatePathContext:
    conversation_id: str
    active_leaf: str
    node_ids: tuple[str, ...]
    entries: tuple[tuple[str, StateEntry], ...]
    bootstrap: Literal["recorded", "live"]

RestoreHook = Callable[[StatePathContext], Awaitable[None] | None]
RewindHook = Callable[[StatePathContext], Awaitable[None] | None]
```

`entries` contains only that registry key's entries, in active-path order,
paired with the owning node id. Hooks run in registration order. The API stays
private in Phase 4; `shinychat:turns` is registered through both registries so
the generic contract is exercised by the in-tree consumer.

Add `HistoryOptions.restore_bootstrap:
Literal["recorded", "live"] = "recorded"`:

- `recorded` reconstructs state from the active path.
- `live` preserves the app's client turns at restore entry, skips only the
  implicit root node's recorded snapshot, then applies later path entries.
  A later snapshot still replaces the accumulated prefix.

For `shinychat:turns`, scan in path order. A snapshot replaces the accumulated
turn list; a delta appends. The most recent snapshot therefore wins naturally.
Page-load/switch restore uses the configured bootstrap: recorded mode starts
empty, while live mode starts from the client's current serialized turns and
skips the root snapshot. Rewind always uses recorded mode so the abandoned
suffix cannot survive an edit, retry, regenerate, or sibling move. Apply once
with `TurnsAdapter.set_turns_json` and reset the recorder's capture baseline
from the applied result so the next capture can produce a delta. Phase 4 is
strict about malformed or unsupported entries; Phase 5 owns
degrade-with-warning behavior.

Restore hooks run for page load and conversation switch. Rewind hooks run for
sibling navigation and before edit/retry/regenerate submission. The blessed
turns implementation is the same materializer registered in both places;
separate registries preserve the extension contract for state with distinct
restore and rewind behavior.

## Restore transaction

Load and validate the target record and optional target node before mutating
the live chat. Inside the existing destructive-mutation boundary:

1. Choose the target leaf (`record.active_leaf` unless a bookmark supplied a
   validated node) and update its in-memory `selected_child` path.
2. Clear transcript messages and the ambient greeting.
3. Replay each active-path node's `input`, then its captured `messages`,
   through `Chat._restore_bookmark_message`; never trust stored HTML.
4. Execute restore hooks for the same path.
5. Install the target as the recorder's active record and persist a changed
   pointer when the selected node differs from the stored leaf.
6. Send exchange metadata, conversation-list state, active-id navigation, and
   existing app restore callbacks.

The Phase 3 replay helper becomes an internal step of this transaction rather
than a second restore route. A restored `pending` node is interpreted as
interrupted display state; its partial messages remain unchanged.

The keystone slice is one valid v2 record restored through this path, followed
by a real submission whose provider receives the restored turn prefix. The
test asserts both turn content and count, not only rendered text.

## One sibling primitive

Use one controller operation for all branch-producing actions:

```text
resubmit(exchange_id, replacement_input?)
  validate an input-bearing exchange
  normalize and validate the replacement before any pointer mutation
  capture the current leaf's close state
  move active_leaf to exchange.parent_id and persist
  replay that prefix and execute rewind hooks
  submit the validated replacement when supplied; otherwise submit a
    defensive copy of exchange.input
```

- Edit supplies modified text/attachments.
- Retry supplies the failed/cancelled/interrupted exchange's original input.
- Regenerate supplies a successful exchange's original input.

The accepted-input capture callback creates the new sibling eagerly under the
rewound parent. The primitive never mutates or reopens the old exchange and
does not create a provisional node if browser submission fails.

Sibling navigation selects the adjacent sibling, follows its remembered
subtree leaf, persists `active_leaf`/`selected_child`, replays that path, and
executes rewind hooks. State and display always derive from the same selected
path but are never reconciled with each other.

## Q3 and client protocol

The predecessor's nine-test `history_edit` Playwright suite is already present
on this branch except for its final message-id-specific fixture update. Run it
against v2 behavior before changing addressing.

Keep the current positional edit/navigate inputs and positional sibling
metadata unless that suite demonstrates a failure. The v2 server can project a
displayed user-message index to an exchange even when a node has multiple
response messages. Do not import the predecessor's event/message-id protocol:
v2 persists exchange ids, not message ids.

If the suite fails specifically because positional identity is ambiguous, the
only approved Q3 upgrade is to expose the owning exchange id on restored/live
user messages and use that id for edit, navigate, resubmit, and sibling
metadata. Record the red test and amend this note before implementing it.

For retry state, add one ephemeral exchange-metadata action projected onto the
input-bearing user message. It carries status and whether retry is allowed; it
is not persisted client transcript state and does not expose stored error
details. A resubmit input carries the current message index and `retry` or
`regenerate`. The server revalidates status and routes both to the sibling
primitive. This ensures retry remains available when an exchange has no
assistant message. Phase 4 adds no separate regenerate UI; a controller-level
production-path regression invokes `regenerate` and proves it uses the same
primitive. Phase 5 owns detailed error-on-reload presentation and
degrade-with-warning behavior.

Any TypeScript/SCSS change runs `make update-dist`, updating all packaged
assets as required by `AGENTS.md`. The R server implementation still waits for
Phase 6; advancing shared client assets does not constitute the R port.

## Bookmark pointer

For v2, register one Shiny bookmark value under a chat-scoped key:

```json
{"conversation_id": "c_...", "node_id": "n_..."}
```

Capture both values from one recorder snapshot. Restore validates the record
first and then validates that `node_id` belongs to it before entering the
restore transaction. A missing record or node emits the existing visible
history-load notification and leaves a fresh draft; it never partially
switches or silently substitutes another leaf.

`bookmark_state_id` remains record metadata for locating and cleaning up the
latest Shiny server bookmark URL. It is not the conversation pointer. In
bookmark mode, response settlement may mint a bookmark and update this URL,
but v2 persistence remains eager and independent of settlement.

Browser and URL restore modes continue to identify only a conversation and
therefore restore its persisted `active_leaf`. Bookmark fidelity beyond the
shinychat pointer is explicitly out of scope; shinychat contributes no
transcript, turns, or rendered content to bookmark values.

## Stacked work

0. **Conversation-ID integration gate (`shinychat#ykxh`, complete).** Stable
   identity ownership, lifecycle ordering, capability-gated transitions, and
   the full Python gate are reviewed and closed.
1. **Current keystone restore + continuation (`shinychat#5r50`, claimed).**
   Add v2 read/activation, display replay, restore hooks, turns materialization,
   baseline reset, and a continued-turn integration test.
2. **Q3 + branching (`shinychat#6drf`, blocked by `shinychat#5r50`).**
   Run/port the predecessor suite; add v2 graph projection, sibling navigation,
   rewind hooks, and the one resubmit primitive. Upgrade the wire only after
   recorded red evidence.
3. **Retry affordance + regenerate path (`shinychat#72ee`, blocked by
   `shinychat#6drf`).** Project exchange status, add retry transport/UI, route
   retry and the tested regenerate path through the sibling primitive, rebuild
   all packaged assets, and cover pending/error/cancelled reloads without
   exposing detailed stored errors.
4. **Bookmark pointer (`shinychat#g6tt`, blocked by `shinychat#72ee`).**
   Store and restore the atomic conversation/node pointer, preserve bookmark
   lifecycle cleanup, and cover stale records/nodes.
5. **Phase 4 acceptance (`shinychat#pvjx`, blocked by `shinychat#g6tt`).**
   Exercise edit, navigation, retry, regenerate, cross-session continuation,
   and bookmark-node restore; run the deletion pass and collect coherent
   review evidence.

Each remaining child is a coherent review unit. The note is approved and P4.0
is closed; P4.2 is parked pending Garrick authorization, while later children
remain sequenced behind it.

### P4.2 parked escalation (2026-09-01)

The graph commit `82ee43bf`, resubmit commit `e50ba734`, and server-block
commit `f6396a39` landed green. Independent review found that browser
optimistic submission can still create phantom UI and lose the draft during a
held resubmit. Implementation, navigation, and the browser port are stopped.

Correlated rejection/rollback is rejected due the prior Shiny serialization
evidence; busy/sibling pending is insufficient. The recommendation is to
narrowly extend the existing capability-gated completion-v1 marker for Python
v2 edit/resubmit and sibling navigation while retaining the `f6396a39` server
defense. Prior P4.0 authorization explicitly excluded edit/navigation, so
Garrick authorization is required.

Does Garrick authorize, for capability-advertising Python v2 only, extension of the existing historyTransitionPending=requestId protocol to edit/resubmit and sibling navigation: synchronously mark before the request; carry the UUID through the handler and best-effort non-masking finally completion; block every user submission path while pending; allow only the matching server-issued resubmit update_input(submit=True) to submit once while preserving the user's draft and attachments; and add no rollback/rejection protocol, queue, timer, second marker/owner, Q3 exchange-ID upgrade, or R server change?

**Regression matrix:** v2 browser edit held resubmit blocks compose
text+attachment and prevents phantom/server input, then release yields one
replacement/provider dispatch while draft+attachment remain; edit
failure/cancellation releases the marker and preserves draft/attachment;
generic UUID stale completion/remount exact-match coverage; v2 navigation
blocks compose while held and has no auto-submit bypass; capability absence
leaves Python v1 and R unchanged.

**Exclusions:** no rollback/rejection protocol, queue, timer, second
marker/owner, Q3 exchange-ID upgrade, R server change, Phase 5
guards/degradation, retry/status UI beyond this contract, bookmarks, legacy
import, or later tasks.

## Verification

- Before the first implementation child, run
  `make py-check-tests FILTER='history or transcript'` and the existing
  `history_edit` Playwright suite on the branch.
- Add focused model/controller tests for graph projection, pointer validation,
  state materialization, hook order, sibling creation, and no mutation on
  failed validation.
- Add production-path Playwright coverage for cross-session continuation,
  edit/navigation, restored partial retry, regenerate, and bookmark-node
  selection.
- For client work, run JS lint/tests/build through Make and `make update-dist`;
  verify committed dist/package copies.
- Run `make py-check-format`, `make py-check-types`, focused tests, and the
  applicable full `make py-check`, recording unrelated failures by Kata id.

## Progress

- P4.0 `shinychat#ykxh` completion: the combined history/transcript gate passed
  34 Playwright and 376 non-browser tests. The dedicated `history_edit`
  browser baseline passed 9 tests with 182 deselected. The Make
  zero-selection disposition is already recorded: its follow-on non-browser
  invocation selected no tests and returned pytest exit 5, which is a caller
  invocation mismatch rather than a harness gap.
- Final `make py-check` passed Ruff, Pyright with 0 errors, 191 Playwright
  tests, 750 non-browser tests, and 1 skipped test. Warnings were
  pre-existing and nonfatal.

## Handoff

Landed: P4.0 `shinychat#ykxh` merged as `e27e7278981e061864cc1fdf81d5c7c6fa5d3ca8`; identity ownership, lifecycle decisions, and the full verification evidence are recorded above.
Next: complete normal integration/review handling for the committed roborev 1067 fix; `shinychat#5r50` remains blocked and not begun.
Boundary: no production or test code changed in this handoff; OTel scalar overlap, the init/restore race, and Phase 5 guards/degradation/audit remain deferred.

### Roborev 1067 handoff (2026-08-31)

Accepted findings are covered by the existing committed bounded fix
(`ad650e88325cfb17d6dded2ddd194f3b2355e06e`). In v2,
`_ExchangeRecorder._new_record()` allocates without notifying; `_persist_record()`
stores first and then performs the active-ID callback once, leaving the
announcement eligible for retry after either a store or callback failure.
`new_chat()` and `delete()` reset the recorder before awaiting active-ID
clearing callbacks, so those callbacks observe no stale v2 record. The focused
retry regression explicitly fails the first store, confirms no callback or
stored record, then succeeds on the next persistence and verifies callback and
store identity.

Verification evidence: `uv run pytest
pkg-py/tests/test_history_controller.py
pkg-py/tests/pytest/test_conversation_id.py` passed 147 tests with 5 warnings;
`make py-check-format` passed; `make py-check-types` reported 0 errors; and
`make py-check` passed Ruff, Pyright, 191 Playwright tests, and 754 non-browser
tests with 1 skipped (15 warnings, no failures). Current state: roborev 1067
review is accepted and this bounded fix is committed and verified; the
post-commit review for this fix remains to be collected. `shinychat#5r50`
remains blocked and not begun.

### Stable-ID publication escalation decision (2026-08-31)

**Decision: REPLACE.** Before any implementation resumes, replace the ambient
stable-ID publication submechanism. Do not replace stable-ID integration, and
do not replace `_ExchangeRecorder` as the sole v2 record owner. This is the
mandatory three-findings escalation for `shinychat#ykxh`.

**Evidence and trace:** Roborev jobs 1067 and 1071 together raised four Medium
lifecycle findings: active-ID/URL publication before durable v2 persistence,
ambiguous retry after callback failure or cancellation, destructive callbacks
observing stale recorder state, and active delete cleanup that can leave active
record/turn state behind. R2 requires a durable v2 record plus URL active-ID
publication. The `{conversation_id,node_id}` bookmark pointer remains owned by
`shinychat#g6tt`. R7 remains the roadmap-primitives trace: extend existing
primitives rather than introduce a new lifecycle subsystem. The lifecycle
cleanup obligation here is limited to Phase 4.0 `new_chat()` and active
`delete()`; the Phase 5 clear/switch/abort audit is outside this decision.

**Abstraction count and deletion pass:** the plan sketch has two ownership
abstractions: `HistoryController` as stable-ID owner and `_ExchangeRecorder` as
v2 record owner. The current mechanism adds notify policy, the unqualified
`_active_id_announced` boolean, and the ambient callback reread, for five
total. The replacement deletes those three additions and retains the two
ownership abstractions.

**Required invariants:**

1. `HistoryController` has one controller ID owner, and every v2
   `record.id` equals that ID.
2. No URL active-ID pointer is published before durable v2 persistence.
3. Capture the record and ID before `store.put()`, publish only if that exact
   record is still current afterward, and record-bound callback retry state
   cannot affect a successor record.
4. Publication remains retryable after store failure, callback failure, or
   cancellation.
5. Phase 4.0 `new_chat()` and active `delete()` reset state before awaiting
   their callbacks; active deletion leaves no recorder, ID, turns, or messages
   behind while the next conversation can publish normally.

**Required tests:** blocked first write A -> reset -> B;
failure/cancellation retry isolated to A; active-delete callback failure leaves
recorder, ID, turns, and messages cleared.

**Exclusions:** no queue, timer, CAS, second owner, restore mechanism, or
init-window guard. Only `shinychat#ykxh` can resume after this decision-note
commit is reviewed. `shinychat#5r50` remains blocked until `shinychat#ykxh` is
green, reviewed, and closed.

### Stable-ID publication replacement handoff (2026-08-31)

The approved stable-ID publication replacement is landed in code commit
`ec00ddc08045689f871b94d3f0fb926933e65d28` (`fix(history): bind v2 ID
publication to record`, `Kata: shinychat#ykxh`). It deletes the notify policy,
the ambient `_active_id_announced` boolean, and the ambient callback reread.
`HistoryController` remains the stable-ID owner and `_ExchangeRecorder` remains
the sole v2 record owner. `_persist_record()` captures the exact `record` and
its ID before `store.put()`, stores first, and publishes only when that same
record is still current; publication retry state is bound to that record.
Active delete clears local recorder, active-ID, turns, and message state before
awaiting the `None` callback.

Exact regression coverage is present in
`pkg-py/tests/test_history_controller.py`: the blocked first write
A -> reset -> B case; the callback failure/cancellation parameterization proving
same-record retry behavior; and active-delete callback failure/cancellation
coverage for both v1 and v2 local-state cleanup. Review disposition: only the
blocked first-write A -> reset -> B regression discriminates the old
ambient-boolean issue; the failure/cancellation regression proves retry for the
same record.

Final evidence: targeted history tests passed (155 passed, 5 known warnings);
format passed; types reported 0 errors; and final `make py-check` passed Ruff,
Pyright with 0 errors, 191 Playwright tests, 761 standard tests, and 1 skipped
test, with 15 known warnings. Final Terra review found no findings. Roborev
1071 was closed immediately after the fix commit.

No new design decision was made, and the existing scope exclusions remain:
no queue, timer, CAS, second owner, restore mechanism, or init-window guard.
`shinychat#5r50` remains blocked and unstarted. `shinychat#ykxh` remains open
with `needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"` for human review.

### Roborev 1073 replacement decision (2026-08-31)

Roborev job `1073` reviewed code commit
`ec00ddc08045689f871b94d3f0fb926933e65d28` and returned `FAIL` with two
Medium findings:

1. An in-flight recorder `put()` can complete after active deletion and
   resurrect the deleted conversation (`pkg-py/src/shinychat/_history.py:930`).
2. A publication callback can suspend after validation; `new_chat()` can
   publish `None`, after which the stale callback can resume and publish the
   old ID last (`pkg-py/src/shinychat/_history.py:371`).

Both findings are valid. They are findings 1-2 against the replacement
submechanism, so the three-findings valve is not re-triggered. **Decision:
PATCH** the replacement by reusing the existing `_ExchangeRecorder` lock as
the one per-session serialization boundary. Do not add another lock or
replace the controller/recorder ownership split.

For v2, `new_chat()` and `delete()` acquire the recorder lock inside the
existing destructive-mutation boundary. Active `delete()` acquires the
existing recorder lock before `on_evict` and `store.delete()`, then holds it
through recorder reset, controller active-ID clear, adapter
turns/transcript and message clear, and the awaited explicit `None` active-ID
callback. New-chat publication is likewise serialized with the recorder
persistence/publication path, so an older callback cannot finish after the
clear transition. Persistence and lifecycle callbacks therefore have these
ordering guarantees:

- A blocked write for conversation A cannot resume after active deletion and
  recreate A as the active conversation.
- A publication callback for A completes before `new_chat()` can publish
  `None`; the observable callback order is `[A, None]`.
- Reset, active-ID clearing, local transcript/message clearing, and the
  explicit clear callback complete as one serialized v2 lifecycle sequence.

**Barrier-test supersession:** the earlier blocked-write `new_chat()`
regression in `pkg-py/tests/test_history_controller.py` around line 716 is
superseded and must be replaced. It awaits `new_chat()` before releasing
`put(A)`, which deadlocks once `new_chat()` acquires the recorder lock, and
its expectation that A remains stored conflicts with the approved lock
ordering. That test and expectation are no longer valid.

The replacement barrier regressions specified by this decision were:

1. Blocked `put(A)` versus active `delete()`: start A's blocked persistence,
   start deletion, assert deletion waits, release A, then assert deletion
   completes after `on_evict` and `store.delete()`, with no durable A and no
   active recorder, ID, turns, or messages.
2. Blocked callback A versus `new_chat()`: block the callback after it
   receives A, start `new_chat()`, assert the new chat waits, release A, then
   assert callback order `[A, None]`, completion of the new chat, and no stale
   publication afterward.

This decision traces to R2's durable-record-before-pointer and session
continuity requirements, and R7's requirement to extend existing lifecycle
primitives rather than introduce a new subsystem. The patch adds no queue,
timer, CAS, second record owner, init-window guard, or new lock. Implementation
was initially stopped pending review. **Superseded by the current resolution
below:** the approved patch has landed, so implementation is no longer stopped
and `shinychat#ykxh` is no longer blocked.

### Roborev 1073 resolution handoff (2026-08-31)

The approved existing-recorder-lock replacement landed in
`2e1f9f0837ce8e499930d5aac5a9750083b88207`. `_ExchangeRecorder` remains the
sole v2 owner, and `HistoryController` remains stable-ID owner/controller.
Active v2 `new_chat()` and `delete()` serialize with the existing recorder
lock. Active delete holds that lock before `on_evict`/`store.delete()` through
recorder reset, active-ID clear, adapter turns/transcript and message cleanup,
and the awaited explicit `None` callback. The barrier regressions verify blocked
`put(A)`/delete removal and blocked callback A/`new_chat()` ordering
`[A, None]`.

No restore, bookmark, init guard, or new mechanism scope was added. Successful
evidence: focused tests 10 passed/126 deselected; `make py-format` passed;
`make py-check-types` reported 0 errors; and full `make py-check` passed with
191 Playwright, 762 non-browser, 1 skipped, and 15 known warnings. Roborev
1073 is closed. `shinychat#ykxh` remains open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`;
`shinychat#5r50` remains blocked and unstarted.

### Roborev 1079 escalation: lifecycle boundary decision required (2026-08-31)

Roborev job `1079` reviewed code commit
`2e1f9f0837ce8e499930d5aac5a9750083b88207` and returned `FAIL` with a valid
Medium finding at `pkg-py/src/shinychat/_history.py:875`: `new_chat()` and
`delete()` reserve destructive transcript admission before waiting for the
recorder lock. A concurrent input can enter the transcript during that wait,
be cleared locally, and then have its recorder callback persist into a new
conversation, leaving transcript and history inconsistent. Job `1079` remains
open; no review closure was performed.

This is finding 3/3 against the replacement submechanism, so the mandatory
three-findings valve fires. **Decision: DELETE/REPLACE** the interpretation
that the recorder lock alone is the lifecycle transaction. Retain the
existing recorder lock for persistence serialization, but do not treat it as
the admission, cleanup, and callback boundary.

The required ordering is:

```text
transcript-admission boundary -> recorder lock -> cleanup/None callback -> release
```

The policy conflict is unresolved and requires Garrick's choice before any
implementation:

- The existing transcript test preserves an input accepted while clear is
  pending.
- The Phase 4 mechanism note says destructive lifecycle operations reject
  conflicting admission.

Garrick must choose one of:

1. **Reject:** reject input admitted during the narrow `new_chat()` or active
   `delete()` wait, preserving the destructive-operation boundary.
2. **Preserve:** preserve that input coherently as input to the new
   conversation by reordering or detaching the clear operation.

No implementation may begin before this choice is recorded. After the choice,
the required regressions cover blocked `put(A)` versus active delete, blocked
callback A versus `new_chat()` with callback order `[A, None]`, concurrent
input during the blocked lifecycle wait under the selected policy, and
failure/cancellation at each awaited lock-held cleanup and callback boundary.
Once implemented, review must use one batched range review covering the
replacement chain.

The escalation remains within R2's durable-record/session-continuity trace and
R7's existing-primitives trace. Scope exclusions remain: no queue, timer,
CAS, second record owner, new lock, restore/bookmark mechanism, or init-window
guard. `shinychat#ykxh` is parked for Garrick escalation, remains open with
`needs-review` and `work.attention="blocked"`, and
`shinychat#5r50` remains blocked and unstarted.

### Garrick decision: Option A (2026-08-31)

Garrick chose **Option A**. During a pending active `new_chat()` or active
deletion, submission is prevented and rejected at admission until the
transition completes or errors. No local transcript entry, exchange node, or
recorder callback is created. The user's browser draft remains available for
explicit resubmission after the transition. Admission reopens on success,
failure, or cancellation; there is no deferred or queued submission.

This supersedes the conflicting pending-clear preservation expectation only
for active `new_chat()` and active deletion lifecycle operations. Generic
clear behavior remains Phase 5 scope.

The initial implementation requires no saving spinner or other visual
affordance. Saves are expected to be fast; observed slowness must be
investigated rather than masked. A history-UI spinner is a possible later
affordance, but is outside Phase 4 unless separately required.

Implementation remains stopped pending review of this note. Before resuming,
the selected policy requires regressions
for blocked input during `new_chat()` and active deletion, successful and
failed/cancelled transitions, and the existing persistence/publication barrier
cases. The previously required batched range review remains after
implementation. At that historical handoff, job `1079` was open; its current
status is recorded at the end of this note, and
`shinychat#5r50` remains blocked.

### Async-save clarification (2026-08-31)

The async-save question is resolved as follows: saves are awaited, failures
propagate, and browser/transcript state is not rolled back. Option A admission
protection remains in force; this is the chosen correctness solution, not a
performance optimization.

Python's store API is awaitable, but the built-in file store's serialization,
write, and replace operations run synchronously. Custom yielding stores may
release the event loop for unrelated work while admission remains blocked.
R persistence is synchronous, and the Phase 6 port carries the stabilized
shape.

Fire-and-forget or background saves are rejected for Phase 4. Correct
ordering, error propagation, and teardown would require a queue/task owner or
second owner, and would risk stale writes and process loss. The initial Phase
4 implementation therefore retains awaited saves. It provides no saving
spinner or other visual affordance.

Q2 evidence for a 3.86 MB, 206-node record shows ordinary writes at roughly
7.15-7.20 ms median with p95 <= 8.29 ms; restart-pointer persistence has p95
88.8 ms. Revisit this decision only with end-to-end slowness evidence, network
filesystem evidence, R evidence, or real user reports. A history-UI spinner
is a possible later affordance, not Phase 4 scope unless separately required.

Implementation remains stopped until this note is reviewed. Job `1079`
remains open and unclosed; `shinychat#5r50` remains blocked and unstarted.

### ~~Option A implementation mechanism (required before implementation)~~ [SUPERSEDED]

> **SUPERSEDED:** The server strict-admission, `input_rejected`, envelope,
> and optimistic-rollback mechanism in this section is obsolete. The
> client-marker protocol in the authorization decision below is the only
> current proposal; recorder persistence and destructive-ordering fixes remain
> current.

Use the existing destructive transcript transaction with a narrow,
strict-admission parameter, and enable that parameter only for active
`new_chat()` and active `delete()`. The admission check occurs before
transcript mutation, latest-input update, recorder callback, and the built-in
`on_user_submit`/provider handlers. A rejected submission creates no server
state. The strict-admission gate releases through the existing `finally` path
on success, failure, or cancellation.

Sequence identity is end-to-end: allocate `seq` before optimistic dispatch,
carry it with the browser input through Python raw-input handling to `Chat`,
store it on both optimistic user/loading entries, and echo it in
`input_rejected`. Restore the draft and attachments and remove the optimistic
pair only when that exact `seq` pair still exists; a stale or mismatched
rejection is a complete no-op.

The admission path is the sole raw-input consumer. Provider and existing
`on_user_submit` handlers observe only the existing accepted-input signal,
which is updated after successful admission; they never consume raw input
independently. Rejection therefore occurs before the accepted signal, latest
input, transcript, recorder, or provider side effects.

The browser currently clears the editor and attachments and adds an
optimistic user/loading pair before the server responds. Rejection therefore
uses the existing transport sequence identity. This protocol is required for
draft retention. It is not a spinner, queue, or new state owner. Generic
`clear()` and inactive `delete()` remain unchanged; generic clear remains
Phase 5 scope, and the R server remains Phase 6 scope.

Before implementation resumes, add:

- model/controller coverage for admission ordering, no server state or
  callbacks on rejection, and gate reopening on success, failure, and
  cancellation;
- JavaScript reducer/UI coverage for correlated optimistic-pair removal,
  text/attachment restoration, and stale-rejection no-op behavior;
- the required asset rebuild with `make update-dist`, including all packaged
  Python and R asset copies; and
- Playwright coverage for pending active `new_chat()`/delete rejection,
  retained-draft resubmission, and success/failure/cancellation transitions.

Implementation remains stopped pending review of this note. Job `1079`
remains open and unclosed, and `shinychat#5r50` remains blocked and
unstarted.

### ~~Orchestrator compatibility decision (2026-08-31)~~ [SUPERSEDED]

> **SUPERSEDED:** This section's strict-admission and `input_rejected`
> requirements are stale. Do not implement them; the client-marker
> authorization question and protocol below are authoritative.

During the strict active `new_chat()`/`delete()` window, only a valid
sequenced composite input is eligible for a correlated rejection:
`input_rejected(seq)`. Bare strings, composites without `seq`, and malformed
payloads are rejected silently with no transcript, exchange node, recorder,
latest-input, or provider side effect because their rollback cannot be safely
correlated. The strict gate still releases through the existing `finally`
path on success, failure, or cancellation.

Outside the strict window, preserve current bare-string compatibility. The
currently shipped browser already emits the composite input with `seq`, so
ordinary users are unaffected. This is not a global hard gate or deprecation.
R browser/handler parity remains Phase 6 scope, and public deprecation/removal
remains Phase 7 scope. During implementation, correct the internal TypeScript
transport comment; do not add public R documentation or `NEWS` entries now.

Required coverage includes Python model/controller handling for valid,
missing-sequence, bare-string, and malformed payloads; JavaScript reducer/UI
correlation behavior; and Playwright strict-window rejection and
outside-window compatibility. Future R parity coverage belongs to Phase 6.
The existing `make update-dist` requirement applies to the JavaScript change
and all packaged asset copies.

Implementation remains stopped pending review of this note. Job `1079`
remains open and unclosed; `shinychat#5r50` remains blocked and unstarted.

### ~~Stage 1 scheduling decision (2026-08-31)~~ [SUPERSEDED]

> **SUPERSEDED:** The server-side envelope and strict-admission scheduling
> instructions in this section are struck. Do not implement them. Use only the
> client-marker authorization question and scope recorded below.

The raw handler creates an immutable parsed input-event envelope
synchronously. Its only immutable disposition variants are:

```text
accepted(payload, seq?)
reject_correlated(seq)
discard_silently
```

The handler reads the destructive transaction capability only at handler time
and snapshots the disposition into the envelope. There is no generation
counter, ambient flag, or later capability check. The later reactive effect
switches only on the immutable envelope and never rereads strict state.
`reject_correlated(seq)` sends exactly one `input_rejected` asynchronously for
each processed rejected envelope. `discard_silently` returns without
transport or state effects. `accepted(payload, seq?)` performs
transcript/capture work and then updates the accepted-only provider/public
signal.

Each real priority:event client update gets its own reactive flush; only
test-only direct reactive writes may coalesce. Delayed, inverse, and rapid
event timing must therefore be tested against the immutable envelope, not
treated as evidence for a second scheduling mechanism.

No unsupported synchronous transport bypass, second ambient flag,
queue/timer/CAS, or second owner is allowed. Remove the accidental
`_strict_user_input_admission` implementation and its slash-command strict
gate/tests from the Stage 1 anchor. Slash-command handling is separate and
outside P4.0.

Required rework and regressions cover the immutable envelope, removal of
`_strict_user_input_admission` and slash-command strict tests, delayed-effect,
inverse-timing, and rapid-event behavior, no-side-effect discard/rejection,
gate release on success/failure/cancellation, two real transport-update cases,
and the effect-coalescing caveat. JavaScript and Playwright coverage must also
prove reducer rejection behavior, `seq` allocation before optimistic dispatch,
and restoration that removes only the exact optimistic pair.

The existing uncommitted Stage 1 anchor must be reworked to this decision.
Implementation remains stopped pending review of this note. Job `1079`
remains open and unclosed; `shinychat#5r50` remains blocked and unstarted.

2026-08-31 handoff: Handler-time envelope core work is currently unstaged.
Terra evidence: focused Python 294 passed/1 skipped; JS lint/tests/update-dist/types passed; Playwright production-path probe failed because Shiny queues follow-up browser input behind the awaited transition; Luna independently confirmed with Shiny client/session-lock code.
Next action: Garrick must decide the admission boundary and whether a client transition marker or independently owned transition task is permitted; neither is within current constraints.

### Stage 1 browser-serialization escalation (2026-08-31)

The real Shiny browser serializes the next input until awaited active
`new_chat()`/`delete()` completes. Therefore the server strict-envelope,
`input_rejected`, and optimistic-rollback design cannot implement Option A as
specified and must be deleted/reworked. The recorder and destructive-ordering
fixes remain required and are retained.

> **SUPERSEDED SERVER DESIGN:** The strict-envelope, `input_rejected`, and
> optimistic-rollback portion of this escalation is superseded by the
> client-marker protocol below. The client-marker proposal remains pending
> Garrick authorization.

The smallest proposed replacement requires Garrick's authorization:

- Maintain a per-chat, client-only
  `historyTransitionPending=requestId`, set synchronously when active New Chat
  or active Delete starts.
- Propagate `submissionBlocked` to the input surface and block Enter, send,
  attachment-only, slash-command, and imperative submission before dispatch.
  Preserve the browser draft and attachments; add no spinner.
- Send `requestId` with the transition event.
- Have Python emit matching
  `history_transition_complete {requestId}` in `finally` after success,
  handled failure, or cancellation.
- Treat a stale completion as a no-op.

Existing busy indicators, history updates, and error notifications are
insufficient because they do not synchronously protect all submission paths
or identify the transition that releases the block. This proposal adds no
queue, timer, CAS, second owner, or server ambient flag. Generic clear,
switch, restore, and inactive delete remain out of scope; the R server remains
Phase 6 scope.

Required coverage includes the JS transition marker and all blocked input
paths, Python completion emission on success/handled failure/cancellation,
Playwright draft/attachment preservation and stale-completion behavior, and
`make update-dist` for all packaged copies. The existing uncommitted anchor
must be reworked only after authorization. Its tracked non-note diff hash is
`46df02b9d29c657405121fda66e12e7b51a28b696e593da8c0d99d6921a3b10a`.

Implementation is stopped pending Garrick authorization. Job `1079` remains
open and unclosed; `shinychat#5r50` remains blocked and unstarted.

### Superseding authorization decision (2026-08-31)

The earlier server strict-admission, `input_rejected`, immutable-envelope,
and optimistic-rollback instructions are explicitly superseded and struck as
implementation requirements. They cannot implement Option A against the real
Shiny browser serialization boundary. Retain the recorder persistence and
destructive-ordering fixes.

The exact authorization question for Garrick is:

> Does Garrick authorize replacing server strict admission, input_rejected,
> and optimistic rollback with a per-chat client-only
> historyTransitionPending=requestId marker, request-ID-bearing active
> New/Delete events, and Python history_transition_complete emitted from
> handler finally, with no queue, timer, CAS, second owner, or server ambient
> flag, while retaining recorder persistence and destructive-ordering fixes?

The proposed design is scoped to New only with an active conversation and
Delete only when its target is active. Inactive delete, switch, restore, and
clear are excluded; `sendMessageEdit` is explicitly excluded. `_on_new` and
`_on_delete` own completion in `finally`, emitting the matching completion for
success, handled error, or cancellation while preserving the original
outcome. Python and TypeScript action types must carry the request ID; matching
completion clears the client marker, while stale completion is a no-op.

Required coverage includes JS/Python action and marker behavior, Playwright
blocking/draft preservation and success/handled-error/cancellation release,
and `make update-dist`. That command mechanically updates the packaged R
JavaScript copies; R server/handler parity remains Phase 6. The obsolete
`history_pending_admission` Playwright fixture is replaced by this
client-transition coverage.

No queue, timer, CAS, second owner, or server ambient flag is authorized by
this note. Implementation is stopped pending Garrick authorization. The
current tracked non-note diff remains preserved with hash
`46df02b9d29c657405121fda66e12e7b51a28b696e593da8c0d99d6921a3b10a`; job
`1079` had not yet reached its final state at that historical handoff; its
current status is recorded at the end of this note, and `shinychat#5r50`
remains blocked and unstarted.

### Garrick authorization: YES (2026-08-31)

Garrick explicitly answered **YES** to the exact authorization question
above. The client-side blocking protocol is approved:

- Set per-chat `historyTransitionPending=requestId` synchronously for active
  New Chat and active Delete.
- Propagate the block to every submit route, preserving draft and attachments
  with no spinner.
- Send request-ID-bearing transition events.
- Have `_on_new` and `_on_delete` own
  `history_transition_complete {requestId}` in `finally` for success, handled
  failure, or cancellation while preserving the original outcome.
- Clear only the matching request; stale completion is a no-op.

The recorder persistence and destructive-ordering fixes remain approved. The
superseded server strict-admission, `input_rejected`, immutable-envelope, and
optimistic-rollback work is deleted/reworked and must not be implemented.
Implementation may resume for `shinychat#ykxh` only after this note is
reviewed; `shinychat#5r50` remains blocked. Attention remains blocked pending
note review. The current tracked non-note diff remains preserved with hash
`46df02b9d29c657405121fda66e12e7b51a28b696e593da8c0d99d6921a3b10a`.

### Client transition protocol handoff (2026-08-31)

- Landed `ace09c52`: active New/Delete set a request-ID marker, block every client submission route, and clear only on matching Python `finally` completion; recorder persistence/destructive ordering remain intact.
- Evidence: JS lint/test/build and `make update-dist` passed; focused history/controller and transition Playwright passed; `make py-check` passed with 193 Playwright and 768 non-browser tests (1 skipped).
- Next: keep `shinychat#ykxh` open with `needs-review` and `work.attention=ok`; `shinychat#5r50` remains blocked; roborev `1079` closed after the fix commit.

### Parked client-transition review handoff (2026-08-31)

**Supersedes the preceding successful handoff only for further
implementation.** Code commit `ace09c52` and documentation commit `37812e37`
remain committed; neither is reverted or patched by this handoff.

Independent review of `ace09c52`/`37812e37` accepted three findings against
the approved client-only transition protocol:

1. The shipped R bundle sends active New/Delete request IDs, but
   `pkg-r/R/chat_history.R` never emits `history_transition_complete`;
   R submissions can therefore remain permanently blocked.
2. `HistoryStore.requestSequence` resets after cleanup/remount, allowing an
   old completion to collide with a new `history-1`.
3. The awaited completion send in Python `finally` can mask the original
   handled failure or cancellation.

These are three findings against the same mechanism, so the escalation valve
fires. Disposition: park further implementation pending Garrick
authorization. Recommended direction: add a Python server capability gate for
marker activation, make no R P4 server changes, and leave R on its legacy
behavior until Phase 6. This is a new cross-wire contract and therefore
requires Garrick's authorization before any implementation resumes.

Current state: `shinychat#ykxh` remains open with `needs-review`,
`work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. Roborev `1079` was closed after
`ace09c52`; `shinychat#5r50` remains blocked and unstarted.

### Mandatory 3/3 replacement proposal (2026-08-31)

The three findings against the client-transition protocol are all valid:

1. R can permanently block because its shipped New/Delete path sends a
   request without emitting completion.
2. Remount cleanup can reset the incrementing request ID and collide with an
   old completion.
3. Awaiting completion in Python `finally` can mask the original handled
   error or cancellation.

The escalation valve therefore fires. **Decision: DELETE/REPLACE** the
unconditional marker and incrementing-ID protocol. Retain `HistoryStore` as
the sole owner of the client transition marker, `_ExchangeRecorder` as the
sole server record owner, matching completion/input blocking, and the
recorder persistence/destructive-ordering fixes.

The smallest proposed replacement requires Garrick's authorization:

- Add optional `transition_protocol: "completion-v1"` to the existing
  `history_update` action.
- Python advertises the exact capability. R omits it in Phase 4 and advertises
  the same capability and completion protocol in Phase 6.
- Absent, unknown, or withdrawn exact capability means legacy behavior: clear
  `historyTransitionPending` and restore legacy behavior with no marker,
  request, or completion expectation.
- When the capability is advertised, only active New and active Delete use the
  existing UUID helper for their request IDs. Inactive delete, select/switch,
  restore, clear, edit, and navigation are excluded.
- Every `history_update` replaces the capability state; omission or withdrawal
  disables the protocol and clears any marker.
- A stale completion is a no-op.
- Python completion is emitted only for request-bearing transitions and is
  best-effort/non-masking, preserving the original operation outcome. Add an
  explicit regression proving completion-delivery failure cannot mask the
  original handler outcome.

This adds no handshake, queue, timer, CAS, server flag, second owner, or
Phase 5 guard. Required coverage includes Python/TypeScript capability
replacement and stale/omitted/unknown/withdrawn behavior, active New/Delete
completion and input blocking, non-masking failure/cancellation and
completion-delivery failure, Playwright remount and legacy-compatibility
cases, and mechanical `make update-dist` R asset copies. R server parity
remains Phase 6, where R advertises the same capability/completion protocol.

The exact authorization question is: **Does Garrick authorize replacing
unconditional protocol with this capability-gated completion-v1 protocol?**
Implementation is stopped pending that authorization. The current tracked
non-note diff is empty with hash
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
job `1079` is currently `done`/`FAIL` with `closed=true`; no review-close
operation was performed in this work. `shinychat#5r50` remains blocked.

**Current state:** `shinychat#ykxh` remains open with `needs-review` and
`work.attention="blocked"`; `shinychat#5r50` remains blocked. The historical
entries above are historical snapshots; the current Roborev state is the
singular `done`/`FAIL`/`closed=true` state above.

### Garrick authorization: completion-v1 approved (2026-08-31)

Garrick authorized replacing the unconditional transition protocol with the
capability-gated completion-v1 protocol:

- `history_update` may advertise optional
  `transition_protocol: "completion-v1"`.
- Python advertises the capability in Phase 4; R remains on legacy behavior
  until Phase 6, when it advertises the same capability and completion
  protocol.
- Absent, unknown, or withdrawn capability clears
  `historyTransitionPending` and restores legacy behavior.
- Advertised active New and active Delete transitions use UUID request IDs.
- Completion is best-effort and cannot mask the original handler outcome.
- The scope remains active New and active Delete only. Inactive delete,
  select/switch, restore, clear, edit, and navigation remain excluded.
- `HistoryStore` remains the sole client transition-marker owner, and
  `_ExchangeRecorder` remains the sole server record owner.

Implementation may resume for `shinychat#ykxh` only after this note is
reviewed. `shinychat#5r50` remains blocked. Attention remains
`work.attention="blocked"` pending note review.

### Completion-v1 replacement handoff (2026-08-31)

Landed: `0d287c1205cd3c22a9fa66baeae27168cb4e6f46` replaces the
unconditional client protocol. Python advertises
`history_update.transition_protocol = "completion-v1"`; `HistoryStore`
replaces capability state on every update and clears its pending marker for
absent, unknown, or withdrawn values. Only capability-enabled active New and
active Delete use UUID request IDs. Completion remains request-bearing only,
best effort, and non-masking. R intentionally omits the capability; its
shared-JS legacy regression is in `test-chat-history-hooks.R`. Generated
assets are committed in `5a0351d7a8dbc5778676b963a22f999b78f3895d`.

Verification: `make update-dist`; `make js-lint`; `make js-test` (1243
passed, 23 skipped); `make js-build`; focused
`make py-check-tests FILTER='history_transition or history_update_advertises
or completion_delivery'` (2 Playwright and 15 non-browser passed);
`make r-check-tests FILTER='chat-history-hooks'` (22 passed);
`make r-check-format`; and `make py-check` (193 Playwright, 777
non-browser, 1 skipped; known warnings only).

Next: retain `shinychat#ykxh` open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"` for
human review. `shinychat#5r50` remains blocked and unstarted.
Boundary: no R server completion implementation, queue, timer, CAS, second
owner, init-window guard, or Phase 5 behavior was added.

### Production Playwright coverage follow-up (2026-08-31)

Added focused production-path coverage under
`pkg-py/tests/playwright/chat/history_transition/`:

- The browser starts an active New transition, remounts the real
  `shiny-chat-container`, starts a new active transition after the remounted
  store receives `completion-v1`, and proves the earlier transition's stale
  completion does not release the new marker. The attempted submission remains
  client-side until the new transition completes, then explicit resubmission
  succeeds.
- Separate real-app cases send `history_update` with absent, unknown, and
  withdrawn `transition_protocol` values. Each path keeps the legacy New
  submission usable and confirms no transition marker blocks it.

Verification: focused
`uv run pytest pkg-py/tests/playwright/chat/history_transition -q` passed
6 tests; targeted Ruff lint and format checks passed. No production code or
generated assets changed. `shinychat#ykxh` remains open with
`needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#5r50` remains blocked
and unstarted.

### Roborev 1111 test-review disposition (2026-08-31)

Roborev job `1111` reviewed test commit
`c3dfbb662f5d4806401127376e83ba6e35e61a32` and returned `FAIL` with one valid
Medium finding at
`pkg-py/tests/playwright/chat/history_transition/test_history_transition.py:120`:
the test attempted submission before confirming delivery of the stale
completion, so it could pass without proving that the stale completion left
the new marker intact.

Disposition: accepted and corrected in follow-up test commit `4f9d8bfb`.
The fixture now sends an existing `update_input` action immediately after the
stale completion; the browser waits for that acknowledgment, proves the real
send button remains disabled, and only then attempts submission. The prior
review job was closed after the correction commit. The focused
history-transition suite passes 6 tests, targeted Ruff lint/format and
`make py-check-format` pass, and no production code or generated assets
changed. `shinychat#ykxh` remains open with `needs-review`,
`work.attention="ok"`, and `shinychat#5r50` remains blocked.

### Roborev 1112 final test-review disposition (2026-08-31)

Roborev job `1112` reviewed the corrected test commit
`4f9d8bfb4ae47f67a0cc886714ecbec72c6d8d28` and returned `PASS` with no
findings. The review confirmed that the stale-completion submission is
attempted only after browser acknowledgement while the replacement transition
remains pending.

Final verification: `uv run pytest
pkg-py/tests/playwright/chat/history_transition -q` passed 6 tests;
`uv run ruff check pkg-py/tests/playwright/chat/history_transition` passed;
`uv run ruff format --check
pkg-py/tests/playwright/chat/history_transition` reported both files already
formatted; and `make py-check-format` passed. No production code or generated
assets changed.

Handoff: keep `shinychat#ykxh` open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"` for
human review and closure. `shinychat#5r50` remains blocked and unstarted.

### Remaining remount evidence gap (2026-08-31)

The existing remount regression still uses fixture-side
`history_transition_complete` injection and does not prove the production
`_on_new` `finally` path. An attempted test-only replacement was stopped
without a test commit: Shiny serializes the session's reactive handlers, so a
blocked real `_on_new` prevents the fixture release/republish handlers from
running; after the custom element is remounted, its production history drawer
cannot render until a server `history_update` arrives. Starting the second New
through the real drawer therefore requires either a production lifecycle
change to republish state while the first handler is blocked or a direct test
bypass, both outside this task's scope.

No production or generated files were changed, and no replacement test landed.
`shinychat#ykxh` remains open with `needs-review` and
`work.attention="blocked"` pending design/production disposition;
`shinychat#5r50` remains blocked and unstarted.

### Stale-completion browser provenance backlog disposition (2026-08-31)

The stale-completion scenario is theoretically reachable. Exact UUID matching
prevents completion A from clearing marker B except on a UUID collision.
However, deterministic reproduction with the current fixture is impossible:
Shiny serializes session reactive handlers, so a blocked real
`_on_new`/`_on_delete` prevents fixture release and republish handlers from
running, while remount hydration requires a server `history_update`. A timer
is not credible synchronization.

This is real but out of Phase 4 scope. Backlog issue
`shinychat#n5d3` requests a future Playwright WebSocket proxy/harness that
holds a real `history_transition_complete(A)` frame across remount and marker
B, then forwards it to prove production-finally provenance deterministically.
It is test-harness work only and is not a Phase 4 fix or blocker.

Existing JS unit coverage proves UUID/exact-match/stale/remount/blocking
behavior. Python coverage proves real finally success/error/cancellation and
non-masking completion delivery. The current Playwright direct completion
injection remains synthetic routing/remount coverage only and must not claim
real production-finally provenance. The `bf9aee8c` fixture blocker is resolved
by this backlog disposition. `shinychat#ykxh` remains open with
`needs-review` and `work.attention="ok"` for human review/closure;
`shinychat#5r50` remains blocked and unstarted.

### P4.0 integration gate closure (2026-08-31)

Garrick authorized closure after the complete implementation range passed
batched Roborev review `1116` with `PASS` and no findings. The reviewed unit
starts at parent `ba95e652c4d84fa1cce8c2694da708c62e0d7146` of `ace09c52` and
ends at `4f9d8bfb4ae47f67a0cc886714ecbec72c6d8d28`, including the capability
replacement, packaged assets, and both production Playwright test commits;
later docs-only disposition commits were excluded.

Verification: `uv run pytest
pkg-py/tests/playwright/chat/history_transition -q` passed 6 tests;
`make py-check-format` passed; the recorded full implementation gate remains
green with JS lint/tests/build, `make update-dist`, focused Python and R
checks, and `make py-check` evidence above. No unresolved review findings
remain. The real browser provenance limitation is dispositioned to backlog
`shinychat#n5d3` and is not a P4.0 blocker.

`shinychat#ykxh` is closed. `shinychat#5r50` is now the ready, unblocked next
Phase 4 keystone; no `shinychat#5r50` implementation has started. The Phase 4
parent `shinychat#azvt` remains open with `work.attention="ok"`.

### P4.1 entry baseline disposition (2026-08-31)

`shinychat#5r50` is claimed on `feat/history-exchange-tree`, but
implementation is parked before code changes because the required type
baseline is red. Evidence:

- `make py-check-tests FILTER='history or transcript'`: 40 Playwright and
  403 non-browser tests passed, with 8 known warnings.
- `make py-check-format`: passed.
- `uv run pytest pkg-py/tests/playwright/ -k 'history_edit'`: 9 passed,
  188 deselected.
- `make py-check-types`: failed with one Pyright error at
  `pkg-py/tests/playwright/chat/history_transition/app.py:140`; the
  fixture's `dict[str, Any]` argument is not assignable to `ChatAction`.

No production or test code was edited to resolve this baseline failure.
`shinychat#5r50` remains open with `work.attention="blocked"` pending
disposition of the existing fixture type error. `shinychat#ykxh` remains
closed; `shinychat#azvt` remains open with `work.attention="ok"`. No
`shinychat#5r50` implementation has started.

### P4.1 fixture typing repair handoff (2026-08-31)

The pre-keystone fixture type gap is fixed in
`shinychat#m0fn` by `da56ffcb16ce03e84744328897b2d3d15d351568`
(`test(history): type transition fixture action`). The intentionally
noncanonical `history_update` payload remains unchanged at runtime; the
fixture now casts it to `ChatAction` at the existing send boundary. No
production behavior, generated assets, or test behavior changed.

Roborev job `1124` reviewed the code/test commit and returned `PASS` with no
findings. Verification after the fix: the focused transition suite passed 6
tests; `make py-check-format` passed; `make py-check-types` passed with 0
errors; and full `make py-check` passed with 197 Playwright tests, 777
non-browser tests, 1 skipped, and known nonfatal warnings.

`shinychat#m0fn` remains open with `needs-review` and
`work.attention="ok"` for human closure. Its completion is required before
`shinychat#5r50` can resume, so `shinychat#5r50` remains open with
`work.attention="blocked"` and no implementation started. `shinychat#ykxh`
remains closed and `shinychat#azvt` remains open with
`work.attention="ok"`.

### Phase-level child-closure authorization (2026-08-31)

Garrick authorized closing reviewed child tasks as they pass their required
reviews, reserving human review and final closure for `shinychat#azvt`.
`shinychat#m0fn` is closed with its scoped fix, full Python gate evidence, and
Roborev `1124` `PASS`/no findings. Its blocking relationship to
`shinychat#5r50` is therefore cleared.

`shinychat#5r50` is active again on `feat/history-exchange-tree` with
`work.attention="ok"` and the green pre-keystone baselines recorded above.
Keystone implementation has not started. Human review is not a gate for this
child; it remains reserved for the end of `shinychat#azvt`. The phase parent
`shinychat#azvt` remains open with `work.attention="ok"`.

### P4.1 restore keystone handoff (2026-08-31)

Landed `d7866b444a3fba49c237dc224b13b5a97e9d9457`
(`feat(history): restore v2 exchange trees`, `Kata: shinychat#5r50`).

- `_ExchangeRecorder` owns the private insertion-ordered restore registry and
  is still the sole v2 record owner. `StatePathContext` supplies each hook
  only its keyed active-path entries, and the registered `shinychat:turns`
  consumer materializes the most recent snapshot plus following deltas once,
  calls `set_turns_json()` once, and resets the capture baseline.
- `HistoryOptions.restore_bootstrap` defaults to `"recorded"`; `"live"` skips
  only the implicit root snapshot. A later snapshot replaces the live prefix.
- `HistoryController._restore_exchange_record()` is the v2 transaction used
  by both initialization and switching. It validates the graph path before
  destructive mutation, clears display/greeting, replays input and captured
  messages through `_restore_bookmark_message`, executes restore hooks, then
  installs the recorder record, publishes changed active identity, restores
  app values, and sends history state. P4.1 has no selected-node pointer
  mutation; bookmark-node persistence remains `shinychat#g6tt`.
- Replay temporarily suppresses transcript capture only around the production
  `_restore_bookmark_message` loop. This is required because that method
  appends to `ChatTranscript`, which otherwise invokes recorder callbacks and
  could persist replay as new exchanges. The suppression is restored before
  state hooks, is inside the destructive v2 transaction, and adds no
  lifecycle owner or persistent state.

Evidence: focused controller restore tests passed 6; history configuration
tests passed 2; dedicated production continuation Playwright passed 1;
`history_edit` passed 9; `make py-check-format` and `make py-check-types`
passed. Final `make py-check` passed Ruff, Pyright, 198 Playwright tests, and
783 non-browser tests with 1 skipped and 19 known nonfatal warnings. The
production fixture asserts restored turn count 2/node count 2, then turn count
4/node count 3 after the next real submission, as well as the provider's
restored-prefix context.

Next: retain `shinychat#5r50` open with `work.attention="ok"` pending the
required human review; do not start `shinychat#6drf`. No graph operations,
rewind hooks, sibling/resubmit work, Q3 protocol change, retry UI, bookmark
pointer, JS/R work, init guard, or degradation behavior landed in this unit.

### P4.1 restore-transaction review escalation (2026-08-31)

Independent read-only review of `d7866b44` and `64e988c3` accepted a
restore-transaction failure-semantics gap. The happy-path keystone is green,
but no further implementation may proceed until this decision is made.

1. Graph-path validation occurs before destructive mutation, but
   `shinychat:turns` kind/version/data validation occurs only after display
   replay begins. A malformed entry can therefore replace live display before
   it raises.
2. Replay transport failure or a restore-hook failure can leave a partially
   restored display/state while the recorder still owns the previous record.
   A later accepted input could then be captured into the wrong record.
3. Active-ID callback failure or cancellation after recorder installation can
   leave the new record active without completing app-state/history
   publication; an ordinary same-ID retry is a no-op.

The reviewer also found duplicate v2 initialization metadata publication and
missing production switch/capture-suppression coverage. Those are bounded
follow-ons once the transaction contract is selected.

**Decision required from Garrick:** should P4.1 restore be failure-atomic
after preflight, and if so what rollback contract is authorized for display,
turns, recorder ownership, active ID, and external callbacks? The approved
note requires install only after display/state success but does not specify
how an already-mutated live session is recovered when replay, a hook, or
publication fails. Do not guess by adding a second owner, queue, timer, CAS,
or init guard.

Current state: `d7866b44` and `64e988c3` remain committed and their full
Python gate evidence remains valid. `shinychat#5r50` is open with
`needs-review` and `work.attention="blocked"` pending the decision; do not
start `shinychat#6drf` or request Roborev.

### P4.1 restore failure-contract escalation (2026-09-01)

Independent findings against the committed happy-path restore are:

1. Partial target display can coexist with old recorder and turn ownership
   after replay mutates display before all state validation succeeds.
2. Active-ID callback failure or cancellation can leave partial activation
   that an ordinary retry cannot recover.
3. Unknown state keys are silently ignored even though the restore contract
   does not define whether state keys are closed or extensible.
4. Browser and URL initialization can publish duplicate `history_update`
   metadata.

The durable documents do not define an abort contract. Atomic
preserve-previous rollback is infeasible: replay commits messages
individually, `set_turns` provides no rollback guarantee, and application
callbacks are external effects. The proposed contract is therefore
fail-to-fresh-draft, not failure-atomic rollback:

- Preflight the complete active path, every state key, state kind/version/data,
  and final turns before mutation.
- Enter the destructive boundary and recorder lock; clear and replay with
  capture suppressed; apply turns and reset the recorder baseline; install
  the target, set the local ID, run callbacks, publish, and send one metadata
  update.
- On any later exception or cancellation, clear recorder and active ID first;
  best-effort clear display, turns, greeting, URL, and metadata; preserve the
  original failure or cancellation; and emit a visible restore-failure
  notification. Cleanup failure reports partial cleanup. Make no atomic
  rollback claim.

Required injected-failure regressions from Terra are: invalid state
kind/version/data during preflight; replay transport failure after partial
replay; restore-hook failure after target installation; active-ID callback
failure and cancellation; cleanup failure after the original error; and
browser/URL initialization asserting exactly one `history_update`. These tests
must prove fresh-draft cleanup, recorder/ID clearing order, original-outcome
preservation, visible failure reporting, and no duplicate publication.

This proposal adds no Phase 5 guard or degradation behavior, second owner,
or rollback subsystem. Exact authorization question: **Does Garrick authorize
the fail-to-fresh-draft contract described above?**

Implementation remains stopped pending that decision. `shinychat#5r50`
remains open with `needs-review` and `work.attention="blocked"`;
`shinychat#6drf` remains blocked and unstarted. `shinychat#azvt` remains open
with `work.attention="ok"`.

### Restore failure-contract correction (2026-09-01)

The Phase 4 unknown-key policy is strict: every state key must be registered
by the restore contract. Any unregistered key is unsupported and fails closed
during preflight, before any mutation. Add a regression for an injected
unknown key and prove that live display, turns, recorder ownership, and active
ID are untouched.

The outcome matrix is explicit:

- Success produces no failure notification.
- An error or cancellation preserves and re-raises the original outcome.
- Cleanup, metadata-publication, and failure-notification errors are
  secondary; they must never mask the original error or cancellation.
- `CancelledError` is caught inside the restore transaction so local recorder
  and active-ID ownership are cleared, best-effort async cleanup and
  notification are attempted, and the original cancellation is re-raised.
  Repeated cancellation or session unavailability may prevent a visible
  notification; that absence is not a new outcome.

The exact successful order is: install the recorder target; set the local
active ID and invoke its callback; run application restore callbacks; send
exactly one metadata update; and suppress the outer initialization duplicate.
Required regressions add successful restore with no failure notification,
cancellation with cleanup failure, cancellation with a notification attempt,
and allowed notification absence under repeated cancellation or unavailable
session, in addition to the unknown-key and previously listed injected
failures.

This correction preserves the prior scope, exclusions, fail-to-fresh-draft
contract, and authorization question. Implementation remains stopped;
`shinychat#5r50` stays open with `needs-review` and
`work.attention="blocked"`, `shinychat#6drf` remains blocked/unstarted, and
`shinychat#azvt` remains open with `work.attention="ok"`.

### Garrick authorization: fail-to-fresh-draft approved (2026-09-01)

Garrick approved the fail-to-fresh-draft restore contract. This is the
intended domain behavior, not a patch or an atomic-rollback substitute:

- Preflight validates the complete active path and all strictly owned state
  data before mutation; unregistered keys fail closed.
- After mutation begins, an error or cancellation clears recorder and active
  ownership first, then attempts best-effort live cleanup and notification.
- Stored records remain untouched and retryable. The original error or
  cancellation outcome is preserved and re-raised; cleanup failures are
  reported honestly as partial cleanup and never mask that outcome.

Implementation may resume on `shinychat#5r50` only. `shinychat#6drf` remains
blocked and unstarted. This is a docs-only authorization handoff;
`shinychat#5r50` remains open with `needs-review` and
`work.attention="blocked"` pending note review.

### P4.1 fail-to-fresh-draft implementation handoff (2026-08-31)

Landed: strict restore preflight validates the active path, every state key,
turn kind/version/data, and final materialized turns before destructive
mutation. The restore transaction now clears display/greeting, replays with
capture suppression, applies turns and resets the baseline once, installs the
recorder target, publishes active identity, invokes app callbacks, and sends
one metadata update. Browser/URL initialization returns after that v2
transaction to suppress the former duplicate update.

Failure contract: after mutation starts, every `BaseException`, including
`CancelledError`, clears recorder and local active ownership synchronously,
then best-effort clears display, turns, greeting, URL/active navigation, and
metadata before attempting the restore-failure notification. The original
outcome is re-raised; cleanup, metadata, and notification failures stay
secondary. Stored records are untouched and the next input creates a fresh
record.

Evidence: controller injections cover clear, greeting, each replay, turn
setter, restore hook, active-ID callback, app callback, metadata, unknown and
unsupported preflight entries, cancellation with cleanup/notification failure,
successful no-notification ordering, and next-input recovery. The production
v2 Playwright fixture covers restore/continuation, capture suppression during
A-to-B switching, and exactly one initialization `history_update`. Focused
history/transcript passed 42 Playwright plus 428 non-browser tests; `history_edit`
passed 9; format and Pyright passed; final `make py-check` passed 199
Playwright, 802 non-browser, 1 skipped, and 19 known warnings.

Next: retain `shinychat#5r50` open with `needs-review` pending human review;
do not start `shinychat#6drf`. Boundary: no Phase 5 guard/degradation,
rollback subsystem, public hook, second owner, JS/R, graph/sibling, or
bookmark work landed.

### Luna accepted follow-up handoff (2026-08-31)

Luna accepted two bounded findings against `6402dcc0` and `f672f7b4`. Both
are fixed in `90c9eee4` (`fix(history): harden restore cleanup and live
bootstrap`, `Kata: shinychat#5r50`).

1. `_clear_failed_restore()` now records failures from every cleanup operation
   before notifying. A fully cleaned failure still says a fresh chat is ready;
   any cleanup failure instead says recovery was incomplete and asks the user
   to reload before starting a new chat. The original restore error or
   cancellation is still re-raised. Cleanup and notification failures remain
   secondary.
2. `restore_bootstrap="live"` now validates the stored record/path/state
   before destructive mutation, then captures and materializes adapter turns
   only after the destructive-admission boundary and recorder lock are held,
   immediately before clear/replay. Lock or admission waiting alone remains
   non-destructive, so it cannot install a stale live-turn snapshot.

Focused injection coverage verifies each cleanup action (messages, turns,
greeting, active-ID callback, and metadata) can fail after the original
restore error without masking it, while selecting incomplete-recovery
notification. Cancellation coverage retains the original cancellation through
cleanup and notification failure. The live-bootstrap barrier test independently
holds admission and the recorder lock, changes adapter turns while restore is
waiting, and proves the installed turns are captured only after both release.

Verification: focused v2 restore controller tests passed 29; `make
py-check-format` passed; `make py-check-types` passed with 0 errors; `make
py-check-tests FILTER='history or transcript'` passed 42 Playwright plus 434
non-browser tests with 8 known warnings; `history_edit` passed 9; and `make
py-check` passed Ruff, Pyright, 199 Playwright tests, 808 non-browser tests,
1 skipped, and 19 known warnings.

At that handoff, task state was `shinychat#5r50` open with `needs-review` and
`work.attention="ok"` for human review. No Roborev request was made, and
`shinychat#6drf` remains blocked and unstarted. No new design decision was
needed at that point.

### P4.1 follow-up review parking

The follow-up review of `90c9eee4` + `b4af5e25` found four **Required**
test-discrimination gaps in the same restore mechanism:

1. The live-bootstrap barrier test mutates before admission release and does
   not prove capture occurs after the recorder lock is held.
2. The cancellation test cannot distinguish cancellation of the original
   restore outcome from cancellation of the notification attempt.
3. The cleanup matrix does not prove that later cleanup runs after an earlier
   cleanup failure.
4. Notification text is not tested.

These are review-evidence gaps; the follow-up review confirmed no new
production behavior defect. All prior production and test evidence remains
valid as recorded above. Because this is now at least three review findings
against the same restore mechanism, the process escalation valve parks the
work pending Garrick's decision: patch the mechanism/tests or delete and
replace the mechanism. No production or test code is to change until that
decision.

Current task state: `shinychat#5r50` remains open with `needs-review`,
`work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. Task closure is unchanged.

### P4.1 escalation-valve decision (2026-08-31)

The Phase 4 orchestrator completed the escalation valve with **PATCH, not
DELETE/REPLACE**. All four post-`90c9eee4` findings are
test-discrimination gaps; no new runtime behavior defect was confirmed. The
restore transaction remains the approved minimal single-owner design, so its
shape is retained.

Only focused test hardening for those four evidence gaps is authorized. This
decision authorizes no production or test code change in this coordination
update. If the focused hardening produces a test that falsifies the approved
behavior, stop and obtain a new decision before proceeding.

Task state is restored to open with labels `area:py,needs-review,phase-4`,
`work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`. Task closure is unchanged.
Do not start `shinychat#6drf`; it remains blocked and unstarted. No Roborev
request is authorized for this documentation-only decision.

### Test-hardening handoff (2026-08-31)

Authorized test-hardening patch `91440e2b` landed. It covers the four evidence
gaps: capture after both live-bootstrap admission and recorder-lock release;
preservation of the original `CancelledError` across notification
cancellation; continuation of every later cleanup action after an earlier
cleanup failure; and exact clean/incomplete recovery notification text.

Verification: controller 170 passed; history/transcript passed 42 Playwright
plus 437 non-browser tests with 8 established warnings; `history_edit` passed
9; `make py-check` passed 199 Playwright plus 811 non-browser tests, 1 skipped,
with 19 established warnings; format and types passed green. Independent Luna
review accepted the first three assertions. The suggestion to test the full
Shiny notification transport was declined: the actual helper with a mocked UI
sink is the approved controller boundary.

No production code, decision, or scope changed. `shinychat#5r50` stays open
with `needs-review` and `work.attention="ok"`; `shinychat#6drf` remains
blocked and unstarted.

### P4.1 bounded review-gap completion (2026-09-01)

The three authorized evidence gaps are complete with no new mechanism or
scope:

- `10a20a16` validates every `StateEntry.mode` strictly as `snapshot` or
  `delta` during complete preflight, before destructive mutation. The unit
  regression proves an invalid mode fails closed without changing live
  display, turns, recorder ownership, or active ID. It also adds the
  restore-specific active-ID callback cancellation regression: the target is
  installed and its callback is attempted, cleanup invokes the callback with
  explicit `None`, recorder/active ownership and display/turns return to a
  fresh draft, and the original `CancelledError` instance propagates.
- `0ed9865d` adds production-path URL-mode Playwright coverage using a real
  URL restore in a fresh session and asserts exactly one `history_update`,
  parallel to the browser-mode coverage.
- `a6fc207d` corrects the URL fixture's `restore_mode` literal typing; full
  Pyright remains green.

Verification: focused controller tests passed 172; the v2 restore Playwright
module passed 3; `make py-check-format` passed; `make py-check-types` passed
with 0 errors; and full `make py-check` passed Ruff, Pyright, 200 Playwright
tests, and 813 non-browser tests with 1 skipped and 19 established warnings.
No Roborev request was made in this handoff.

Implementation is complete for this bounded fix and the task remains open
with `needs-review` and `work.attention="ok"` pending the instructed review
step. `shinychat#6drf` remains blocked and unstarted. The existing
fail-to-fresh-draft transaction and all Phase 4 scope exclusions remain
unchanged.

### P4.1 final transcript-recovery evidence (2026-09-01)

The last test-evidence gap is closed in `a9bd8ce7`
(`test: exercise transcript recovery after restore failure`,
`Kata: shinychat#5r50`). The existing next-input recovery regression now:

- installs the recorder's actual production callbacks on
  `fake_chat._transcript`;
- forces replay failure through that attached transcript's `append()` and
  failing send path;
- verifies every `suspend_capture` callback is restored after failure;
- proves the prior active record and failed target record are unchanged and
  recorder ownership is cleared; and
- submits the next input through the same transcript, proving a fresh record
  and node are created through the real recorder callbacks.

No production defect was exposed and no production code or mechanism changed.
The focused controller test passed; `make py-check-format` and
`make py-check-types` passed with 0 errors; and full `make py-check` passed
Ruff, Pyright, 200 Playwright tests, and 813 non-browser tests with 1 skipped
and 19 established warnings. No Roborev request was made.

`shinychat#5r50` remains open with `needs-review` and
`work.attention="ok"`; `shinychat#6drf` remains blocked and unstarted. The
approved fail-to-fresh-draft contract and Phase 4 scope exclusions remain
unchanged.

### P4.1 same-transcript recovery evidence tightened (2026-09-01)

The follow-up test-evidence tightening is committed in `f311053c`
(`test(history): tighten transcript recovery regression`,
`Kata: shinychat#5r50`). The failing transcript send stub now asserts all
five recorder capture callbacks are `None` before raising, proving replay
failure occurs while `suspend_capture` is active. After the next input uses
that same transcript, the regression asserts the fresh record ID differs from
both `target.id` and the prior `existing.id`, while the pre-restore existing
record remains unchanged. No production defect was exposed.

Verification after these assertions: the focused controller test passed;
`make py-check-format` passed; `make py-check-types` passed with 0 errors; and
full `make py-check` passed Ruff, Pyright, 200 Playwright tests, and 813
non-browser tests with 1 skipped and 19 established warnings. No Roborev
request was made.

`shinychat#5r50` remains open with `needs-review` and
`work.attention="ok"`; `shinychat#6drf` remains blocked and unstarted. The
approved restore contract and Phase 4 scope exclusions remain unchanged.

### P4.1 Roborev 1135 escalation decision (2026-08-31)

Mandatory batched range review job `1135` was requested from parent
`3582d67` and covered `d7866b44` through `f311053c` inclusive. The job
returned `FAIL` with four findings and remains open (`closed=false`); it must
not be closed. All four findings are valid and in scope against the mixed v2
persistence/projection layer:

1. Active v2 rename mutates a separately loaded record while the recorder
   retains the old title, allowing the next capture to overwrite the rename
   with stale recorder state. Active rename must mutate the recorder-owned
   record under its lock; storage loading is only for inactive records.
2. V2 persistence omits `on_save` capture and switching bypasses
   `save_current()`, so application values expected by restore are not
   round-tripped. Capture app state through the recorder path at response
   settlement and before switching.
3. `stream_updated()` durably persists each streamed chunk and publishes a
   full `history_update` on the streaming critical path. Chunk durability must
   remain eager without emitting history metadata.
4. Restore publishes the active ID without marking that exact record as
   published, causing a redundant URL callback on the next capture. The exact
   restored record must be marked ID-published after the active-ID callback.

**Decision: DELETE/REPLACE the mixed layer, not patch it.** Replace the
mixed persistence/projection ownership while retaining `_ExchangeRecorder`,
the approved restore behavior, and the stable conversation ID. The exact
replacement target is:

- `_ExchangeRecorder` is the sole active v2 owner/mutator; it owns active
  rename, `on_save` capture, and `store.put` under its existing lock.
- `HistoryController` owns active ID and wire publication only; it never
  separately writes active v2 records. Inactive rename may load from storage.
- V2 response/save/switch/new capture `on_save` values and durably save the
  departing record through the one recorder path.
- Restore installs/publishes the exact record, marks that exact record
  ID-published after the active-ID callback, runs restore callbacks, then sends
  exactly one metadata update.
- Stream chunks remain eagerly durable but do not emit `history_update`.
  Metadata publication is limited to initial creation, terminal state,
  rename, visible ID/metadata change, restore/switch/new/delete.

Required regressions cover active rename/title preservation; `on_save`
round-trip across response/save/switch/new; eager chunk durability without
`history_update`; and restore exact-ID publication, callback, and one-metadata
ordering. Include ownership and lock-serialization coverage as appropriate,
proving the recorder remains the only active v2 mutator and that controller
projection/publication does not race recorder-owned mutation.

Exclusions are explicit: no mixed second active writer/projection owner, no
new lock/queue/timer/CAS/second owner, no Phase 5 guard/degradation, and no
unrelated Q3, bookmark, or R work. Preserve the existing Phase 4 scope
boundaries and the stable recorder/restore/ID decisions.

Implementation is stopped pending note review. `shinychat#5r50` remains open
with `needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. `shinychat#6drf` remains open,
blocked, and unstarted. `shinychat#azvt` remains open with
`work.attention="ok"`. No implementation tests are authorized by this
handoff.

### P4.1 Roborev 1135 corrective current-state record (2026-08-31)

This append-only correction supersedes every earlier implementation-complete
or `work.attention="ok"` snapshot in this note and in the
`shinychat#5r50` history. Those entries remain historical records; they do
not authorize implementation, change the valve decision, or describe the
current task state. The current and authoritative state is the blocked
decision below.

Roborev 1135 has four findings against the same mixed v2
persistence/projection layer, so the three-findings escalation valve fired.
All four findings are valid and in scope. The decision remains
**DELETE/REPLACE the mixed layer**, retaining `_ExchangeRecorder`, restore,
and the stable ID.

Ownership is exact: `_ExchangeRecorder` is the sole active v2 owner of
content/state mutation and `store.put` under its existing lock, including
active rename and `on_save` capture. `HistoryController` owns lifecycle
orchestration, display/state projection, deletion, and active-ID plus
metadata publication; it never separately writes active v2 records.
Inactive rename may load.

`ConversationRecordV2.values` has these exact capture points:

- terminal response captures values;
- explicit save captures current values;
- switch/new saves the departing record before restore/reset; and
- application restore callbacks run only after target installation.

The discriminating tests must prove that streamed chunks are eagerly durable
with zero `history_update` metadata, terminal response emits exactly one
metadata update, restore marks only the exact record ID-published and only
after active-ID callback success, and the next capture does not repeat that
callback. Retain active rename/title, `on_save` round-trip, and
ownership/serialization regressions.

Preserve these exclusions: no second active writer/projection owner, new
lock, queue, timer, CAS, second owner, Phase 5 guard/degradation, Q3,
bookmark, or R work.

Implementation is stopped pending note review. Roborev 1135 remains open with
`FAIL`/`closed=false`. `shinychat#5r50` is open with `needs-review`,
`work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. `shinychat#6drf` is open,
blocked, and unstarted. `shinychat#azvt` is open with
`work.attention="ok"`. No implementation tests are authorized by this
correction.

### HISTORICAL, SUPERSEDED: P4.1 Roborev 1135 DELETE/REPLACE implementation (2026-08-31)

The approved replacement landed in `04825f1f`
(`fix(history): replace v2 persistence ownership`, `Kata: shinychat#5r50`).
It retains the existing recorder lock and the restore/failure contract:

- `_ExchangeRecorder` is the sole active v2 content/state mutator. Under its
  existing lock it captures `on_save` values, handles active rename, and is
  the only active v2 `store.put` path. `HistoryController` no longer writes
  the active v2 record.
- Response settlement, explicit save, switch, and new-chat capture the active
  record's values through recorder-owned persistence before any restore or
  reset. Application restore callbacks still run only after target
  installation.
- Stream start/update/finish writes remain eager and durable. They send no
  `history_update`; terminal response settlement publishes exactly one
  metadata update. Initial creation, rename, restore, switch, new, and delete
  retain their visible metadata paths.
- Restore marks only the installed record as ID-published, and only after
  `_set_active_id()` and its callback have completed. The next capture does
  not re-publish that ID. Existing store/callback failure and cancellation
  retry behavior remains intact.

The new focused regressions use `FileConversationStore` to prove an active
rename survives a later capture; cover values across response/save/switch/new
plus restore callback installation; prove chunk durability with zero metadata
and terminal-only metadata; prove exact restore-ID publication; and prove
active rename serializes behind a blocked recorder capture. The prior v2
response-settlement test now correctly asserts one recorder-owned persistence
write rather than the superseded v2 no-op.

Verification: required entry baseline passed 43 history/transcript Playwright
tests plus 439 non-browser tests (8 established warnings), `history_edit`
passed 9, format passed, and Pyright reported 0 errors. Post-change focused
controller coverage passed 177 tests (2 established warnings); the final
history/transcript gate passed 43 Playwright plus 444 non-browser tests (8
established warnings); and final `make py-check` passed Ruff, Pyright, 200
Playwright tests, and 818 non-browser tests with 1 skipped and 19 established
warnings. `git diff --check` passed.

Roborev job 1135 was closed immediately after the code/test fix commit, as
required; no new review was requested. The documentation handoff is
`dbde0c1a`. `shinychat#5r50` remains open with `needs-review` and
`work.attention="ok"`; do not close it here. `shinychat#6drf` remains blocked
and unstarted. No branching/Q3, bookmark, Phase 5, JavaScript, R, queue,
timer, CAS, second lock, or second owner work was added.

### HISTORICAL, SUPERSEDED: P4.1 Luna independent read-only review disposition (2026-08-31)

Luna reviewed `04825f1f` + `dbde0c1a` + `5849f02e` against the Roborev 1135
DELETE/REPLACE ownership boundary, found no in-scope production defect,
verified actual complete-response and stream-terminal settlement wiring, and
identified only two non-blocking test gaps: the focused chunk test invokes
`controller.on_response` directly rather than the production callback; inactive
v2 rename has no dedicated regression. Decision: neither gap falsifies
production behavior nor is required by the approved bounded fix; do not
expand scope.

Roborev 1135 is closed; no new review was requested. All verified evidence
from final `make py-check` remains: Ruff passed, Pyright passed, 200
Playwright tests passed, 818 non-browser tests passed, 1 test was skipped,
and 19 established warnings remained. `shinychat#5r50` remains open with
`needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`. `shinychat#6drf` remains blocked
and unstarted. This was a read-only review disposition; no production or
test change is authorized or required.

### P4.1 corrected independent-review handoff (2026-08-31)

This section is authoritative and supersedes/withdraws the prior Luna
dispositions that called the following gaps non-blocking or optional:

- Terminal production settlement coverage is an in-scope required regression.
  The terminal metadata assertion must exercise the registered production
  settlement callback, not call `controller.on_response` directly.
- Inactive v2 rename coverage is an in-scope required regression, using
  `use_exchange_tree=True`.

The corrected review also records a P1 switch race in `04825f1f`: v2 source
save currently occurs before destructive admission, so an input can be
persisted and then visually cleared during a switch. The approved ordering
uses only existing primitives:

```text
destructive transcript admission -> recorder lock/source save -> restore
```

No new mechanism is approved. The required regressions are:

1. A deterministic interleaving proving accepted input cannot enter during
   switch save/restore.
2. Terminal metadata through the registered production settlement callback,
   rather than a direct controller call.
3. Inactive v2 rename with `use_exchange_tree=True`.

A fresh mandatory batched Roborev review is required after these fixes.
Roborev 1135 was a pre-replacement review and is insufficient for the
corrected range; it is not current review evidence and must not be requested
again now.

Implementation is stopped pending note review. `shinychat#5r50` remains open
with `needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. `shinychat#6drf` remains open,
blocked, and unstarted. `shinychat#azvt` remains open with
`work.attention="ok"`. No code implementation, test implementation, review
request, or closure is authorized in this update.

### P4.1 authoritative one-boundary blocked handoff (2026-08-31)

This handoff supersedes the earlier implementation-complete and Luna
disposition sections above. They remain historical evidence only and do not
authorize implementation.

`switch_to` enters ONE `_destructive_mutation()` before departing v2 source save and retains that same boundary through the entire restore transaction, closing the admission window. The approved order is `destructive transcript admission -> recorder lock/source save -> restore`; no new mechanism.

Implementation remains stopped pending note review. The required regressions
remain:

1. A deterministic interleaving proving accepted input cannot enter during
   switch save/restore.
2. Terminal metadata through the registered production settlement callback,
   rather than a direct controller call.
3. Inactive v2 rename with `use_exchange_tree=True`.

A fresh batched Roborev review is required after these fixes because Roborev
1135 was a pre-replacement review and is not sufficient current evidence.

Truthful current task state: `shinychat#5r50` remains open with
`needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains open,
blocked, and unstarted; and `shinychat#azvt` remains open with
`work.attention="ok"`. No production code, tests, assets, review request, or
issue closure is authorized by this documentation-only handoff.

### P4.1 one-boundary follow-up (2026-08-31)

Landed `fb1e2f0d` (`fix(history): hold switch admission through v2 restore`,
`Kata: shinychat#5r50`). `switch_to()` now preflights the v2 target, enters
one `_destructive_mutation()`, acquires the existing recorder lock, saves the
departure with `save_current_locked()`, and retains that same admission/lock
pair through the shared restore transaction. The restore helper remains the
single owner of live replay, app-state restoration, active-ID publication,
terminal metadata, and fail-to-fresh-draft cleanup; no nested destructive
boundary, lock, queue, timer, CAS, or second owner was added.

The regressions deterministically hold the departing save and restore clear
while an actual recorder capture callback attempts user input, proving it
cannot persist into the source during the switch and instead persists against
the installed target. Terminal metadata is asserted through a callback
registered with `Chat._on_response_settled`, not a direct
`controller.on_response()` invocation. Inactive v2 rename runs with
`use_exchange_tree=True`, then captures the distinct active recorder record
to prove it remains unchanged.

Evidence: pre-edit history/transcript baseline passed 43 Playwright + 444
non-browser tests with 8 established warnings; pre-edit `history_edit` passed
9. Focused regressions passed 4 controller + 1 settlement test. Post-change
history/transcript passed 43 Playwright + 446 non-browser tests with the same
8 warnings; `history_edit` passed 9; `make py-format`, Pyright (0 errors),
and `git diff --check` passed. Final `make py-check` passed Ruff, Pyright, 200
Playwright tests, 821 non-browser tests, 1 skipped, and 19 established
warnings.

No Roborev request was made by instruction. `shinychat#5r50` remains open with
`needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains blocked
and unstarted. Next: retain this bounded unit for the instructed review
handling. Provisional decisions: none.

### P4.1 save-before-preflight rework (2026-08-31)

Landed `27ec1802` (`fix(history): save v2 source before target preflight`,
`Kata: shinychat#5r50`). This corrects the prior follow-up's ordering: after
the target record is loaded, `switch_to()` enters its one existing destructive
admission boundary and recorder lock, saves the departing v2 record with
`save_current_locked()`, then prepares/preflights the target, and finally
calls the existing locked restore helper. Preflight still completes before
any destructive display or state replay. No lock, queue, timer, CAS, owner,
v1, Q3, bookmark, Phase 5, JavaScript, or R mechanism changed.

The new regression uses a snapshotting store so source durability cannot be
mistaken for in-memory aliasing. A source with unsaved input and current
on-save values switches to a malformed v2 target: the failure persists the
latest source content and values, while recorder ownership, active ID, live
messages, greeting, and client turns remain source state. The same test fails
against `fb1e2f0d` because target preflight previously ran before the source
save. The three prior one-boundary regressions remain and pass.

Evidence: pre-edit history/transcript baseline passed 43 Playwright + 446
non-browser tests with 8 established warnings; `history_edit` passed 9.
Focused prior-plus-new regressions passed 4. Post-change history/transcript
passed 43 Playwright + 447 non-browser tests with the same 8 warnings;
`history_edit` passed 9; Pyright reported 0 errors; and `git diff --check`
passed. Final `make py-check` passed Ruff, Pyright, 200 Playwright tests, and
822 non-browser tests with 1 skipped and 19 established warnings.

No Roborev request was made by instruction. `shinychat#5r50` remains open with
`needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains blocked
and unstarted. No provisional decision was introduced.

### P4.1 blocked-input interleaving correction (2026-08-31)

Luna found a real blocked-input interleaving defect after `fb1e2f0d` +
`27ec1802`: during an active v2 switch, raw input can still enter after the
switch admission boundary is held. Terra's architecture review confirms the
correction is directly required by the durable Phase 2 fail-fast admission
contract and the approved `e7448db4` one-boundary handoff; it is not a new
Garrick decision.

For an active v2 switch only, raw input must fail fast before conversion,
transcript mutation, latest-input update, provider or `on_user_submit`
handling, or recorder effects. Reuse the existing destructive admission state;
add no lock, queue, timer, CAS, or owner. The accepted-input signal remains the
sole provider/`on_user_submit` trigger for latest input. Generic `clear()`,
`new_chat()`, inactive delete, and all Phase 5, JavaScript, and R work remain
unchanged. This section supersedes only the prior switch-admission
disposition/status entries; unrelated evidence remains valid.

**Handoff**
- Code for this correction is not yet landed; implementation remains pending.
- Required regression scope: deterministically interleave raw input with an active v2 switch and prove fail-fast ordering plus accepted-only provider/`on_user_submit` latest-input effects, while preserving the unchanged paths above.
- No Roborev request and no task closure; retain `shinychat#5r50` open with `needs-review`, `work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`.

### P4.1 blocked-input correction implementation (2026-08-31)

Landed `e5e59983` (`fix(history): reject input during v2 switches`,
`Kata: shinychat#5r50`). The existing destructive-history admission now has a
switch-only input-block mode. Active v2 `switch_to()` enables it before the
existing recorder-lock/source-save sequence and retains it through target
preflight and restore; the outermost existing `finally` clears it on success,
error, and cancellation. No lock, queue, timer, CAS, second owner, v1,
generic-clear/new-chat/inactive-delete, Phase 5, Q3/bookmark, JavaScript, or
R mechanism changed.

Both raw accepted-input helpers reject before `StoredMessage` conversion while
that switch mode is active. The priority raw-input effect remains the only raw
consumer; `on_user_submit` and provider handling now react to the accepted
latest-input signal only, published after capture succeeds. Echoed slash
commands retain their existing capture-before-handler behavior without
becoming normal provider submissions.

The former detached-`ChatTranscript` interleaving test is replaced by real
`Chat`/`HistoryController` regressions. They block source `put()` and real
restore `clear_messages()` independently, then prove each attempted raw input
rejects immediately with no conversion, transcript/latest/provider/recorder/
store effect and no phantom target input. A cancellation test proves later
raw input succeeds after release; generic destructive admission remains
non-strict. The first full-gate attempt exposed a test-only global
`reactive.flush()` interaction with an unrelated pending fixture; removing
that flush preserved the assertions and made the regression suite-isolated.

Evidence: pre-edit `make py-check-tests FILTER="history or transcript"`
passed 43 Playwright plus 447 non-browser tests (8 established warnings).
Targeted controller regressions passed 3; focused slash behavior and
identical-resubmission Playwright each passed 1; Pyright reported 0 errors.
Post-change history/transcript passed 43 Playwright plus 449 non-browser
tests (8 established warnings), and `history_edit` passed 9. Final
`make py-check` passed Ruff and Pyright, 200 Playwright tests, and 824
non-browser tests with 1 skipped and 19 established warnings. `git diff
--check` passed.

No Roborev request or task closure was made. `shinychat#5r50` remains open
with `needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains blocked
and unstarted. No provisional decision was introduced.

### P4.1 Luna raw-input coverage follow-up (2026-08-31)

Accepted test-coverage follow-up only. No production behavior changed.
`aa16983f` (`test(history): drive blocked input through raw effect`),
`7665c528` (`test(history): isolate raw-input regression flush`), and
`adebdf23` (`test(history): clean raw-input reactive effects`) strengthen the
active v2 switch regression while retaining the existing direct helper guards,
cancellation-release, and generic-admission coverage.

The regression now pre-seeds the real session user-input value and drives
`Chat._on_user_input` through `reactive.flush()` while source `put()` and the
real restore `clear_messages()` are independently blocked. At each barrier it
proves no conversion, accepted transcript/latest-input, provider,
recorder, or store effect. The raw effect's intended `RuntimeError` is caught
by its production error boundary, so the test records and asserts that error
instead of expecting `reactive.flush()` to raise. After the switch, a real raw
accepted submission adds no error, dispatches the provider through
`_latest_user_input`, and persists on the target record; no stuck
client/server condition was observed.

Before creating the real chat, the test drains only pre-existing foreign
mock-session effects from Shiny's process-global scheduler, with warnings
suppressed inside that cleanup; it destroys its own chat after assertions.
This keeps raw-effect flushes isolated and retains the established full-suite
warning profile.

Evidence: focused blocked-input/cancellation/generic-admission controller
tests passed 3; `make py-format` passed; Pyright reported 0 errors.
`make py-check-tests FILTER="history or transcript"` passed 43 Playwright plus
449 non-browser tests with 8 established warnings; `history_edit` passed 9.
Final `make py-check` passed Ruff and Pyright, 200 Playwright tests, and 824
non-browser tests with 1 skipped and 19 established warnings.

No Roborev request or task closure was made. `shinychat#5r50` remains open
with `needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains blocked
and unstarted. No provisional decision was introduced.

### P4.1 authoritative raw-input escalation handoff (2026-08-31)

This section supersedes the preceding raw-input acceptance and attention
snapshot. The raw-input follow-up commits `aa16983f`, `7665c528`, and
`adebdf23`, plus docs commit `56ad3a0c`, are committed; their stated gates
were green.

Luna found no in-scope production behavior violation, but found two P2
test-isolation findings: `test_cancelled_v2_switch_releases_real_chat_input_admission`
and `test_generic_destructive_admission_does_not_block_real_chat_input` create
real Chats without destroy, and
`test_v2_switch_rejects_real_chat_input_during_save_and_restore` suppresses
global scheduler failures via a 500-flush pre-drain. Together with the two
earlier test-discrimination findings that led to the real raw-effect
follow-up, this invokes the three-findings escalation valve for the raw-input
regression mechanism.

No code fix or disposition is authorized until an orchestrator chooses patch
or delete/replace. Truthful Kata state: `shinychat#5r50` remains open with
`needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains open,
blocked, and unstarted. No implementation tests, code changes, review
request/closure, or task closure are authorized by this handoff.

### P4.1 authoritative raw-input escalation decision (2026-08-31)

The escalation valve chooses DELETE/REPLACE of the raw-input regression
test-isolation strategy only. It does not choose DELETE/REPLACE of the
verified production switch-admission contract. The existing production
contract remains authoritative: an active v2 switch blocks raw input
fail-fast through the existing destructive admission state, before
conversion, transcript/latest-input/provider/`on_user_submit`, recorder, or
store effects, and the accepted-input signal remains the sole provider and
`on_user_submit` trigger for latest input.

Replacement scope is limited to the test fixtures and cleanup:

- Remove the global 500-flush reactive pre-drain.
- Give every real-`Chat` raw-input regression explicit local cleanup on both
  success and failure.
- Keep real production raw-effect coverage and the blocked-path assertions,
  including no conversion, transcript/latest-input/provider/recorder/store
  effect and no phantom target input.
- Do not change production code or production semantics, locks, queues,
  timers, CAS, or owners.

The implementer must first retry the applicable suite without the global
draining. Only if that retry produces a reproducible red test may the
implementer identify and minimally fix the responsible foreign fixture; the
fixture, failure, and evidence must be recorded. This decision authorizes no
production change, no new test-only global scheduler mechanism, no Roborev
request or closure, no task closure, and no `shinychat#6drf` work.

The decision supersedes the preceding raw-input escalation handoff only for
this test-isolation disposition. `shinychat#5r50` remains open with
`needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains open,
blocked, and unstarted.

### P4.1 raw-input test-isolation DELETE/REPLACE handoff (2026-09-01)

The approved bounded test-isolation replacement is complete in code commit
`df3653c6` (`test(history): replace raw-input global drain with cleanup`,
`Kata: shinychat#5r50`). No production behavior or mechanism changed. The
global 500-flush reactive drain was deleted. The real raw `Chat` regression
now has explicit teardown, including cancellation cleanup, and the valid
busy-count/cancellation mock lifecycle was repaired in only the foreign
fixtures that reproduced in full ordering: drawer `ArtifactSession`, greeting
`SpySession`, and greeting `MockBookmarkSession`. Unrelated Ruff format churn
in eight files was removed and was not committed.

Evidence: the initial focused/reproducer set passed 3 controller regressions,
the focused slash-behavior Playwright test, and the focused
identical-resubmission Playwright test. The first full filtered browser run
failed in `history_out_of_band`; that failure was non-reproducible twice in
isolation and passed on retry. The final filtered
`make py-check-tests FILTER="history or transcript"` passed 43 Playwright
plus 449 non-browser tests with 8 established warnings; `history_edit` passed
9. Final `make py-check` passed Ruff, Pyright, 200 Playwright tests, and 824
non-browser tests, with 1 skipped and 19 established warnings. `git diff
--check` passed.

Review disposition: no design decision was made. Potential unrelated fixture
leaks that did not reproduce were declined to preserve the approved bounded
scope; the bookmark fixture was accepted only after reproduction in the full
gate. `shinychat#5r50` remains open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`.
`shinychat#6drf` remains blocked and unstarted. No Roborev was requested.

### P4.1 current implementation and review handoff (2026-09-01)

The earlier blocked-input handoff, including its statement that the correction
was not landed, is historical and superseded by the committed implementation
and follow-up evidence below. Those historical sections remain in place as an
audit trail; they do not describe the current implementation status.

The bounded implementation is landed: the existing destructive admission
boundary blocks raw input through the v2 switch source save and restore, and
the raw-input test-isolation replacement is committed. The terminal settlement
regression is landed in `1bb5b886` and import-cleaned in `0cca3b49`. It uses
normal `Chat(..., history=HistoryOptions(...))` startup wiring and the
registered `_save_on_response`/response-settlement path; it does not assign
`controller.on_response` directly. Stream chunks produce zero
`history_update` metadata actions, while the production terminal settlement
produces exactly one metadata update and one v2 recorder response capture.

Verification for this handoff: the focused registered-settlement test passed;
`make py-check-format` passed; `make py-check-types` passed with zero errors;
and full `make py-check` passed with 200 Playwright tests, 824 non-browser
tests, 1 skipped test, and 19 established warnings. A fresh batched Roborev
review remains required and is not yet requested by this handoff.

Current state: `shinychat#5r50` remains open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`,
awaiting the fresh batched review. `shinychat#6drf` remains blocked and
unstarted; `shinychat#azvt` remains open. No task closure or sibling work is
authorized here.

### P4.1 Roborev 1146 disposition (2026-09-01)

Mandatory batched Roborev job `1146` reviewed the exact code/test range
`04825f1f^..0cca3b49` (canonical `39a61813..0cca3b49`), excluding the later
docs-only heads `a4d107e7` and `eae64b48`. It reported three findings. The
following dispositions are provisional pending the required evidence and fix;
the three-findings valve is not fired provisionally.

The switch timing disposition is provisional, not declined. The preflight
rationale that `switch_to()` loads and validates the target schema before
destructive admission is insufficient without a production v2 provider
regression. The required contract test is unconditional and must use the real
v2 provider/turn path: hold target lookup before admission, start source
provider/turn work, release lookup while that work is active, then prove the
switch rejects before target installation and leaves source ID, display,
turns, recorder, and store unchanged. The source-usability/preflight rationale
does not waive this contract or resolve the admission ordering.

The terminal-settlement teardown disposition is provisionally accepted. The
real `Chat` created by the registered settlement test must be destroyed in
`try/finally` so reactive effects and callbacks cannot leak into later tests.
Roborev `1146` remains open pending the fix commit.

The v2 bookmark settlement transfer is also provisional. It is assigned to
existing task `shinychat#g6tt`, outside the `shinychat#5r50` blocker. That task
must define the recorder-owned active-v2 `bookmark_state_id` under the
recorder lock and cover late callbacks, replacement cleanup, v2 URL behavior,
and stale-pointer behavior. This is a distinct bookmark pointer protocol,
not a `shinychat#5r50` persistence/restore blocker.

### P4.1 Roborev 1146 final progress and handoff (2026-09-01)

The required validation and teardown follow-up is landed in test commit
`88cd612c` (`test(history): cover active provider switch preflight`, Kata:
`shinychat#5r50`). The real attached-v2-provider slow-target-lookup
regression holds the target `get()` before destructive admission, starts the
source provider/turn stream, keeps that source stream active while target
lookup is released, and proves the switch rejects before target installation.
Snapshots at rejection prove no switch mutation to the source active ID,
display, turns, recorder, or store. The bounded successful-provider
settlement cleanup releases the provider and waits for the stream to settle;
the terminal-settlement test destroys its real `Chat` in `try/finally`.

Focused evidence:
`uv run pytest pkg-py/tests/test_history_controller.py
pkg-py/tests/pytest/test_chat.py -k
"active_attached_provider_without_mutating_source or
terminal_metadata_uses_registered_response_settlement_callback"` passed 2
tests, with 319 deselected. Full evidence: `make py-check` passed Ruff,
Pyright with 0 errors, 200 Playwright tests, 825 non-browser tests, 1 skipped
test, and 19 established warnings.

Roborev 1146 switch timing and terminal teardown findings are accepted and
finalized after this evidence, and job `1146` was closed. This is not final
or closable evidence: a new mandatory batched review is required over the
full range `04825f1f^..34831fd`; no new review has been requested yet. The
bookmark pointer remains out of scope in `shinychat#g6tt`; it is not a
`shinychat#5r50` blocker. `shinychat#5r50` remains open with `needs-review`,
`work.attention="blocked"`, and `work.branch="feat/history-exchange-tree"`.
`shinychat#6drf` remains open, blocked, and unstarted. No task closure or
sibling work is authorized here.

### P4.1 Roborev 1152 disposition (2026-09-01)

Mandatory batched Roborev job `1152` reviewed
`04825f1f^..34831fd1` (canonical `39a61813..34831fd1`), excluding later
docs-only commits. It completed `FAIL` with two valid PATCH findings across
two mechanisms. The three-findings valve did not fire. Job `1152` remains
open pending these fixes; prior individual or unrequested stale reviews are
not current evidence.

For v2 rename, acquire the existing recorder lock before checking the active
ID. Under that same lock, recheck the ID: if it matches, mutate and persist
the active recorder record; otherwise load and rename the requested
`conv_id` as an inactive record under the same lock. A missing record is a
no-op. Terra's exact required regression is a deterministic v2
switch/rename interleaving: block source save, start a source rename, release
the switch, and assert the source is renamed, the target title is unchanged,
and recorder/active ID remain the target. Preserve and extend
`test_v2_active_rename_waits_for_recorder_capture_lock` and
`test_v2_inactive_rename_does_not_affect_active_recorder_capture` for the
lock-time recheck, inactive persistence, and missing-ID no-op behavior.

For slash/input semantics, `_latest_user_input` remains the public latest
accepted input, including a captured echoed slash. Add a private normal
submission event carrying `(sequence, StoredMessage)` for invalidation.
Every successful capture updates the latest value. Ordinary submissions
publish the event and provider/`on_user_submit` effects consume its snapshot.
Echoed slash dispatch uses `dispatch_user_submit=False`: the slash handler
runs and latest input updates, but no provider or public callback runs.
Failed or blocked captures update neither latest input nor the normal event.
Terra's exact required tests are: extend
`test_echoed_slash_command_records_once_before_its_callback` so an echoed
command updates `user_input()` from `None` and after a prior normal input,
triggers neither `on_user_submit` nor provider work, and leaves the direct
slash handler observing the captured transcript; assert a normal raw
submission dispatches once after capture with its own text/attachments and
identical normal submissions dispatch twice; preserve failed/blocked
behavior, with `test_v2_switch_rejects_real_chat_input_during_save_and_restore`
as the blocked-path base, proving neither public latest nor private dispatch
event changes. Update helper doubles and the settlement test's
`publish_latest=False` control to the dispatch-only control introduced by
this split.

Implementation remains stopped pending note review. `shinychat#5r50` remains
open with `needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains open,
blocked, and unstarted. No implementation, review closure, or task closure is
authorized by this docs-only disposition.

### P4.1 real-provider echoed-slash regression (2026-09-01)

Test commit `7d3cd6ac` (`test(history): cover echoed slash provider bypass`,
`Kata: shinychat#5r50`) adds the final bounded provider-path regression. It
constructs `Chat(..., client=...)` with a controllable client whose
`stream_async` records calls, drives the production slash input through
`session.input[chat._slash_command_id]` and `reactive.flush()`, and destroys
the Chat in `finally`. The test proves an echoed slash updates public latest
accepted input, runs the slash handler, does not run public `on_user_submit`,
and does not call the built-in provider's `stream_async`.

Verification: the focused test
`test_echoed_slash_command_skips_builtin_provider_handler` passed; format
passed; Pyright reported zero errors; and full `make py-check` passed 200
Playwright tests, 827 non-browser tests, 1 skipped test, and 19 established
warnings. No production defect or production change was required. No Roborev
review was requested for `7d3cd6ac` in this handoff. Roborev `1155` reviewed
the pre-`7d3cd6ac` range and its provider-path gap is superseded by this
regression; it is not evidence for this commit. Roborev `1152` is already
closed after its fixes. `shinychat#5r50` remains open with `needs-review` and
`work.attention="ok"` pending review of this new test commit;
`shinychat#6drf` remains blocked and unstarted.

### P4.1 Roborev 1152 resolution and current handoff (2026-09-01)

Roborev 1152's two valid PATCH findings were accepted and fixed by
`34ed7fbe` (`fix(history): resolve Roborev 1152 findings`). The existing
recorder-lock rename recheck is preserved, and public latest accepted input
is split from the private sequenced normal-dispatch event: echoed slash
commands update the public latest value without provider or public callback
dispatch, while ordinary accepted submissions dispatch from their own
captured input. Failed or blocked captures update neither channel.

Exact verification evidence is green: focused chat 6 passed; controller 3
passed; history/transcript 43 Playwright plus 450 non-browser tests passed;
`history_edit` 9 passed; format passed; types reported 0 errors; and full
`make py-check` passed with 200 Playwright tests, 826 non-browser tests, 1
skipped test, and 19 established warnings. The independent Luna read-only
review found no findings and verified the existing recorder-lock rename
recheck, the public/private input split, the required regressions, and the
bounded scope.

`shinychat#5r50` stays open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`;
`shinychat#6drf` remains blocked and unstarted. No JavaScript, R, packaged
asset, bookmark, Phase 5, sibling, or task-closure work is included. The
phase note is committed before the Roborev 1152 close operation; the close
outcome is recorded in the corresponding Kata handoff comment.

### P4.1 provider-test tightening handoff (2026-09-01)

Test commit `93ed712c` (`test(history): prove ordinary provider dispatch`,
`Kata: shinychat#5r50`) tightens `7d3cd6ac` on the same `Chat`: after echoed
slash suppression, ordinary raw input produces exactly one real client
`stream_async` call and exactly one public `on_user_submit` callback. The
mandatory future batched range is
`04825f1f3da2286008a6e1c8e7a475b33be2426f^..93ed712cdb5d20e5e79c15fc4a3e6b15a94af146`,
with canonical base `39a61813f51ff1d99bcd6182aa7b61c968af773d` through
`93ed712cdb5d20e5e79c15fc4a3e6b15a94af146`, excluding later docs-only heads.

The focused provider test, format, Pyright, and full `make py-check` passed:
200 Playwright tests, 827 non-browser tests, 1 skipped test, and 19
established warnings. No production defect or production change was required.
No Roborev was requested for `7d3cd6ac` or `93ed712c`; `shinychat#5r50`
remains open with `needs-review` and `work.attention="ok"` pending review of
this new test range. `shinychat#6drf` remains blocked and unstarted.

### P4.1 Roborev 1158 three-findings escalation decision (2026-09-01)

Roborev `1158` returned three findings against the public-latest/private-normal-dispatch
mechanism, so the three-findings escalation valve fired. Decision: **PATCH**. Retain
the split because it is required: accepted echoed-slash inputs update public latest,
while provider and public callbacks receive normal submissions only.

The exact defect is that the private normal-dispatch event had no scheduling contract.
Default-priority consumers can run after queued history-selection effects, allowing
same-flush input plus history selection to restore the target before provider dispatch.
Authorize every `on_user_submit` consumer at priority `9998`, after raw capture at
priority `9999` and before default-priority history selection. Authorize v2
`switch_to` rejection using the existing
`latest_message_stream.status() == "running"` check after target lookup and before
destructive work. Add no flag, queue, lock, or owner; reuse existing primitives.
This decision traces to R2/R7 and the one-display-stream contract.

The deletion/abstraction pass is complete. Deleting the split would reintroduce
slash-triggered provider work or require a tagged envelope, dispatcher, and new
owner; no safe deletion or abstraction replacement is justified.

The exact same-flush regression matrix is required: normal input with one attachment
plus history select must prove source capture, provider dispatch, and public callback,
while the target remains untouched or rejected; failed capture plus history select must
prove no latest value and no private dispatch, with clean target restoration. Preserve
echoed-slash suppression, blocked-input, identical-normal-submission, and attachment
paths.

Implementation is stopped until this documentation decision is reviewed.
Fully qualified Kata issue `shinychat#5r50` remains open with `needs-review` and
`work.attention="blocked"`. `shinychat#6drf` remains open, blocked, and unstarted.

### P4.1 Roborev 1158 PATCH implementation handoff (2026-09-01)

Code `b99074b028d43687a8fa44bf97a5701fefffa7c1`
(`fix(history): sequence submissions before history selection`,
`Kata: shinychat#5r50`) implements the approved bounded PATCH only. Every
`on_user_submit` consumer, including the built-in `client=` handler, now runs
at priority `9998`; v2 `switch_to()` rejects a running
`latest_message_stream` after target lookup and before destructive work.
Production-path same-flush coverage uses the real history selector, raw input,
and a real `client=` Chat with explicit stream settlement and `Chat.destroy()`.
It proves source capture plus exact provider/public attachment data and target
preservation on rejection, and proves failed capture publishes neither input
channel while the target restores cleanly.

Gates: focused controller/chat regressions passed 5; `make py-check-format`
passed; `make py-check-types` reported 0 errors; `make py-check-tests
FILTER="history or transcript"` passed 43 Playwright and 452 non-browser tests;
`uv run pytest pkg-py/tests/playwright/ -k "history_edit"` passed 9; and
`make py-check` passed 200 Playwright tests plus 829 non-browser tests, with 1
skipped test and 20 established warnings.

Roborev outcome: `roborev close 1158` succeeded (`Job 1158 closed`) after the
code commit. Kata `shinychat#5r50` remains open with `needs-review`,
`work.attention="ok"`, and `work.branch="feat/history-exchange-tree"`; the next
action is orchestrator inspection and integration. `shinychat#6drf` remains
blocked and unstarted.

### P4.1 Roborev 1159 authoritative disposition (2026-09-01)

Mandatory batched Roborev job `1159` reviewed
`04825f1f3da2286008a6e1c8e7a475b33be2426f^..b99074b028d43687a8fa44bf97a5701fefffa7c1`
(canonical `39a61813f51ff1d99bcd6182aa7b61c968af773d..b99074b028d43687a8fa44bf97a5701fefffa7c1`).
Both findings are valid and in scope for `shinychat#5r50`.

1. **Initial programmatic v2 creation metadata: PATCH; valve not fired.**
   `_content_exchange()` must report whether it created the record. After the
   first successful durable persistence, `message_committed()` and
   `stream_started()` must each publish exactly one `history_update` for an
   initially created record. `stream_updated()` and `stream_finished()` remain
   metadata-free; streamed chunks stay eagerly durable without drawer
   publication. The required regressions use the `ChatTranscript` callbacks
   for both an initial complete-message path and an initial stream-start path,
   asserting the persisted record, exactly one metadata update, and no
   chunk/finish metadata.

2. **Stale switch target versus rename: DELETE/REPLACE; valve fires.**
   This is the third finding in the recorder-authority mechanism, following
   Roborev `1135`, `1152`, and now `1159`. Replace only the
   pre-lock-authoritative target snapshot. Keep the initial target lookup for
   eligibility and stream preflight; inside the existing destructive-admission
   boundary and recorder lock, save the source, reload the target as the
   authoritative record, preflight it, and restore that fresh record. Add no
   lock, owner, queue, CAS, or rollback mechanism.

The decisions trace to R2 continuity, R4 durable restore fidelity, and R7's
existing-primitives boundary. The deletion pass removes reliance on the
unlocked target snapshot while retaining the recorder, existing lock,
destructive admission, restore helper, and single-owner design. The
snapshot-store interleaving regression must hold the first target lookup,
complete a rename of the inactive target, release the stale lookup, switch,
and then capture; the installed and persisted target must retain the renamed
title. Preserve the reverse-direction source-rename interleaving, inactive
rename, and source-save-before-invalid-target coverage.

Implementation is stopped until this disposition is reviewed. Roborev `1159`
remains open and unclosed. Fully qualified Kata issue `shinychat#5r50`
remains open with `needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`. Fully qualified
`shinychat#6drf` remains open, blocked, and unstarted. No implementation,
test, review closure, issue closure, or sibling work is authorized by this
handoff.

### P4.1 authoritative implementation and evidence handoff (2026-09-01)

The Roborev 1159 dispositions are implemented and verified. Commit
`29c93d1603957160cae44f7be9ca045ed5f4339a` DELETE/REPLACEs only the pre-lock
switch target snapshot: under the existing destructive-admission and recorder
lock it saves the source, reloads the target authoritatively, preflights it,
and restores that fresh record. Its snapshot-store rename interleaving
regression proves the renamed target title is retained after the stale lookup,
switch, and capture.

Commit `8067459f8af44f62f34a1abf09400e7e5b1d9d3f` adds the initial programmatic
metadata patch. After first persistence, the initial message/stream paths each
publish exactly one metadata update; chunks and finish publish none. The
initial baseline has 3 controller tests. Focused units passed; format and
Pyright are clean; history/transcript passed 43 Playwright and 455 non-browser
tests with 9 warnings; `history_edit` passed 9 tests. Final `make py-check`
was Ruff/Pyright clean and passed 200 Playwright tests, 832 non-browser tests,
1 skipped test, and 20 warnings. `git diff --check` passed.

Independent Luna final read-only review found no findings. Roborev 1159 is
closed, and no fresh Roborev review was requested. `shinychat#5r50` remains
open with `needs-review`, `work.attention="ok"`, and
`work.branch="feat/history-exchange-tree"`; `shinychat#6drf` remains open,
blocked, and unstarted. History is preserved. No JavaScript, R, packaged
asset, bookmark, Phase 5, sibling, or task-closure work is included.

### P4.1 closure (2026-09-01)

Roborev 1161 passed with no findings for
`04825f1f3da2286008a6e1c8e7a475b33be2426f^..8067459f8af44f62f34a1abf09400e7e5b1d9d3f`;
the canonical range is
`39a61813f51ff1d99bcd6182aa7b61c968af773d..8067459f8af44f62f34a1abf09400e7e5b1d9d3f`.
The full gates were green: 200 Playwright tests, 832 non-browser tests, 1
skipped test, and 20 established warnings; format, types, and `history_edit`
also passed.

P4.1 acceptance is complete: the v2 active path restores display and
recorded/live turn state, continues through a real provider path, preserves
failed restore recovery and input-dispatch ordering, reloads switch targets
under recorder authority, and publishes initial programmatic metadata without
chunk/finish noise. Review findings were resolved within scope, with no
production or test work outside the accepted slice and no provisional
decision remaining. `shinychat#5r50` is closed. `shinychat#6drf` is the next
ready, unclaimed task; `shinychat#azvt` remains open with attention `ok`.

### P4.2 entry handoff (2026-09-01)

P4.2 is claimed. All required entry baselines are green: 43 Playwright plus
455 non-browser history/transcript tests, 9 `history_edit` tests, and
format/types. Investigation shows `history_edit` is v1-only and v2 has restore
but no edit/navigation coverage. Decision: retain positional client addressing
with no wire upgrade because there is no concrete red ambiguity. Next is the
v2 graph/rewind/sibling-resubmit vertical slice. No production/test/client
changes landed.

### P4.2 authoritative edit-projection authorization (2026-09-01)

This section is the current and authoritative P4.2 mechanism decision. It
supersedes the preceding `P4.2 parked escalation` authorization question and
the proposal there to extend completion-v1 broadly to edit/resubmit and
sibling navigation. The preceding sections remain historical audit trail;
they do not constrain this decision.

Garrick's decision unblocks edit/resubmit implementation. It supersedes the
prior proposal to reuse full display restore for edit and the earlier broad
completion-v1 authorization question. The revised edit projection is the
approved mechanism:

- For edit, delete server `clear_messages()` and retained-prefix display
  replay, and delete imperative `update_input(submit=True)` as the resubmit
  tail. Retain graph validation, attachment normalization, current-leaf
  close/capture, active-pointer rewind/persist, recorded-prefix state/turn
  rewind, the recorder lock, and the `f6396a39` server-side input block.
- The client sends edit with a request UUID and synchronously blocks every
  mutating action while it is held: normal submit, attachment-only submit,
  slash submit, edit, sibling navigation, switch, new, and delete. The
  writable unstaged composer draft and attachments remain available.
- A server-confirmed matching branch-projection action truncates display from
  the target index, appends the validated replacement through the standard
  `INPUT_SENT`/loading lifecycle, and dispatches exactly one raw accepted
  input. It must not consume or overwrite unrelated composer draft or
  attachments.
- Matching best-effort, non-masking `finally` completion handles validation,
  rewind, pre-admission error, and cancellation. A successful projection is
  handed to the standard submission and stream busy behavior. Stale or
  mismatched actions and completions are no-ops. Capability absence leaves
  v1 and R unchanged. Q3 stays positional; the request UUID is lifecycle
  correlation only, not an addressing or exchange-ID protocol.
- If post-mutation projection delivery fails, apply the existing
  fail-to-fresh-draft/incomplete-recovery contract rather than leaving mixed
  ownership; preserve the original outcome. Input-less targets are rejected
  before mutation.

The edit-projection wire and handoff are exact:

- `history_update.transition_protocol` evolves from `"completion-v1"` to
  `"completion-v2"` for capability-advertising Python v2 only. The browser
  continues to accept `"completion-v1"` for active New/Delete, but begins an
  edit transition only for `"completion-v2"`. Python v1 continues to emit
  `"completion-v1"` and R continues to omit the field, so neither changes
  edit behavior. An absent, unknown, or withdrawn value clears the one
  existing pending marker exactly as completion-v1 does; no second marker,
  owner, or edit-specific capability field is introduced.
- Extend the existing positional `sendMessageEdit()` request only with an
  optional `requestId`. A completion-v2 edit sends
  `{index, content, attachments, requestId, ts}`; legacy edits omit
  `requestId`. Python parses that field, and `_on_edit` owns the matching
  best-effort, non-masking `history_transition_complete {requestId}` in
  `finally`, including handled errors and cancellation. The request UUID
  still identifies only this lifecycle, never an exchange.
- After durable rewind/persist and recorded-prefix turn rewind succeed, the
  v2 request-ID path sends
  `history_edit_projection {requestId, index, content, attachments}` before
  its `finally` completion. `index` is the original positional user-message
  index; `content` and the always-present `attachments` array are the
  server-normalized replacement. A browser ignores the action unless
  `requestId` exactly equals its pending marker.
- Handling a matching projection synchronously sets the existing history
  store busy, truncates `state.messages` from `index`, dispatches the normal
  `INPUT_SENT` reducer action with the supplied replacement, and calls the
  normal raw-input transport once. It does not invoke the imperative
  `ChatInput.setInputValue(..., submit=True)` path, does not stage the
  replacement in the composer, and does not call `resetAll()` or
  `clearAttachments()`. The replacement's attachments belong only to
  `INPUT_SENT` and the raw-input payload; unrelated composer text and staged
  attachments are untouched.
- Projection dispatch and its raw transport send occur in the same
  browser-message callback before the next server action is processed.
  Python awaits the projection action before emitting the `finally`
  completion. Thus completion can clear the marker only after the normal
  loading state is installed; it cannot open a user-action gap. The standard
  history mutation predicate is
  `historyTransitionPending != null || state.inputDisabled ||
  state.streamingMessage != null`. `HistoryStore.busy` follows
  `state.inputDisabled || state.streamingMessage != null`, and every
  mutating path (select, New, rename, delete, edit, and sibling navigation)
  must consult that same predicate. The projection's synchronous busy set
  closes the render/effect gap before this standard state is observed.
- Completion releases only the transition marker. The ordinary accepted-input
  and stream lifecycle owns loading, provider output, cancellation, and
  response failure thereafter. A manual/no-provider submission that produces
  no terminal response retains the pre-existing normal loading behavior; the
  edit protocol must neither invent a second completion nor clear that state.
- A failure or cancellation before projection sends no projection action and
  only sends best-effort matching completion. A failure or cancellation after
  pointer mutation, including projection-send failure, invokes the approved
  `_clear_failed_restore()` fail-to-fresh-draft cleanup, preserves and
  re-raises the original outcome, and treats cleanup/notification failures
  as secondary. Its best-effort clear/metadata actions may be unavailable to
  a disconnected browser; that is the existing incomplete-recovery outcome,
  not permission to retain mixed ownership or add rollback.

Navigation is not locally projectable because the client lacks the sibling
path. Retain server replay/rewind for navigation and treat its lifecycle
guard and projection as a separate implementation unit; do not fold it into
edit. In particular, this edit unit does not add `requestId` to
`sendMessageNavigate()`, does not define a navigation projection action, and
does not alter the existing positional navigation request. Its later design
must separately specify how a selected sibling path is projected and when its
own request-correlated guard completes.

Commits `82ee43bf`, `e50ba734`, and `f6396a39` remain landed. The
`e50ba734` display-replay/`update_input` tail is now approved for replacement.
Implementation may resume on `shinychat#6drf` only. No later Phase 4 task may
start from this authorization, and no R server, Phase 5, bookmark, retry UI,
or legacy-import work is included.

The exact regression matrix is: leaf and non-leaf truncation; UI-only and
custom-prefix fidelity; replacement attachments; held edit blocks all
mutations while preserving draft; exactly one raw/provider dispatch;
projection-before-completion atomic handoff with no action gap; validation,
rewind, projection-send, error, cancel, no-provider, and no-output behavior;
stale UUID; completion-v1/absent/unknown/withdrawn capability behavior; and
input-less no mutation. Unit coverage must prove the normalized projection
payload never changes unrelated composer state. Browser coverage must hold the
edit before projection, attempt each mutating command, then verify the
replacement is the sole accepted input and the preserved draft/attachments
remain available for a later explicit submission.

This is a documentation/Kata authorization only. No Roborev review is needed
for this docs-only change.

### P4.2 edit-projection implementation handoff (2026-09-01)

Landed `e295befccac5ee7cee4e0a987aad79eceb07dca7`
(`feat(history): project v2 edits through normal input`, Kata:
`shinychat#6drf`) and generated-asset commit
`0134466100ab46f1528aa389f4bcb51a7d3d5680`
(`build(js): update history assets`, Kata: `shinychat#6drf`).

- Python v2 now advertises `completion-v2`; Python v1 retains
  `completion-v1`, and R still omits the capability. An edit carries an
  optional lifecycle-only `requestId`; the v2 handler validates it and emits
  exact, best-effort non-masking completion in `finally`. Rewind persists the
  parent pointer and recorded turns, then sends the normalized
  `history_edit_projection` instead of clearing/replaying display or using
  imperative `update_input(submit=True)`. Projection delivery failure uses
  the approved fail-to-fresh-draft recovery.
- The shared client store accepts only exact matching projections, makes the
  history state busy before reducer work, truncates at the positional target,
  installs normal `INPUT_SENT` loading state, and sends one raw input.
  Pending/loading blocks submit, edit, sibling navigation, select, New,
  rename, and delete; the unrelated composer draft and staged attachments
  stay untouched. Completion releases only the marker, leaving ordinary
  no-output/loading behavior to the standard input lifecycle. Navigation
  protocol and projection remain unimplemented.
- Focused JS/Python coverage covers v1/v2 and legacy capability behavior,
  exact/stale UUIDs, input-less and invalid targets, leaf/non-leaf rewinds,
  attachment normalization, projection-send recovery, finally
  error/cancellation non-masking, full client mutation blocking, one raw
  dispatch, and retained composer state. The pre-existing legacy Playwright
  fixture now uses `completion-v3` for its unknown-capability case because
  `completion-v2` is now recognized.

Verification: `make js-lint`; `make js-test` (1246 passed, 23 skipped);
`make js-build`; `make update-dist`; `make r-check-tests
FILTER='chat-history-hooks'` (22 passed); focused controller (11 passed) and
transition-handler (21 passed) tests; `make py-check-tests FILTER='history or
transcript'` (43 Playwright, 476 non-browser, 11 established warnings);
`history_edit` (9 passed); and `make py-check` (200 Playwright, 853
non-browser, 1 skipped, 22 established warnings). Format and Pyright were
green.

Production Playwright cannot deterministically hold then release this edit
transaction: while `_on_edit` is deliberately held before projection, Shiny
serializes the session and cannot run a fixture release input. No timer,
transport bypass, or test-only ordering mechanism was added. The unit and
integration coverage is the deterministic evidence for this slice; retain
this limitation for any future browser-harness work.

Next: `shinychat#6drf` remains open for the instructed review process; do not
request Roborev, close the task, or begin sibling navigation or later Phase 4
work. Boundary: no Q3 addressing change, R server change, retry UI, bookmark,
legacy-import, or Phase 5 behavior landed.

### P4.2 edit-projection review disposition (2026-09-01)

Independent review of `e295befc` plus generated assets `01344661` found three
valid, bounded Required issues. The three-findings escalation valve does not
fire: capability/mutation gating has two findings and edit-projection evidence
has one.

1. Any advertised `transition_protocol` change, including
   `completion-v2` to `completion-v1`, must clear the one pending transition
   marker. Add the exact in-flight v2 edit downgrade regression so a stale v2
   projection cannot remain eligible after capability withdrawal.
2. Gate ordinary `inputDisabled`-based history-mutation blocking to
   `completion-v2`. Python v1 and R retain their prior behavior; existing
   streaming and pending-transition protections remain unchanged.
3. Add a real, non-held Python-v2 browser edit happy path proving one raw
   input/provider dispatch, replacement attachments, and preservation of the
   unrelated composer draft and staged attachments. Shiny session
   serialization limits only the held-and-released browser case; it does not
   prevent this production path.

Implementation is stopped until these corrections land and pass focused JS,
Python, R compatibility, asset, browser, and full Python gates. Sibling
navigation remains unstarted, positional Q3 addressing remains unchanged, and
no later Phase 4 task is authorized.

### P4.2 edit-projection correction resolution (2026-09-01)

The three accepted corrections are complete:

- `4b3e337b` clears pending transitions on every protocol change and
  capability-gates ordinary `inputDisabled` history blocking to
  `completion-v2`, preserving Python v1 and R behavior.
- `013db8ee` adds the real Python-v2 browser edit path through rewind,
  projection, raw input, public callback, and provider exactly once.
- `95cac211` makes attachment preservation discriminating with distinct
  replacement and unrelated-draft files, asserting attachment identity at
  both the public callback and provider.

Generated assets are current in `39bdc334`. Verification passed JS lint,
build, and 1249 tests with 23 skipped; 22 R history-hook tests; format and
Pyright; 44 history/transcript Playwright plus 476 non-browser tests;
`history_edit` 9; and full `make py-check` with 201 Playwright, 853
non-browser, 1 skipped, and 22 established warnings. `git diff --check`
passed.

The capability and compatibility findings are resolved, and the production
browser path now proves unrelated composer attachment identity survives the
edit projection. P4.2 remains open with attention `ok`; sibling navigation
has not started. The next action is a batched Roborev review of this coherent
edit-projection slice.

### P4.2 Roborev 1163 disposition (2026-09-01)

Roborev `1163` reviewed `82ee43bf^..95cac211` (canonical
`3e346434..95cac211`) and returned two valid Medium findings in separate
submechanisms. The three-findings escalation valve does not fire.

1. **PATCH persistence failure recovery.** Move active-pointer mutation and
   `_persist_record()` inside the existing resubmit recovery `try`. A store
   failure after in-memory rewind must invoke the approved
   fail-to-fresh-draft/incomplete-recovery path rather than leave the recorder
   rewound while display and turns remain old.
2. **PATCH page-owned control gating.** The external/page-owned history entry
   must pass `history.busy || history.historyTransitionPending !== null` to
   its controls, matching the chat-owned container. Add a discriminating test
   proving New, select, rename, and delete are disabled during a pending edit
   rather than silently discarded by store guards.

Roborev `1163` remains open pending the fix commits. `shinychat#6drf` and
`shinychat#azvt` remain attention-blocked; sibling navigation and later Phase
4 work remain unstarted.

### P4.2 Roborev 1163 resolution (2026-09-01)

The accepted findings are fixed in `f553fe9b` and `3fc5a562`; generated assets
are current in `c7738cef`.

- Resubmit pointer mutation and persistence now run inside the existing
  recovery `try`. The injected store-failure regression proves the original
  error propagates while recorder ownership, active ID, turns, transcript,
  greeting, metadata, and notification settle to the approved fresh-draft
  outcome.
- Page-owned history now treats a pending transition as busy. Its focused
  test proves New, select, rename, and delete controls are disabled during an
  edit transition.

Verification passed 1250 JS tests with 23 skipped, JS lint/build/update-dist,
22 R history-hook tests, 44 history/transcript Playwright plus 477 non-browser
tests, `history_edit` 9, and full `make py-check` with 201 Playwright, 854
non-browser, 1 skipped, and 22 established warnings. Format, Pyright, asset
equality, and `git diff --check` passed. Roborev 1163 is closed; a fresh
batched review of the amended edit-projection slice is required before
sibling navigation begins.

### P4.2 Roborev 1164 disposition (2026-09-01)

Roborev `1164` reviewed `82ee43bf^..c7738cef` and returned one valid Medium
finding. A matching edit projection may contain server-normalized replacement
attachments even when the current composer has `enableUpload=false`; the
client must send the composite raw-input payload whenever projected
attachments are present rather than dropping them through the plain-text
transport. Add a discriminating projection test for this exact case.

This is a bounded PATCH in the existing edit attachment-transport mechanism;
the three-findings escalation valve does not fire. Roborev 1164 remains open
pending the fix. P4.2 and its parent remain attention-blocked, and sibling
navigation remains unstarted.

### P4.2 Roborev 1164 resolution and navigation handoff (2026-09-01)

The accepted attachment-transport finding is fixed in `b9a31e86`; generated
assets are current in `ac8338de`. A matching edit projection now sends the
composite raw-input payload whenever projected attachments are present,
including when composer uploads are disabled. The focused regression
discriminates this path.

Verification passed 1251 JS tests with 23 skipped, JS lint/build/update-dist,
22 R history-hook tests, 44 history/transcript Playwright plus 477 non-browser
tests, and full `make py-check` with 201 Playwright, 854 non-browser, and 1
skipped. `git diff --check` passed. Roborev 1164 is closed.

Driver decision: the edit-projection review chain has reached diminishing
returns after its accepted findings were fixed and verified. Do not request
another batched range review before continuing P4.2; later coherent-unit
reviews may surface any remaining actionable issue. Attention returns to
`ok`.

Next: implement sibling navigation as the separate unit reserved by the edit
authorization. It must replay the selected sibling path, persist
`active_leaf` and `selected_child`, restore the exact recorded turn prefix,
and define its lifecycle guard/projection without changing positional Q3
addressing absent concrete red evidence. Do not begin `shinychat#72ee` or any
later Phase 4 task.

### P4.2 sibling-navigation authorization (2026-09-01)

Sibling navigation reuses the one `completion-v2` transition marker but not
the edit projection. This is the reserved navigation-specific decision from
the edit authorization:

- For `completion-v2` only, the browser synchronously allocates the existing
  request UUID before sending navigation, preserving the composer draft and
  staged attachments while the shared mutation predicate blocks submit,
  edit, navigation, switch, New, rename, and delete.
- Extend the existing positional navigation payload only with optional
  `requestId`. The UUID is lifecycle correlation, not exchange identity.
  Python v1 and R continue to send and handle request-less navigation exactly
  as before.
- The Python v2 handler validates the target and request UUID, enters the
  existing recorder/destructive-mutation boundary with live input blocked,
  selects the sibling path, persists `active_leaf` and `selected_child`,
  clears and replays that server-owned path, and applies the exact recorded
  prefix through the rewind hooks. Existing replayed message actions plus
  `history_update` are the navigation projection because the browser does not
  own the selected sibling transcript.
- Validate the adjacent sibling, remembered subtree leaf, complete selected
  path, and rewind state before destructive mutation. A failure after pointer
  mutation or display clearing uses the approved
  `_clear_failed_restore()` fail-to-fresh-draft/incomplete-recovery contract,
  preserving the original error or cancellation; it does not attempt
  rollback to the prior sibling.
- Do not add `history_navigation_projection` or another marker/owner.
  `_on_navigate` owns matching, best-effort, non-masking
  `history_transition_complete {requestId}` in `finally` after success,
  handled error, or cancellation. Stale or mismatched completion remains a
  no-op.
- Retain positional Q3 addressing unless the predecessor/v2 browser suite
  produces concrete ambiguity. Do not add queues, rollback, timers, an
  exchange-ID wire upgrade, R server behavior, retry/status UI, bookmarks,
  or Phase 5 recovery behavior.

Required evidence covers both directions and boundary no-ops, persisted
`active_leaf`/`selected_child` across reload, exact turn-prefix rewind,
UI-only/custom-prefix replay fidelity, held navigation blocking every
mutation while preserving draft/attachments, success/error/cancellation
completion, stale UUID behavior, and Python v1/R compatibility. A real v2
browser path must prove the selected sibling transcript and subsequent model
turn continue from that sibling exactly once.

### P4.2 sibling-navigation review disposition (2026-09-01)

The navigation slice landed in `786861a8`, with browser assertion correction
`bc2c6d8e` and current generated assets `50ffc0cc`. Independent review found
no production defect or v1/R compatibility regression, but identified two
required evidence gaps in separate submechanisms; the three-findings valve
does not fire.

1. Add a real v2 sibling tree with remembered descendants and exercise both
   directions plus both boundary no-ops. Assert persisted `active_leaf` and
   changed `selected_child` pointers, replayed display, and exact rewind turn
   prefix.
2. Exercise the real v2 navigation recovery path after mutation rather than
   only mocking the handler wrapper. Inject persistence failure and
   replay/rewind cancellation; prove the original outcome survives and the
   approved fresh-draft cleanup resets recorder ownership, active ID,
   transcript, and turns. Retain matching completion evidence at the handler
   boundary.

This is a test-only correction unless a discriminating regression exposes a
production defect. Stop and escalate before changing the authorized mechanism
or production behavior. Sibling navigation is not complete until this
evidence is green; `shinychat#72ee` remains blocked.

### P4.2 sibling-navigation resolution (2026-09-01)

The accepted evidence correction landed in `8870b215` without a production
change. It covers remembered descendant selection in both directions, both
boundary no-ops, persisted `active_leaf`/`selected_child`, custom-prefix
display replay, exact turn prefixes, persistence failure, and cancellation
after real replay and real rewind.

Verification passed the six focused navigation tests, 205 controller tests,
45 history/transcript Playwright plus 491 non-browser tests, and full
`make py-check` with 202 Playwright, 868 non-browser, and 1 skipped. Ruff,
Pyright, and diff checks passed. Targeted independent re-review returned PASS.

P4.2 is complete. The edit and navigation paths retain positional Q3
addressing because no concrete ambiguity appeared. Python v2 uses the one
`completion-v2` lifecycle marker; v1 and R compatibility remain unchanged.
The driver-directed review policy applies: after accepted findings, full
verification, and targeted PASS, do not add another range review for this
unit. Any remaining actionable issue can surface in review of a later
coherent unit.

Next: unblock `shinychat#72ee` for the Phase 4 retry affordance and tested
regenerate path through the existing sibling primitive. Bookmark, Phase 5,
R-server, legacy-import, queue, cursor, reconciliation, and Q3 wire expansion
remain out of scope.

### P4.3 retry/regenerate resolution (2026-09-01)

P4.3 landed in `9c68e3bb`, with generated assets in `6cf8b4da` and a
formatter-only import-order correction in `202fdfc4`.

- V2 restore projects ephemeral status/retry metadata only onto input-bearing
  restored user messages and exposes no stored error detail.
- Restored pending/interrupted, error, and cancelled exchanges render the
  accessible Retry affordance, including the no-assistant-message case.
  Retry reuses the exact `completion-v2` lifecycle, is revalidated by the
  server, and enters the existing defensive-copy sibling primitive. The old
  node and partial display remain unchanged.
- The production controller regenerate path uses the same sibling primitive
  without adding Phase 4 regenerate UI. Python v1 and R remain unchanged.

Verification passed 1256 JS tests with 23 skipped, JS lint/build/update-dist,
22 R history-hook tests, 269 focused controller/history tests, 6 v2 restore
Playwright tests, and full `make py-check` with 203 Playwright, 881
non-browser, and 1 skipped. Packaged assets match `js/dist`.

Independent review returned PASS with no findings. Its residual composition
gaps (partial-assistant browser retry and retry-specific attachment copying)
are already exercised at the underlying capture/resubmit boundaries and do
not justify duplicative hardening. Per the driver-directed stopping rule, do
not request another range review for this green unit.

P4.3 is complete. Next: unblock `shinychat#g6tt` for the pointer-only Python
bookmark slice. Phase 5 degradation/error detail, R server work, client
transcript ownership, queues, cursors, reconciliation, and Q3 expansion remain
out of scope.

### P4.4 bookmark-pointer resolution (2026-09-01)

P4.4 landed in `6b459a76`.

- V2 server bookmarks contain exactly one atomic
  `{conversation_id, node_id}` pointer captured under the recorder lock, with
  no transcript, turns, rendered content, or other fidelity data.
- Restore validates record and node before destructive mutation, then selects
  and persists the target path through the existing v2 restore transaction.
- Recorder-owned `bookmark_state_id` settlement is serialized under the same
  lock, rejects late/stale pointers, persists before publishing, and returns
  replaced state IDs for cleanup. Eager v2 history persistence remains
  independent of bookmark settlement.
- Browser/URL modes remain conversation-only pointers. Missing records or
  nodes visibly fail to a fresh draft without a partial switch.

Verification passed format and Pyright, focused bookmark/v2 tests, and full
`make py-check` with 204 Playwright, 888 non-browser, and 1 skipped.
Independent review returned PASS with no findings. Its residual browser/unit
assertion split and non-concurrent callback scheduling match the existing
layered coverage and serialized settlement pump; they do not warrant another
hardening round or range review.

P4.4 is complete. Next: unblock `shinychat#pvjx` for Phase 4 acceptance,
production-path matrix verification, scope/deletion review, and final review
disposition. Do not begin Phase 5 or any R-server/legacy work.

### P4.5 acceptance/deletion review disposition (2026-09-01)

The final adversarial architecture and scope review found no production
defect. The acceptance runner passed every criterion except one bounded
evidence gap: restored error retry has a real browser path, but restored
pending and cancelled exchanges with retained partial assistant display have
not been exercised through retry into a new sibling while proving the
original node remains unchanged.

Add discriminating production-controller evidence for pending and cancelled
partial-display retry. It must restore the retained partial display, retry
through the existing sibling primitive, prove the original node is immutable,
and prove the replacement sibling continues from the parent prefix. This is a
test-only correction unless red evidence demonstrates a production defect;
stop before changing production behavior.

Deletion pass:

- one active v2 record owner: `_ExchangeRecorder.record`;
- one client lifecycle marker: `historyTransitionPending`;
- one destructive history transaction:
  `Chat._destructive_history_mutation()`;
- one branch-producing primitive: `resubmit()`;
- three approved state-hook registries: capture, restore, and rewind.

No mechanism can be deleted without removing an approved requirement.
`bookmark_state_id` remains necessary for server-bookmark URL settlement and
replacement cleanup. No queue, cursor protocol, reconciliation pass,
rendered-HTML history storage, CAS, second v2 owner, detailed Phase 5
degradation/error UI, R server port, or legacy import entered Phase 4.

All other acceptance criteria and full gates are green. `shinychat#pvjx` and
`shinychat#azvt` remain attention-blocked until the bounded evidence
correction passes targeted review.
