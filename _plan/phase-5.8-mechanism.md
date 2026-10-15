# Phase 5.8 mechanism: pre-port hardening (Python)

**Status:** APPROVED by the driver 2026-10-15 (units 1–9, D1–D10 as
amended). Children: `5hda` → `z2nt` → `xny0` → `b1wd` → `ajxc` → `yp75`
→ `mvyc` → `fsj3` → `c1ht` (linear blocking chain).
**Phase:** plan.md §4, Phase 5.8
**Kata:** parent `shinychat#e8kd` under epic `shinychat#6d0d`
**Context:** `phase-5.7-mechanism.md` is completed context only. This note
is the Phase 5.8 gate and the only phase-local mechanism reference for new
work.

## Objective and boundary

Resolve the Phase-5-closeout holistic-review findings (roborev analyses
1592 architecture, 1593 complexity, 1594 dead-code, run against the nine
`_history*` modules at HEAD), the comment audit of the same modules
(four tranches under `.agents/prompts/review-comments.md`, triaged in
`_plan/phase-5.8-comment-audit-triage.md`: 135 sites — 80 DELETE, 23
REWRITE-AS-CODE, 26 KEEP), plus one requirement gap those analyses
surfaced, so the architecture the collaborator draft PR (`73pm`) asks to
approve — and that Phase 6 (`05vb`) copies into R — is final-shape.

Driver decision (2026-10-15): **full pre-port hardening** — the layering,
duplication, recorder-boundary, and module-split work all land before the
draft PR, not after.

Boundary:

- **No behavior change**, except the lossy-import warning wiring (unit 1),
  which is a requirement gap fix. Everything else is move/rename/extract.
- **No JS/SCSS changes** in this phase (no `make update-dist` needed). If a
  unit discovers it needs one, stop and re-gate.
- **No R changes.** Where a structural decision is one the R port must
  mirror, the unit's kata issue says so explicitly (§3.2 shape-stability:
  Python settles first, R copies the settled shape).
- The generic state-hook registry **stays generic** — plan §3.7 (extension
  contract) is a requirement. Collapsing the registry to turns-only is
  pre-refused.

## The requirement gap (unit 1)

Phase 5.7's absorbed requirement (`36z7` ← `6nzh`): *warn only on
genuinely lossy imports, with correct node/message wording — never
unconditionally, never re-warned on every read.* The transform
(`import_v1_record_with_warnings`, `_history_import.py:75`) produces
exactly those warnings, but **no production path calls it**: both upgrade
sites (`_history.py:517` read-gate, `_history_types.py:669` validator)
call `import_v1_record`, which discards them. The module docstring's
design ("returned, never emitted, so the read-gate wiring … can surface
each warning once") was never wired. Current behavior satisfies
"never re-warn on read" by never warning at all. This traces to a
requirement — it is a fix, not a backlog item (process §2.1).

## Work units (sequenced)

Order is dependency-driven: moves before centralization, centralization
before the split, trims continuous. Each unit is one kata child, one
review unit; the orchestrator requests one roborev range review per unit
(process §4.1) and batches its findings.

1. **Wire lossy-import warnings** (requirement gap; D1). Independent of
   all other units; lands first.
2. **Layering moves** (D2, D3). Consolidate all v1-only code into one
   version-named module: rename `_history_import.py` to `_history_v1.py`
   and move the v1-only UI-derivation helpers (`_stored_ui_dict`,
   `derive_stored_ui_message`, `_strip_attachment_content`,
   `derive_node_ui` — `_history.py:205–339`) into it, deleting the
   `_history_import → _history` lazy import cycle. The read-gate and the
   validator shim are the only current-version call sites. Move
   `TurnDict` down so `_history_types` stops importing `_history_client`
   (D3). The types↔v1-module validator cycle stays as the documented
   compatibility shim.
3. **Duplication centralization** (D4, D5). One visible-input iterator on
   `ConversationRecordV2` for the three index-math sites
   (`exchange_id_for_user_message_index`, `_send_sibling_metadata`,
   `_send_exchange_metadata`); a `root_id` property replacing the five
   `"n_0000"` literals (D5 covers the importer's `n_0000_1` collision
   case); one ancestor-walk helper for `path_node_ids` /
   `set_active_leaf` / the importer's active-path walk;
   `TURNS_STATE_KEY` defined once and imported (replacing the
   "mirrors `_history_recorder`" comment); `_RETRYABLE_STATUSES` and the
   `_attachment_projection` extraction in `resubmit`; one `_rewind_locked`
   skeleton shared by `handle_navigate` and `resubmit` (capture close →
   run plan → set leaf → persist → send → `_clear_failed_restore`), with
   `_validate_resubmit_target` and the sibling-open path extracted; the
   recorder's one-line-differing `message_committed`/`stream_started`
   merged; the trivial `_canonical_turns` wrapper deleted in favor of
   calling `canonical_turns` at its two call sites; store helpers
   (`_read_jsonl`, `_upsert_meta`, `_check_overwrite`) in
   `_history_store.py`.
4. **Recorder boundary** (D6). A `Protocol` naming what
   `_ExchangeRecorder` needs from its host; public recorder methods for
   the operations the controller currently performs through privates
   (`_lock`, `_persist_record`, `_restore_hooks`, `_rewind_hooks`,
   `_invalidate_turn_baseline`, `_accepted_resubmit_input_locked`,
   record mutation via `record.set_active_leaf`); delete the
   `getattr(..., None)` test-fake fallbacks (test fakes implement the
   Protocol); controller's `retitle` record mutation goes through the
   recorder; the `_TURN_BASELINE_INVALID` sentinel retires — the turn
   baseline becomes `list[str] | None` (or carries an explicit invalid
   flag), ending the fingerprint-collision and aliasing prose. Makes the
   Phase-4 "sole v2 record owner" invariant true. R-port mirror: yes.
5. **Restore-step on the exception** (D7). Replace the mutable
   `_restore_failure_step` slot, its manual reset, and the
   `restore_body_entered` flag with the step label carried on the
   re-raised exception (the `StateHookError` pattern; `add_note` or a
   `RestoreStepError` wrapper). Innermost-step rule per D7.
6. **Split `_history.py`** (D8). `HistoryController` (orchestration) and
   `ChatHistory`/`_start` (Shiny wiring, restore-mode setup, input
   effects) become separate modules; the five near-identical input
   handlers share a `_transition_effect` helper; the restore-mode
   callback-slot strategy gets a name; `finish_initial` folds the
   authoritative `send_history_update` into the helper so the ordering
   invariant is structural. Lands late so units 2–3 shrink the file
   first. R-port mirror: yes.
7. **Test-only and leftover surface** (D9). Fold `replay_exchange_record`,
   `restore_bookmark_pointer`, `retry`/`regenerate` wrappers, and
   `fallback_title` into the tests or delete them; tests stop exercising
   production paths through test-only bypasses (process §5.2).
   `import_v1_record_with_warnings` stays — unit 1 wires it.
8. **Stale names and docs** (continuous, lands with the unit that
   touches the site). Drop the `_v2` suffixes (`retitle_v2`,
   `_publish_active_v2_id`); fix the `FileConversationStore` docstring
   (three-file layout, "returns `ConversationRecordV1`"), the
   `ui_message_count` comment (`replay_ui` is gone), the identity-path
   comment (`_history.py:396–400` vs `:468`/`:786`); dedupe
   `ensure_conversation_id` / `_allocate_conversation_id`; flatten the
   no-op if/else in `_destructive_mutation`; plus the remaining
   low-risk list from 1593: `_check_record_for_store`'s precedence
   expression, `handle_navigate`'s prev/next branches, a `live_turns`
   helper, `_after_persist`, and `_parse_bookmark_pointer` for the
   `_init_history` parsing block.
9. **Comment hygiene** (D10). Apply the comment-audit triage
   (`_plan/phase-5.8-comment-audit-triage.md`): the 80 DELETEs, and
   ref-stripping of planning-artifact pointers from kept comments.
   Lands after unit 2 (moved helpers carry clean comments) and before
   unit 6 (the split moves a smaller, cleaner file). Sites the triage
   mapped to units 1–8 die with those units; this unit takes the rest
   in one mechanical pass, verified against the triage list, not
   re-adjudicated site by site.

## Decisions

- **D1 — Warning surfacing.** The controller's `_get_record` read-gate
  collects warnings from `import_v1_record_with_warnings` and emits them
  via `warnings.warn` (one warning per lossy step, wording unchanged from
  the transform), guarded by a per-controller `set` of conversation ids
  already warned — each warning surfaces once per session per
  conversation, never on re-read. The store and the pydantic validator
  keep discarding warnings (they have no session to warn into; the
  controller read-gate is the only user-facing upgrade path). Tests pin:
  lossy fixture warns once with node/message wording; second read is
  quiet; non-lossy forms (the four released-form matrix cases) never
  warn.
- **D2 — v1 code lives in one version-named module, `_history_v1.py`**
  (driver annotation 2026-10-15: version in the file name keeps legacy
  code out of current-version code paths). `_history_import.py` is
  renamed — the transform, the fidelity contract, and the moved
  UI-derivation helpers (whose only production caller is the importer)
  are all v1-only; the "delete when v1 is retired" stopgap becomes one
  module to delete. This matches the version-suffixed record types
  (`ConversationRecordV1`/`V2`) and clarifies the R port's parity
  mapping. `FileConversationStore` stays whole: it is public, and its
  v1 read/write paths are the deferred Phase-7 item, not a
  version-split of a public class. Test imports of the moved symbols
  update in the same commit.
- **D3 — `TurnDict` moves to `_history_types.py`.** `_history_client`
  imports it from there. Breaks the types → client → `_chat_*` import
  chain; types becomes importable without the chat-client modules.
- **D4 — One derivation per concept, owned by the record.**
  `ConversationRecordV2` gains the visible-input iterator and `root_id`;
  the ancestor walk is a module-private helper in `_history_types`. The
  controller's metadata senders consume these; they keep no index math
  of their own. Fail-closed preflight ordering (preflight on deep copy →
  admit → lock → mutate) is untouched.
- **D5 — `root_id` semantics.** The unique node with no parent. The
  importer's synthesized-root collision handling (`n_0000_1` when a v1
  node already claims `n_0000`) moves behind the property; add a test
  with a v1 node literally named `n_0000`.
- **D6 — Recorder boundary.** A `RecorderHost` Protocol in
  `_history_recorder.py` declares exactly the members the recorder reads
  today (`adapter`, `partition`, `store`, active-id access and publish,
  conversation-id allocation, `send_history_update`, save callbacks).
  New public recorder methods own every record mutation and every
  currently-private operation the controller calls. The `getattr`
  fallbacks are deleted with the fakes updated to satisfy the Protocol.
- **D7 — Restore step travels on the exception.** A `RestoreStepError`
  (or `add_note`, matching the existing `StateHookError` pattern)
  carries the innermost step label; setters must not overwrite an
  existing label. Cancellation re-raise paths stay unwrapped, as
  `run_plan` already does.
- **D8 — Module split.** `HistoryController` moves to
  `_history_controller.py`; `_history.py` keeps `ChatHistory`,
  `HistoryOptions`, and the Shiny wiring. (Alternative the implementer
  may propose: inverse split. Either way, one module is wiring, one is
  orchestration, and the diff is a pure move.) Test patches of
  `shinychat._history.*` update in the same commit; public import paths
  (`shinychat` / `shinychat.types` exports) are unchanged — the split
  moves private modules only.
- **D9 — Test-only surface.** No production symbol survives solely
  because tests call it. Fixture-building convenience moves into test
  helpers. (`ConversationRecordV1`'s graph-editing API is explicitly out
  of this unit — see Deferred.)
- **D10 — Comment-audit judgment calls** (driver-delegated, recorded
  2026-10-15; full triage in `_plan/phase-5.8-comment-audit-triage.md`
  §5). KEEP: the `_restore_failure_detail` leak-safety docstring (trust
  boundary for the bounded-error requirement); the `_teardown` Shiny
  effect/session constraint (trimmed); the
  `_complete_history_transition` advisory-swallow comment (no code
  change); the import module's "Structure mapping" paragraph and the
  recorder/plan module-docstring contracts, minus plan pointers (the
  parts units 4/6 make structural die with those units); the
  `sanitize_scope` path-traversal rationale; the `(#372)` issue link
  (exception 5). DELETE: all three "R port mirrors" notes — R6 parity
  is enforced by shared fixtures, not prose. STRIP: bare `shinychat#…`
  kata ids from kept comments (local task tracking); `_plan/`/
  `plan §`/D-number references die per the audit policy. DECLINED as
  mechanism-without-requirement: callback-registration API, `_effects`
  registry object, `_initial_history_initialized` guard object,
  `_teardown` owner-object refactor — their narration comments simply
  die.

## Deferred (recorded, not this phase)

- **v1 write path in `FileConversationStore.put`** (~200 lines:
  `_WriteState`, JSONL append/rollback). Dead in production after Phase
  5.7, but `FileConversationStore` is public and this is a behavior
  change for custom-store authors → kata issue, decide before release
  (Phase 7 candidate), with migration notes.
- **`ConversationRecordV1` graph-editing API** (`append_linear` et al.,
  used only as a test fixture builder) → same kata issue or its own;
  test refactor, no urgency.
- **Import-closure rewrite** (`import_v1_record_with_warnings`, radon
  E(38)) as precomputed tables → backlog. Pure, fixture-pinned, and the
  R port mirrors it; rewrite only if the port finds the closures
  untranslatable.
- **Older codex reviews (1118–1197, incl. the p4-5r50 series)** →
  follow-up disposition sweep, separate task.
- **`new_conversation_id` collision-free ids** → kata `shinychat#fd2p`
  (backlog; changes the new-record id format, so it lands after this
  phase's no-behavior-change boundary).
- **Hook-registry collapse** → declined (plan §3.7). The
  turns-only fields in `StatePathContext` may move into a turns payload
  as part of unit 4 only if it stays internal.

## Done when

- Unit 1 lands: a genuinely lossy v1 import warns once per session per
  conversation with node/message wording; re-reads are quiet; the
  released-form matrix stays silent.
- Units 2–8 land, each with its orchestrator-requested roborev review
  and batched dispositions; the escalation valve (process §4.3) applies
  per unit.
- `roborev analyze` architecture/complexity/dead-code re-run against the
  same nine modules: every targeted finding is resolved or carries a
  recorded disposition here; 1592/1593/1594 are closed with evidence.
- Gates green: `make py-check-unit`, Playwright history specs,
  ruff/pyright/air. No JS gate expected (no JS changes).
- No production behavior change except unit 1's warnings: the full py
  suite passes with zero test-expectation changes other than moved
  imports/patches and the new warning tests.
- This note and plan.md §4 are updated at exit; the draft-PR packaging
  task (`73pm`) is unblocked.

## Handoff log

- 2026-10-15: Note drafted from roborev 1592/1593/1594 + the
  warning-wiring gap verification; driver selected full pre-port
  hardening. Awaiting approval before child-task creation.
- 2026-10-15: Comment audit folded in (4 tranches, medium triage):
  unit 9 added, accepted refactors folded into units 3/4/6, D10 records
  the driver-delegated judgment calls, `fd2p` backlog filed. Still
  awaiting driver approval of the whole gate.
- 2026-10-15: Driver annotation (Plannotator): D2 amended — version-named
  `_history_v1.py` module (rename of `_history_import.py`) holds all
  v1-only code; store stays whole.
- 2026-10-15: Driver approved the gate. Nine children created in a
  linear blocking chain (`5hda` first: warning wiring). Phase open.
- 2026-10-15: Unit 1 (`5hda`) landed — read-gate wires
  `import_v1_record_with_warnings` with a per-controller warned-id set
  (`2fb061d8`, `d7454174`); roborev 1595 pass, findings batched on the
  issue. Next: unit 2 (`z2nt`, layering moves D2/D3). Provisional
  disposition: Python's default warnings filter coalesces identical
  warnings process-wide, so cross-session repeats in one process may be
  suppressed — D1 mechanism kept, caveat documented at the read-gate.
  Session-entry note: `uv sync --extra providers` was needed for a
  green `make py-check-unit` in this worktree.
- 2026-10-15: Unit 2 (`z2nt`) landed — `_history_v1.py` consolidation
  (D2, `286a4be6`) + `TurnDict` to `_history_types` (D3, `39a82920`);
  roborev 1596 pass (1 Low, fixed in `74a97b41`). Next: unit 3
  (`xny0`, duplication centralization D4/D5). New backlog `c87g`:
  bookmark input-restore Playwright flake (orthogonal, ~1/3 failure
  rate, related ht4q/bmqg).
- 2026-10-15: Unit 3 (`xny0`) landed — all ten centralizations (D4/D5)
  in 9 commits (`b836b620`..`d0af557c`); roborev 1597 pass, finding
  fixed in `a695a942` (root_id laziness in accepted_input + descriptive
  error). Next: unit 4 (`b1wd`, recorder boundary D6 — the phase's
  biggest unit; Protocol, public recorder methods, sentinel
  retirement). `c87g` now 3/3 in full history-filter runs, still ~1/3
  solo.
