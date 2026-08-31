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
Next: complete normal integration/review handling for the accepted roborev 1067 fix; `shinychat#5r50` remains blocked and not begun.
Boundary: no production or test code changed in this handoff; OTel scalar overlap, the init/restore race, and Phase 5 guards/degradation/audit remain deferred.

### Roborev 1067 handoff (2026-08-31)

Accepted findings are covered by the existing uncommitted bounded fix. In v2,
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
review is accepted and this bounded fix is verified, pending its normal
integration/review handling. `shinychat#5r50` remains blocked and not begun.
