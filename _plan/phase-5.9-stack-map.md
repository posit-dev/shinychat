# Proposed Python review-stack map

**Status:** preparation proposal, not approved reconstruction. Static dependency/test inspection only: no intermediate trees, builds or runtime tests in this preparation. Construction experiments require driver approval and a validated reference incorporating the resolved modal prerequisite.
**Task:** Phase 5.9 `shinychat#f9hc`; independent main-based prerequisite `8ej9`; R gate `05vb`.
**Contract:** [phase-5.9-mechanism.md](phase-5.9-mechanism.md). The completed stack merges together, but each PR tip must be buildable and verified against its actual predecessor.

## Snapshot and inventory

Analysis compares source `b382c176985e71754457372fc6ee21b37f5dea2a` with provisional base `0bf2364a7d7612d7381bf641c7556fccfca3e233`, not moving refs. Planning commit `93e82051` changes documentation/guidance, not runtime source. This preparation has not fetched upstream or integrated it.

**Independent prerequisite handoff:** `8ej9` is now CLOSED; its main-based fix landed as `2fa02a27` (PR #430). Local origin/main now points there, and its tree matches the recorded CI-green PR head `c6ac0d9f` (verified by local tree IDs). Only the modal test changed relative to the provisional base. Pin/integrate/verify updated main and regenerate the inventory before construction; do not silently replace the snapshot pair behind the counts below.

[phase-5.9-change-inventory.csv](phase-5.9-change-inventory.csv) accounts for every path in that two-tip comparison:

| Inventory category | Files | Added lines | Removed lines |
|---|---:|---:|---:|
| Python source | 14 | 5,540 | 1,352 |
| JS source | 13 | 479 | 52 |
| Tests and fixtures | 119 | 25,190 | 3,238 |
| Generated assets | 14 | 251 | 251 |
| Working artifacts | 15 | 8,615 | 0 |
| Build configuration (Makefile) | 1 | 4 | 0 |
| Public documentation (Python CHANGELOG) | 1 | 16 | 0 |
| **Total** | **177** | **40,095** | **4,893** |

The 15 `_plan/` and effort-local `.agents` paths do not enter the stack. The CSV's per-path proposed ownership distinguishes shared/hunk-split files; it does not prove a cut is green. Generated one-line bundles make line counts a poor estimate of asset review size.

The scoped `AGENTS.md` asset guidance introduced by preparation is a separate approved guidance delta, absent from the older snapshot CSV. Carry it with the first JS/Python asset level and include it when regenerating the validated-reference inventory. Do not transplant preparation `_plan/` or handoffs alongside it.

All 542 source-only commits in this fixed comparison have Garrick Aden-Buie as author. Preserve authorship and existing contribution credits; keep representative old-to-new evidence mapping on the task. Do not turn historical commit order, private task IDs, or review numbers into reviewer-facing subjects.

## Recommended chain

```text
pinned main (after modal resolution)
  -> history-tree/records
  -> history-tree/transcript
  -> history-tree/exchange-history
  -> future R-port / legacy-docs segments
```

These are proposed exact branch slugs under the approved prefix. No branches have been created. Archive/integration reference names and exact base/source SHAs are chosen when freezing the reference.

### Why three layers, not the original four concerns

- Explicit record models and the pure importer have independent verification surfaces, so they can precede live history cutover.
- The new transcript module imports chat primitives, not the history controller/recorder. That permits a transcript-first staging proposal; actual legacy capture/save compatibility is a required experiment, not a proven consequence of the import graph.
- Recorder, state plans and controller share one concrete host and are tested through controller paths. Do not create a placeholder host or a second engine merely to split them.
- The final store returns both record versions. Installing it under the old controller would require an intermediate type-narrowing guard. Reject that packaging mechanism: keep the legacy store in the first two layers and change it with its live consumer.
- Client protocol plumbing can precede activation, but the HTML protocol seed, server admission decision, disabled-history release and transition completion sender must arrive together.
- Historical browser snapshot deletion is net-zero against this base. Do not reconstruct that discarded branch mechanism or describe it as a new PR change.

## PR 1 — Record models and released-form import

**Branch:** `history-tree/records`; base: pinned main.
**Reviewer question:** Are exchange records and the pure legacy import faithful, without changing the active legacy history engine?

### Production and fixture hunks

- `_history_types.py`: give the existing record its final explicit name `ConversationRecordV1`; add explicit `ConversationRecordV2`, exchange/state/captured-message types, graph helpers and safe error constants. Move `TurnDict` here atomically with its client import.
- Retain the released `ConversationRecord` meaning as `ConversationRecord = ConversationRecordV1` until PR 3. This is preservation of the existing public entry point, not a new flag or API. Defer the current-version subclass, `_upgrade_v1`, `_is_v1_shaped`, its version-tracking comments and corresponding tests.
- Preserve the legacy `MAX_SCHEMA_VERSION` acceptance until PR 3. Explicit V2 model construction/import is testable without advertising V2 to the still-legacy store/controller. Any generic schema-gate test expecting V2 acceptance also waits.
- `_chat_types.py`: only shared record/captured-message prerequisites; protocol and transcript-facing hunks may follow in PR 2. Typed declarations that are shared by both can land here once.
- `_history_client.py`: shared `TurnDict` re-export, mapping-key validation, JSON model-turn serialization and system-prompt-inclusive adapter capture. Preserve its default signature behavior; verify the deliberate serialization tightening with the client tests.
- `_history_v1.py`: final pure importer and its warning-return contract. No controller import and no session/store side effects.
- `types/__init__.py`: explicit V1/V2 export additions, but defer the comment promising that unversioned `ConversationRecord` tracks/upgrades to V2.
- `_history_test_helpers.py`: only final pure `branch_from`; do not add its `HistoryController` import or `replay_exchange_record` yet.
- Shared released-writer import matrix and R fixture copy. Against `0bf2364a`, the Makefile additions are exactly the copy pairs for `history-v1-import-matrix.json` and `history-turn-rewrite-matrix.json`; neither canonical file exists at base. PR 1 adds only the import source/copy and its cp pair. PR 3 adds the turn-rewrite source/copy and its cp pair. Existing behavior/store copy pairs stay unchanged.
- Shared unreplayable-value store fixture and matching V1-only Python/R persistence tests may land here: they exercise existing storage, not the future V2 store API.

**Keep unchanged:** active legacy controller/wiring/store, live recorder, bootstrap, bookmark switching, generic record upgrade-on-read and V2 writes. Do not wholesale-copy final `_history_store.py` or the alias-upgrade test tail.

### Semantic commit sequence

1. `refactor(history): name legacy records explicitly and share turn types`
   - Versioned naming/re-export and existing-test adjustments; keep the public alias on V1.
2. `feat(history): add exchange record models and validated turn serialization`
   - Explicit V2 data model, client adapter changes and their direct tests.
3. `feat(history): import released conversation records into exchange trees`
   - Pure transform, warning tests, released-writer matrix and its fixture copy.

Implementation and decisive tests belong in the same commits. The sequences are suggestions, not permission to move failing tests into later commits to conceal an incomplete change.

### Test pairing and intermediate contract

- `test_history_types.py`: V1/V2 model/graph tests, not `test_conversation_record_names_the_current_version` or the unversioned-upgrade test family.
- `test_history_client.py`: mapping validation and turn serialization.
- `test_history_import_matrix.py`: pure importer and released forms; its production FileConversationStore reads remain V1. Check against the actual legacy store, not a bypass.
- `test_history_store.py`: retain baseline coverage; only stage the V1 fixture/name-adjustment hunks here. V2 store tests and worked-example store roundtrips wait for PR 3.
- R store fixture test: roundtrip opaque data on unchanged R implementation/assets.

The public alias and active store remain legacy-compatible. Class names and literal schema validation are observable in errors/introspection; verify rather than calling the class rename behaviorally invisible.

## PR 2 — Transcript ownership and dormant client protocol

**Branch:** `history-tree/transcript`; base: `history-tree/records`.
**Reviewer question:** Does server-owned transcript/stream lifecycle work with existing history/bookmarks, while new client protocol handling stays unactivated?

### Production hunks

- `_chat_transcript.py`: final transcript/stream identity, reservation, commit/rollback, terminal state and capture-callback surface; callbacks remain unregistered by the legacy history runtime.
- `_chat.py`: transcript-backed `messages()`, accepted input ordering, complete/stream append lifecycle, synchronous reservation, cancellation/failed-end recovery, response settlement, destructive mutation, bookmark snapshot/replay and teardown.
- Defer every `_history_action_admitted()` call, its warning/suppression behavior and the legacy-facade readiness adaptation to PR 3. This is a line-level split: retain transcript transaction/reservation/capture flow surrounding the guard in `_append_complete_message`, stream entry/chunk paths and accepted-input methods; defer only the admission expression and its rejection/warning branch. Do not omit a whole mixed hunk or invent an always-allow readiness stub. The host retains baseline ungated initialization until live server/client admission cutover.
- Defer `_init_chat` disabled-history updates, `_withdraw_unavailable_history_seed`, its effect registration and the `chat_ui` completion-v2 attribute to PR 3. Split the shared initialization hunk: transactional initial append belongs here; seeded-client release belongs there.
- `_chat_types.py`: remaining transcript status/error and wire typed declarations.
- JS transport types/history store/state: new action/payload shapes and transition/projection handling; retain the existing non-completion path.
- JS ChatApp/input/message/drawer components: new protocol handlers and testable UI primitives, but defer automatic seed in `chat-entry.ts` and any unconditionally changed legacy busy-control hunks to PR 3 if they cannot retain baseline behavior. Do not claim every JS change is dormant: legacy controls must be verified explicitly.
- Defer `shiny-transport.ts`'s `sendInput` event-priority change to PR 3, paired with projection resubmission evidence. It is an actual surviving delta, not a consequence of removing a baseline browser echo.
- Retry/error styles can land with their component primitives; the server emits no exchange metadata yet.
- Scoped AGENTS asset guidance, JS dist and Python www copies; R served assets remain exactly the pinned upstream bytes.

### Semantic commit sequence

1. `feat(chat): own transcript messages and stream reservations on the server`
   - Transcript module, host storage/read/send paths and production-path transcript tests.
2. `fix(chat): serialize stream completion and destructive mutations`
   - Terminal recovery, settlement, bookmark/clear/teardown and their regressions; retain existing contribution credits for stream reservation fixes.
3. `feat(chat): add completion and projection protocol primitives`
   - JS/wire shapes, state/transition handlers and isolated client tests without automatic activation.
4. `chore(chat): distribute the transcript client bundle to Python`
   - Build JS then copy to Python; include the source/asset consistency proof and unchanged R-tree check in this PR.

### Test pairing and intermediate contract

- `test_chat_transcript.py`, `test_message_transcript_matrix.py`, `tests/shared/message-transcript-matrix.json` (Python-only; no R copy).
- `pkg-py/tests/pytest/test_chat.py`: transcript/accepted input/stream/bookmark/settlement hunks. Keep final initial-admission/V2 integration tests for PR 3; retain remaining baseline tests rather than replacing the file blindly.
- `test_chat_history.py` and old controller tests: only host-API/fake adjustments required to preserve their existing legacy coverage. Do not install the final controller test module yet.
- Changed JS suites: state, store, transport, ChatApp integration, input/message/drawer. The automatic chat-entry seed/test hunk waits for PR 3; transport priority assertions move with that changed behavior. Protocol handlers may be tested with their normal mock transport; don't suppress legacy-path failures.
- R protocol/legacy history integration assertions: verify unchanged R still uses its old server protocol and pinned served assets.

No seeded completion-v2 state or automatic V2 persistence exists here. Preserve the base `ChatHistory._start` reactive `_save_on_response` effect (`@reactive.event(chat.messages, ignore_init=True)`); it calls the old `HistoryController.on_response`, which reads `adapter.get_turns_grouped()` and `chat._messages_for_bookmark()`. PR 2 must preserve the reactive dependency through `_transcript_revision` in `messages()` and the wire-spec shape from `_messages_for_bookmark()`, not replace that consumer with settlement registration early.

Named retained legacy checks include `test_on_response_no_new_data_does_not_overwrite_saved_values`, `test_replay_rereport_does_not_resave_or_truncate`, `test_replay_rereport_then_new_turn_does_not_duplicate_ui`, and `test_switch_to_swaps_in_session` from the pinned base controller suite. Run those plus the base history/bookmark browser flows on the constructed PR 2 tree. Their survival through the actual reactive save path is a named pre-approval experiment; if it needs a new legacy adapter/guard, collapse PR 2 into cutover. Deliberate stream/settlement behavior changes are disclosed and tested here; initialization suppression waits for PR 3.

## PR 3 — Live exchange-history cutover

**Branch:** `history-tree/exchange-history`; base: `history-tree/transcript`.
**Reviewer question:** Does the complete engine persist and restore exactly what was captured, with faithful legacy import, coherent branching, and correct failure/admission behavior?

### Atomic production group

- Final `_history_plan.py`, `_history_recorder.py`, `_history_controller.py` and `_history.py` wiring/strategy/transition effects; capture and settlement registrations arrive with their concrete controller host.
- Final dual-version `_history_store.py`; activate schema acceptance and lazy conversion at the same level as its consumer.
- `_history_types.py`: replace retained V1 alias with the final current-version `ConversationRecord` subclass/validator and markerless-shape handling. Finish the version-tracking export comments/tests.
- `_history_title.py`: final helper/retitle behavior; delete `fallback_title` only after its old-controller caller is retired.
- `_chat.py` admission/suppression guards, initial authoritative enabled/disabled updates and HTML protocol seed; `_chat_client.py` pending-history New-chat guard.
- JS `chat-entry.ts` seed, activation/control hunks and event-priority projection resend. Keep the seed, server completion sender and disabled-history release in one PR.
- Remove the legacy live engine; retain only compatibility record/import/storage input required by the final design. Do not introduce a runtime-selection flag.

### Semantic commit sequence

1. `feat(history): plan exchange state capture and rewind`
   - Plan/recorder final structures and controller-path tests in the complete cutover unit; don't publish them as an unwired PR.
2. `feat(history): restore and branch through the exchange controller`
   - Controller, dual-version stores, current-version validation, lazy read upgrade and their direct tests.
3. `feat(history): wire initial admission and completion-aware actions`
   - Facade, host/client activation, disabled-history release and forged/held-initialization regressions.
4. `feat(history): restore bookmark state without reloading conversations`
   - Restore-mode hooks, legacy bookmark pointer, browser assertions and input-state contract.
5. `test(history): pin turn rewrites and released-record recovery`
   - Shared turn fixture/copy target, cross-session/failure acceptance and retained test-only helpers; related tests also accompany the earlier implementation commits.
6. `chore(chat): distribute the exchange-history client bundle to Python`
   - Per-level assets, scoped exclusions and source equivalence evidence.

These are review steps inside ONE atomic cutover PR. CI is required at the PR tip; none of its subcommits is a separately publishable recorder/plan layer. Prefer moving already-complete tests into their implementation commit over a blanket final test dump.

### Test pairing and intermediate contract

- Complete `test_history_controller.py` and controller-dependent helper tail.
- Final `test_chat_history.py`, `test_history_legacy_bookmark.py`, `test_history_turn_rewrite_matrix.py`, title/store tests and current-version model-upgrade tail.
- Final affected pytest host tests and every new/changed history/bookmark Playwright app/spec; c87g/tn7c fixes retain their assertions.
- V2 worked-example fixture/store tests; shared turn-rewrite matrix + R copy + its Makefile copy pair.
- Full public CHANGELOG history migration/admission/restore entries. Keep reservation bug-fix entry with PR 2. Version-specific API-reference expansion belongs to existing Phase 7 docs scope, not a new prerequisite mechanism.

The client never seeds completion-v2 without a server that completes transitions and publishes the initial history decision. History-disabled chats must release their conservative seed. R keeps the old served bundle and protocol; this is not the R port.

### Decisive cutover review routes

| Reviewer question | Existing source tests to read/run with the owning changes |
|---|---|
| Can preflight or rewind failure mutate the live/persisted path? | Controller `test_v2_restore_preflight_failure_leaves_live_state_untouched` and `test_v2_navigation_rewind_hook_failure_keeps_persisted_leaf` |
| Does retry preserve a failed exchange and create the right sibling? | Controller `test_v2_retry_restores_partial_exchange_before_creating_sibling`; browser `test_v2_restored_failure_retries_through_the_real_provider` |
| Can seeded input/actions race the initial decision, including disabled history? | Chat-history `test_history_disabled_publishes_one_initial_withdrawal` and `test_v2_initial_readiness_rejects_direct_input_without_mutation`; browser `test_v2_restore_holds_retry_edit_and_navigation_until_history_release` |
| Are import losses surfaced without repeatedly warning on valid legacy records? | Controller `test_lossy_v1_import_warns_once_per_session_per_conversation`; released-writer importer matrix |
| Does bookmark switching stay in place yet reload the correct saved target? | Browser `test_v2_bookmark_switch_updates_url_in_place_and_reload_restores_target` and history-bookmark input-state suite |

These are navigation anchors in the source snapshot, not evidence that reconstructed levels already passed them.

## Verification matrix and collection rules

Commands below are proposed execution gates, not results from this preparation. Run `make help` first. `FILTER=...` is pytest keyword selection, not a file path or `make -k`; filters do not prevent import-time collection failures.

| Level | Focused construction checks | Before declaring the level verified |
|---|---|---|
| Records | `make py-check-unit FILTER='history_types or history_client or import_matrix or history_store'`; `make py-check-types`; `make py-check-format`; `make r-check-tests FILTER=chat_history_store` | Full unfiltered `make py-check`; `make r-check`; applicable CI at recorded exact SHAs |
| Transcript | `make js-lint`; `make js-test`; `make py-check-unit FILTER='chat_transcript or message_transcript_matrix or test_chat or history'`; `make py-check-playwright FILTER='bookmark or history or message_stream_context or auto_cancel_core'` | Full unfiltered `make py-check`; `make r-check`; applicable JS/py/R CI; Python asset and R pin checks |
| Cutover | `make py-check-unit FILTER=history`; `make py-check-playwright FILTER=history`; `make py-check-types`; `make py-check-format`; `make js-lint`; `make js-test` | Full unfiltered `make py-check`; `make r-check`; applicable JS/py/R CI; final-tree comparison |

- JS Make targets have no supported filter; run their complete suites.
- `py-check-types` covers configured pkg-py scope INCLUDING tests. Do not repeat the earlier narrower local gate mistake.
- The first helper stage contains only `branch_from`; the controller import/replay helper arrives at cutover. Turn-rewrite tests import controller test fakes; legacy-bookmark tests import chat-history helpers; the final conversation-ID test module imports the new controller. Keep those final imports/assertions with their dependencies, retaining baseline modules or staging only required legacy-host fake adjustments earlier. Preserve newer main's session hooks rather than copying the old snapshot over them.
- At each fixture level, stage only copy commands for existing canonical inputs and run `make r-sync-fixtures`. R fixture copies can advance; R SERVED ASSETS cannot. The JS CI fixture-sync gate needs all files named by that intermediate target.
- Current JS CI rebuilds js/dist and synchronizes R fixtures; it neither copies nor proves Python www freshness. No observed gate compares Python and R served bundles. Verify Python built-file copies directly, excluding only the expected Python provenance stamp; verify every R asset including its stamp against the pinned base.
- Do not install new guards/counters/CI machinery just to enforce the map: record reproducible per-level checks/evidence using the existing targets and ordinary git/file comparisons.
- The main-based modal correction is resolved, but it must still be present in the validated integration reference. Do not retry away its failure or carry its previous waiver into these gates.

## Recomposition proof and approval gates

Before reconstruction, record archive/integration references and regenerate the inventory against the validated source. The final difference manifest allows only omitted working documents, R served assets held at pinned base, and explained reconstructed provenance stamps. No blanket exemption for bundles or source maps.

The actual construction/type/runtime experiments may expose an invalid seam. If PR 1 or 2 cannot retain baseline behavior without temporary guards/flags/hosts, combine the affected layer with cutover and return the changed map for approval. Do not quietly add mechanisms or claim static inspection proved CI green.

Approval still needed: these exact three boundaries/slugs, the staged existing public alias/schema contract, and bounded construction experiments after modal resolution. Publication, exact-base verification and human approval remain the default R prerequisite.

## Self-review

**93/100:** clarity 24/25, comprehensiveness 24/25, feasibility 20/25, consistency 25/25.

- [x] Give every changed path an inventory/ownership entry and identify preparation-guidance deltas outside the older runtime snapshot.
- [x] Merge recorder/plans/controller/restore into one live cutover and move the store with its consumer instead of creating a temporary guard.
- [x] Keep alias-upgrade tests, initial admission, completion seed/release and source fixtures at the layer that supports them.
- [x] Use supported Make FILTER arguments, full-scope types, per-level Python distribution and independent R asset pin verification.
- [x] Address focused static review: name the actual legacy reactive save hooks and retained tests, spell out line-level admission/transaction splits, and verify the exact Makefile fixture additions against base.
- [ ] Driver approval of concrete cuts and bounded experiments; integrate the now-resolved main-based prerequisite and refresh source/base.
- [ ] Prove the staged aliases, host initialization paths, test import closure, legacy/R behavior and asset checks on constructed trees.

The map is complete enough for review, but the unexecuted staging checks are real feasibility limits. No reconstruction is authorized or claimed complete by this document.
