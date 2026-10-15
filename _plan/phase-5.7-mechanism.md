# Phase 5.7 mechanism: retire v1 history (Python)

**Status:** APPROVED by the driver 2026-10-15 (D1–D9 as written; D5 may be
amended to (b) pending the research-spike outcome)
**Phase:** plan.md §4, Phase 5.7; reset decisions plan.md §7.3–7.8 (2026-10-14)
**Kata:** parent `shinychat#36z7` under epic `shinychat#6d0d`
**Context:** `phase-5.6-mechanism.md` is completed context only. This note
is the Phase 5.7 gate and the only phase-local mechanism reference for new
work.

## Objective and boundary

Close the v2 parity gaps, add versioned record types with upgrade-on-read,
import every released v1 record form, honor the legacy v1 bookmark stamp,
then delete the v1 runtime, the `use_exchange_tree` flag, and the Python
`completion-v1` protocol branch — so Phase 6 ports exactly one engine to R.
Scope and done-when: plan.md §4 Phase 5.7. Import fidelity (§7.4), lazy
conversion (§7.5), record types (§7.6), and the legacy bookmark stamp
(§7.8) are already decided; this note resolves the remaining mechanism
decisions.

Boundary: the JS `completion-v1` path **stays** until R emits
`completion-v2` (Phase 6). No bulk store migration (§7.5). No new public
API. The import is a pure data transform — no session, no I/O (§7.6).

## Current state (verified by inventory, 2026-10-15)

- `_history_types.py`: `ConversationRecord` is the **v1** type
  (`schema_version: Literal[1]`, :184); `ConversationRecordV2` is separate
  (:379). `MAX_SCHEMA_VERSION = 2` (:144). There is **no** upgrade-on-read
  hook and **no** `_migrated_from_v1` flag on this branch.
- Store: `FileConversationStore.put` (:389) routes to `_put_v2` only when
  `schema_version == 2` and **refuses the v1→v2 overwrite** lazy
  conversion needs. `_put_v2` re-sorts the meta cache by `updated_at`
  (:547) while `list()` sorts by `created_at` (:284) — the #372
  inconsistency (`gwg3`).
- V1 runtime surface (deletion targets, `4b9z`): `extend_record_linear`
  (:347), `replay_ui` (:1258), `_EXCHANGE_TREE_HISTORY_V2` (:88) +
  `use_exchange_tree` param (:496, :2080), v1 tails in `on_response`
  (:657-743 incl. retitle), `handle_navigate` (:1639) / `handle_edit`
  (:1744) linear paths, `save_current` (:809),
  `_capture/_restore_app_state` (:829/:835), `_on_pre_switch`
  (:2176-2186), `stamp_conversation_id` (:2242), init fallback
  `replay_ui` (:2394/:2434), and the `completion-v1` branch in
  `send_history_update` (:1840). ~20 test flag-patch sites.
- Parity gaps: v2 `on_response` returns at :655 before the retitle block
  (:726-743); v2 `switch_to` (:1180-1212) never calls `on_pre_switch`;
  `new_chat(greeting=)` (`_history.py:1224`) and `clear()` gating exist
  on v1 paths only; `CapturedMessage` segments are StoredSegment-only so
  #373 structured blocks are skipped with a warning on replay;
  `_on_evict` (:2188-2207) reads v1-shaped record state.
- Bookmark stamp: v2 reads `{id}_history_exchange_pointer`
  (`_init_history` :2331); the legacy `{id}_history_conversation_id` is
  still written (:2244) and read (:2342) by the v1 path only.
- Shared fixtures live in `tests/shared/`
  (`history-behavior-matrix.json`, `history-store-fixture-matrix.json`,
  `message-transcript-matrix.json`), synced to R by `make r-sync-fixtures`
  with CI drift checks. Released tags for fixture derivation: `py/v0.6.1`,
  `py/v0.7.0`, `py/v0.7.1`, `py/v0.7.2`; R 0.5.0.
- Python CHANGELOG: `pkg-py/CHANGELOG.md`; no store-author migration
  section exists yet.

## Decisions

### D1 — Record-type layout (`e0x2`, §7.6)

Rename today's `ConversationRecord` → `ConversationRecordV1` in
`_history_types.py` (it is the v1 type; the import consumes it).
`ConversationRecordV2` stays as is. `ConversationRecord` becomes the name
for the **current** version (V2) and upgrades older versions on
validation: a `mode="before"` validator detects v1-shaped input and runs
the D2 import, so existing custom stores calling
`ConversationRecord.model_validate*` keep working. The controller also
accepts a `ConversationRecordV1` instance from a store and upgrades it.
Metadata fields (`id`, `title`, `created_at`, `updated_at`) keep their
names in every version; `put()` gains no meta argument. Type the
`ConversationStore` ABC against the record types (currently `Any`) and
update `shinychat.types` exports.

### D2 — The import (`by2p`, §7.3–7.5)

New module `_history_import.py`: a pure function
`import_v1_record(record: ConversationRecordV1) -> ConversationRecordV2`
— no session, no I/O. Behavior:

- Pair user/response v1 nodes into exchanges; re-parent multiple roots
  under a synthesized input-less root; synthesize `status` and
  `created_at`; handle the missing system prompt in v1 turns.
- Fidelity (§7.4): the result displays what released 0.7.2 shows — no
  better, no worse. F3-class artifacts already in stored records are
  carried, not repaired.
- Warnings (absorbed from superseded `6nzh`): warn **only** on genuinely
  lossy imports, with correct node/message wording — never
  unconditionally, never re-warned on every read.
- Ids (absorbed from `6nzh`): tolerate foreign/custom ids; **no
  int-parsing of node ids**.
- Synthesis rules (driver-approved 2026-10-15): status is `"ok"` for
  exchanges with messages and `"cancelled"` for input-bearing exchanges
  with no response messages (retryable; v2's honest representation of an
  interrupted exchange — plan §3.4 preserve-partial, R3); root `"ok"`.
  Every synthesized node's `created_at` is the record's `created_at`;
  v2's tie-break falls to children-list order, matching v1's
  `children[-1]` sibling fallback.
- Research findings guiding the transform (spike, 2026-10-15): v1's
  on-disk layout is identical across py 0.6.1–0.7.2 and R 0.5.0
  (`record.json` + `turns.jsonl` + `ui.jsonl`; R omits `next_node_seq`).
  Fidelity per 0.7.2 `replay_ui`: versioned stored UI is carried
  verbatim; unversioned/missing UI is re-derived from turns; user-message
  attachment content is stripped. The import emits per-exchange
  `mode:"delta"` turn entries and NO root snapshot — v1 never stored the
  system prompt, so restore reproduces 0.7.2's context exactly. The R
  0.5.0 fixture stays attachment-free (R had no attachment stripping).

### D3 — Import fixtures (`by2p`)

New shared fixture file `tests/shared/history-v1-import-matrix.json`, one
case per released form, derived from the released writers (tags
`py/v0.6.1`, `py/v0.7.0`, `py/v0.7.1`+; R 0.5.0):

1. py 0.6.x — unversioned stored UI (UI re-derived from turns, as `main`
   does).
2. py 0.7.0 — versioned stored UI.
3. py 0.7.1+ — attachments, with model-facing attachment text stripped.
4. R 0.5.0 — shared now so Phase 6 runs the same fixture in R.

Synced to R via `make r-sync-fixtures` (drift CI-checked); Python harness
follows the `tests/test_history_matrix.py` pattern. Confirm rendering
needs no live provider client.

### D4 — Lazy conversion read-gate and write guards (`e0x2`, `8ec9`, §7.5)

- `get()` (and any record read) upgrades v1 → v2 in memory through the D1
  validator. There is no bulk migration. The read-gate wiring lands with
  `e0x2` (Wave 2) — `by2p` delivers only the pure transform and fixtures.
- `put()` **accepts a v2 record overwriting an existing v1 record**
  (reversing today's refusal) — that is the "written as v2 on their next
  write" half of §7.5. Also lands with `e0x2`.
- Write guards (`8ec9`, verified against the landed versioned path):
  never write a v1-flagged record through the v2 path; a record that was
  upgraded on read is written as v2 with no v1 chimera. If any migration
  marker is introduced, it is consumed only after appends succeed.
- NEWS/CHANGELOG state that downgrading hides converted conversations
  (§7.5).

### D5 — Bookmark-mode `switch_to` (`mfb3`) — **RESOLVED: (b) in-place URL update**

Resolved 2026-10-15 per the driver's conditional direction ("if reasonably
safe, (b) is the better choice") after a research spike found (b) is
reasonably safe (full findings on `mfb3`):

- The mechanism already exists end-to-end: the `history_navigate` wire
  action WITHOUT `reload` is a soft `replaceState`, already exercised by
  v2 today after every response save (`_history.py:2138-2140`). No new
  wire action, no new JS handler; Shiny's own `updateQueryString`
  defaults to `replaceState` — in-place update is a first-class pattern.
- The target's `bookmark_state_id` is already persisted per conversation
  (`_history_recorder.py:297-320`; `_history_store.py:478`) — no new
  capture needed.
- py-shiny reads `_state_id_` only at page GET and WS init, never after;
  shiny.js patches only `pushState`, so `replaceState` is invisible to
  server state. Use `replaceState`, never `pushState` (pushState mutates
  server-side clientdata).
- Residual risk accepted: WS reconnect re-initializes from the page-load
  state id — a pre-existing staleness class v2's mint-time navigations
  already introduce; (a) buys consistency there only at a full reload per
  switch.

**Mechanism:** after `switch_to`'s v2 restore succeeds, send the existing
`history_navigate` action with `?_state_id_={bookmark_state_id}` when the
restored record has one, else `url=None` to clear the stale query. Tests
at controller, client, and Playwright levels (sketch on `mfb3`).

Rejected: (a) full navigation via `on_pre_switch` (a reload per switch;
v1's own no-state-id fallthrough already left the URL stale); (c) leaving
the URL stale (silently wrong conversation on reload).

### D6 — Legacy bookmark stamp (`dmgt`, §7.8)

`_init_history` additionally reads the legacy
`{id}_history_conversation_id` key when the v2 pointer is absent and opens
that conversation at its active leaf (upgraded on read via D4). The v1
**write** site (`stamp_conversation_id` :2242) is deleted with `4b9z`;
the read-gate stays as long as the import does.

### D7 — `new_chat(greeting=)` and `clear()` gating (`221w`, main #399)

v2 `new_chat(greeting=)` closes the active record and starts a fresh v2
record; the greeting stays the ambient slot (excluded from capture, plan
§2). `clear()` with history enabled raises, matching main's #399
semantics. No new public API.

### D8 — LLM auto-titling on v2 (`tgdt`)

Restore v1 behavior on the recorder path: the conversation title falls
back to the truncated first input (`fallback_title`,
`_history_title.py`), then the LLM retitle task fires when the active
path reaches its second completed input-bearing exchange (the v2
equivalent of v1's `response_count == 2`). The retitle writes through the
normal v2 persist path and publishes via `history_update`.

### D9 — Deletion surface (`4b9z`, after all parity/import children)

Delete: `extend_record_linear`, `replay_ui`, every v1 branch listed in
Current state, the `_EXCHANGE_TREE_HISTORY_V2` flag and `use_exchange_tree`
param, and the Python `completion-v1` branch (`send_history_update` always
emits `completion-v2`). `ConversationRecordV1` remains, but only as import
input (D1/D2). The JS `completion-v1` path stays until Phase 6. Tests
patching the flag are updated or deleted; tests of v1 behavior that the
import now owns move to the import fixture.

## Sequencing

Keystone-first: the import path (read v1 → upgrade → display) is this
phase's keystone; the v1 deletion is the hardening that lands last.

- **Wave 1 (disjoint scopes, parallel):** `by2p` import transform +
  fixtures (new files: `_history_import.py`, fixture, harness) ∥ `tgdt`
  titling (`_history.py` response path).
- **Wave 2:** `e0x2` versioned types + read-gate wiring (consumes D2's
  transform) ∥ `221w` (new_chat/clear) ∥ `fn6m` (structured blocks).
  Same-file overlap on `_history.py` is resolved by landing order:
  `221w`/`fn6m` after `tgdt` merges.
- **Wave 3 (parallel):** `dmgt` (after `by2p`), `8ec9` (after `e0x2`),
  `mfb3`, `gwg3`, `t21d` fixture + CHANGELOG migration notes.
- **Wave 4:** `4b9z` v1 deletion (blocked by `tgdt`, `mfb3`, `221w`,
  `fn6m`, `gwg3`, `e0x2`, `by2p`, `dmgt`).

Edge fixes to apply: `dmgt` blocked-by `by2p`; `8ec9` blocked-by `e0x2`.

Every task: claimed in Kata with truthful attention pair, small
conventional commits (Kata refs in body), roborev review on the task's
commits, three-findings escalation valve per mechanism.

## Progress log

- 2026-10-15: phase opened. Suite baseline: JS 1407 passed (23 skipped);
  R 2123 passed (0 fail); py 224/225 Playwright + unit green — the one red
  is `cancel_in_modal::test_escape_cancels_stream_before_closing_chat_modal`,
  a pre-existing local-environment failure dispositioned under `ftz9`
  (fails identically on pure `origin/main`; main CI passes; re-check when
  branch CI runs). `phase-5.6-mechanism.md` handoff backfilled. Branch is
  404 commits ahead of `origin/main`; `origin/main` is an ancestor — no
  boundary merge needed.
- 2026-10-15: note APPROVED (D1–D9). Edges fixed: `dmgt` blocked-by
  `by2p`, `8ec9` blocked-by `e0x2`. D4 scope amended: read-gate wiring and
  the v1→v2 overwrite allowance land with `e0x2`, not `by2p` (comments on
  both issues). Wave 1 delegated: `by2p` (import transform + fixtures),
  `tgdt` (v2 titling); D5 research spike delegated (medium).
- 2026-10-15: D5 RESOLVED to (b) in-place URL update per the driver's
  conditional direction (spike: mechanism exists as `history_navigate`
  sans `reload`; `bookmark_state_id` already persisted; py-shiny never
  re-reads the URL). Decision on `mfb3`. `tgdt` landed `fb3c8105` (D8:
  fallback title + retitle at second input-bearing exchange, persist via
  recorder lock, publish via `history_update`); coordinator-verified (300
  controller/title tests); roborev 1578 enqueued. Accepted scope
  deviation: one-line `accepted_input` change in `_history_recorder.py`
  (v2 fallback title is minted there, not in `_history.py`).
- 2026-10-15: `tgdt` CLOSED. Roborev 1578 Pass with 3 Low, all fixed in
  `a1d51d9a` (retitle target passed through with start-of-task bail;
  docstring; sibling/third-exchange test pins). First `by2p`/`fn6m`
  agents hit the default turn limit after research-only runs (the 5.6
  `b0hf` pattern); re-delegated with incremental-commit briefs and the
  driver-approved D2 synthesis rules. `fn6m`'s finding: the 5.6 merge
  already widened `CapturedMessage.segments` to
  `StoredSegment | StructuredBlock` — remaining work is mostly coverage.

## Handoff

(appended at phase exit — what landed, what's next, provisional decisions)
