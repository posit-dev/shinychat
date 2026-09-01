# Phase 4 mechanism: restore, branching, and bookmark pointer (Python)

**Status (current and authoritative):** P4.0 complete; the P4.1 Roborev 1135
DELETE/REPLACE unit is implemented, but its corrected handoff is stopped
pending note review. `shinychat#5r50` remains open with `needs-review`,
`work.attention="blocked"`, and `work.branch="feat/history-exchange-tree"`;
`shinychat#6drf` remains open, blocked, and unstarted; and
`shinychat#azvt` remains open with `work.attention="ok"` (2026-08-31).
**Phase:** plan.md §4, Phase 4
**Kata (current):** child `shinychat#5r50` is open with
`needs-review`, `work.attention="blocked"`, and
`work.branch="feat/history-exchange-tree"`; successor `shinychat#6drf` is
open, blocked, and unstarted; parent `shinychat#azvt` is open with
`work.attention="ok"` under epic `shinychat#6d0d`
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
is closed; `shinychat#5r50` is the current claimed keystone, while later
children remain sequenced behind it.

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

### P4.1 Roborev 1135 DELETE/REPLACE implementation (2026-08-31)

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

### P4.1 Luna independent read-only review disposition (2026-08-31)

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
