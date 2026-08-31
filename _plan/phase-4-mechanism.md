# Phase 4 mechanism: restore, branching, and bookmark pointer (Python)

**Status:** P4.0 complete; human review pending 2026-08-31
**Phase:** plan.md §4, Phase 4
**Kata:** parent `shinychat#azvt` under epic `shinychat#6d0d`
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

The task's 2026-08-28 conflict recipe is evidence, not an executable recipe:
both heads have advanced and Phase 3 is complete. Re-run the merge/dry-run
analysis against current `main` and `feat/history-exchange-tree`, then update
`shinychat#ykxh` before resolving conflicts. Preserve its semantic decisions:

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

0. **Conversation-ID integration gate (`shinychat#ykxh`).** Merge current
   `main`, re-derive the stale conflict recipe, settle v2 identity ownership,
   and pass the full Python gate.
1. **Keystone restore + continuation (`shinychat#5r50`, blocked by
   `shinychat#ykxh`).** Add v2 read/activation, display replay, restore hooks,
   turns materialization, baseline reset, and a continued-turn integration
   test.
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

Each child is a coherent review unit and remains open for human review. The
note is approved; P4.0 is complete and the restore keystone remains blocked pending human review and closure of `shinychat#ykxh`.

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
implementation. Job `1079` remains open and unclosed, and
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
