# Comment-Audit Triage — Phase 5 exchange-tree history (`_history*.py`)

Triage of tranches 1–4 (`/tmp/comment-audit-tranche-{1..4}.md`) against the
actual source, the export surface (`shinychat/__init__.py`,
`shinychat/types/__init__.py`), and `_plan/phase-5.8-mechanism.md`.
Report-only; no source modified.

**Export surface check (keep-exception 4 ground truth).** `shinychat` exports
no `_history*` symbol directly (`chat_ui_history` comes from `_page_chat`).
`shinychat.types` exports: `HistoryOptions`, `ConversationMeta`,
`ConversationPartition`, `ConversationStore`, `FileConversationStore`,
`ConversationRecord`, `ConversationRecordV1`, `ConversationRecordV2`.
Everything else in the nine modules is internal — including `HistoryController`,
`ChatHistory`, `derive_stored_ui_message`, `derive_node_ui`, `ConversationNode`,
and `CapturedMessage` (tranche 1 applied exception 4 more broadly than the
export surface justifies; its *flags* were re-checked accordingly).

**Overall numbers.** 134 flags received (T1 41 distinct — its items 43/44 fold
into 18/19/4; T2 22; T3 38; T4 33), plus one site raised only as a MUST KILL
(T1 #3, `_complete_history_transition`) = 135 sites. All 135 were checked
against source. 26 flags rejected outright (comment stays), 80 DELETE,
23 REWRITE-AS-CODE, 6 driver-decision. Of the 30 MUST KILL flags: 10 map to
existing Phase 5.8 units, 8 are realistic new work (1 contingent on a driver
call), 10 rejected as unrealistic or already-structural, 1 driver call.

---

## 1. Summary table (per file)

| File | Flags received | Verified | Rejected | DELETE | KEEP (exception) | REWRITE-AS-CODE | Driver decision |
|---|---|---|---|---|---|---|---|
| `_history.py` | 63 (+1 implicit) | 64 | 6 (2 partial) | 41 | 6 | 14 | 3 |
| `_history_types.py` | 25 | 25 | 15 | 8 | 15 | 2 | 0 |
| `_history_store.py` | 13 | 13 | 5 | 7 | 5 | 0 | 1 |
| `_history_import.py` | 20 | 20 | 0 | 15 | 0 | 4 | 1 |
| `_history_recorder.py` | 4 | 4 | 0 | 1 | 0 | 3 | 1 |
| `_history_plan.py` | 4 | 4 | 0 | 3 | 0 | 0 | 1 |
| `_history_client.py` | 3 | 3 | 0 | 3 | 0 | 0 | 0 |
| `_history_bookmark.py` | 0 | — | 0 | 0 | 0 | 0 | 0 |
| `_history_title.py` | 2 | 2 | 0 | 2 | 0 | 0 | 0 |
| **Total** | **134 (+1)** | **135** | **26** | **80** | **26** | **23** | **6** |

Notes: two `_history.py` rejections are partial (only the self-contained
external-constraint clause of the comment survives; the rest dies).
`_history_recorder.py`'s module-docstring flag is counted once as
REWRITE-AS-CODE with a driver sub-question on its inventory paragraph.
Planning-artifact references form a group of **17 comment sites** (see §2.10).

---

## 2. Disposition list, grouped by file

Dispositions: DELETE (comment dies, no code change) · KEEP (named exception) ·
REWRITE-AS-CODE (MUST KILL accepted; 5.8 unit or "new work") · DRIVER (§5).

### 2.1 `_history.py` (T1 + T2)

**KEEP (exception 2 — released on-disk data / external dependency):**
- L62–63 lazy `shiny` import — *kept by auditor, confirmed*: circular import
  forced by `shiny.ui._chat` importing `shinychat`. (Not a flag; listed for
  completeness.)
- L206 `_stored_ui_dict` docstring — REJECT flag. "Drops empty `attachments`
  so text-only messages keep their previous shape" pins the released on-disk
  serialized shape. KEEP (2).
- L234–237 stopgap comment on `_strip_attachment_content` — REJECT flag and
  REJECT its MUST KILL: v1 records on disk (py 0.6.x–0.7.2) already contain
  mixed attachment content; subtraction at upgrade is the only remediation.
  "Delete when v1 is retired" names a data-format lifecycle, not a task
  tracker. KEEP (2). Unit 2 (D2) relocates the helper and the comment.
- L265–266 broad `except` in `_strip_attachment_content` — REJECT flag and
  MUST KILL: the guarded data is arbitrary attachment content from
  older-version records; replay must not hard-fail. KEEP (2).
- L1877–1882 legacy v1 bookmark read-gate — auditor-kept, confirmed KEEP (2)
  (v1-written bookmarks persist in the wild); **strip refs** `shinychat#dmgt`,
  `plan §7.8`, `shinychat#4b9z`.
- L2000–2006 v1-stamp fallback — auditor-kept, KEEP (2); strip refs.
- L2032–2037 legacy node_id synthesis — auditor-kept, KEEP (2); strip refs.
- L1904–1914 `scope()` flush-timing — auditor-kept, confirmed KEEP (2)
  (Shiny input-delivery timing + pending py-shiny PR; external).
- L1926–1928 `session.user` convention — auditor-kept, KEEP (2) (Shiny
  convention, collision caveat).

**REWRITE-AS-CODE (accepted MUST KILL / mechanism-covered):**
- L396–400 identity-invariant comment — **5.8 unit 4** (D6 makes the
  "sole record owner" invariant structural) + **unit 8** (mechanism note
  explicitly lists "the identity-path comment `_history.py:396–400` vs
  `:468`/`:786`" as a fix target).
- L404–406, L410–411, L415–420, L424, L426–430 (the five `on_*` hook
  comments in `__init__`) — **5.8 unit 6** (D8: "the restore-mode
  callback-slot strategy gets a name" — hook contracts move onto the named
  strategy/type). The D5-flavored prose in L415–420 dies with it.
- L436–438, L755–760 (`_restore_step` docstring), L986–988
  (`restore_body_entered` attribution) — **5.8 unit 5** (D7 deletes the
  `_restore_failure_step` slot and the `restore_body_entered` flag; step
  label travels on the exception).
- L511–516 read-gate comment (plan §7.5, D1/D4) — **5.8 unit 1** (D1 rewires
  exactly this site to surface warnings via `import_v1_record_with_warnings`).
- L543 `on_response` docstring (P5.6.8 audit + concurrency argument) —
  **5.8 unit 4** (D6 routes all record mutation through recorder methods that
  acquire the lock internally, making the safety argument structural).
- L882–884 "sole v2 record owner" — **5.8 unit 4** (D6: "Makes the Phase-4
  'sole v2 record owner' invariant true").
- L1051–1054 only-after-successful-restore hook timing — **5.8 unit 6**.
- L2116–2119 `_on_new` mirror comment — **5.8 unit 6** (D8: the five
  near-identical input handlers share `_transition_effect`; the mirroring
  dies with the duplication).
- L1839–1845 `D5:` comment on `_on_switch_restored` — PARTIAL: the "D5:"
  planning prefix dies (grouped with unit 6's named callback-slot strategy);
  the **replaceState-never-pushState / clientdata constraint survives as a
  self-contained comment** (exception 2: Shiny server-side clientdata reacts
  to URL changes mid-session). Counted as rejected-partial in §1.

**DELETE:**
- L249 `_strip_attachment_content` docstring (restates the kept block comment
  above it).
- L385–387 callback-list aliasing narration (see §4 for the rejected
  copy-refactor; re-aimed new work in §3).
- L442, L540, L1011, L1283, L1324, L1506 section banners.
- L457–458 `isolate()` narration; L487–489 single-writer narration.
- L572 `_schedule_exchange_retitle` docstring planning refs
  (`phase-5.7 D8: tgdt`) — clause dies; surrounding v1/v2 narration dies with
  unit 7 (folds v1 `retitle`) / unit 8 (drops `_v2` suffixes).
- L604 `retitle_v2` docstring — same.
- L615, L624, L626–627 guard narration in retitle path; L659 "oldest first".
- L705–706 detail-composition narration.
- L774–776 info-split narration (the split is already structural:
  `_restore_failure_detail` is the user-safe channel, `warnings.warn` the
  developer channel).
- L783–784 sync-clear ordering (adjacent to unit 5's rewrite).
- L819 `except: pass` narration.
- L837–838 validate-path-first ordering (D4 keeps the fail-closed preflight
  ordering; prose doesn't guard it).
- L866–867 live-bootstrap-after-admission — deduped with
  `_history_plan.py` L256–261 (one root cause, two files; both die).
- L964–965 initial-restore-no-transaction rationale.
- L1018–1019 load-before-mutate ordering.
- L1059–1061 best-effort URL-failure rationale.
- L1081–1084 announce-cleared-state rationale.
- L1089–1091 fresh-chat-never-restore rationale.
- L1168–1169 preflight-on-copy (MUST KILL rejected, §4; D4 declares this
  ordering untouched).
- L1189–1191 sibling-open branch narration (extraction = new work, §3).
- L1232–1237 **and** L1455–1463 rewind-hooks-before-persist rationale —
  duplicates; one deduped entry, both DELETE.
- L1332–1337 no-clear-badges proof (MUST KILL rejected, §4).
- L1567–1569 `_effects` tracking (registry = new work, §3).
- L1586–1589 `_initial_history_initialized` narration (guard object = new
  work, §3).
- L1598 `_history_action_admitted` "v2" framing docstring.
- L1874–1875 bookmark-stamp narration.
- L1943–1944 `finish_initial` ordering invariant (folding = new work, §3).
- L1966 settlement-is-advisory narration.
- L1970 `owner_scope = scope()` inline narration.
- L1975 "Priority 1" narration.
- L2053–2059 **partial**: the readiness/retry narration dies; the
  SilentException/first-flush sentence (Shiny input-delivery timing) survives
  as a self-contained comment (exception 2). Counted as rejected-partial.
- L2248–2249 session-end consumed-registration narration.

**KEEP via rejection:**
- L1977–1979 `bookmark_pointer` tuple semantics — REJECT flag: `node_id is
  None` exists because v1 bookmarks in the wild carry only a conversation id
  (exception 2). MUST KILL rejected (§4).

**DRIVER:** L732–741 `_restore_failure_detail` docstring; L1606–1615
`_teardown` docstring; L358–360 `_complete_history_transition` advisory
swallow (raised only as MUST KILL) — see §5.

### 2.2 `_history_types.py` (T3) — 25 flags

**KEEP (exception 2 — released v1 on-disk format semantics; flags rejected):**
- L64, L72, L81–87 (`StoredSegmentDict`, `AttachmentDict`, `StoredUiMessage`
  docstrings) — these TypedDicts *are* the on-disk serialized forms; the
  docstrings pin format identity with `StoredMessage.model_dump(...)`. KEEP (2).
- L113–115 `ConversationMeta.size_bytes` — KEEP (4): `ConversationMeta` is
  exported from `shinychat.types`; the comment defines the store-implementer
  contract behind `total_size()`. Flag rejected (it is not duplicate
  narration — `ConversationStore.total_size()` is the consumer side).
- L122–124 `turns`, L126–127 `ui`, L129–132 `selected_child` on
  `ConversationNode` — KEEP (2): `ConversationNode` is the released v1
  on-disk record shape (py 0.6.x–0.7.2); the comments document the stored
  format's semantics, which we cannot reshape. Rename refactor (T3's
  suggestion) is impossible: field names are on disk.
- L153–158 `is_stored_ui_versioned` docstring — KEEP (2): describes the
  versioned/unversioned mixing present in released records.
- L194–196 `title_source`, L198–201 `response_count` — KEEP (2): stored-field
  enum/count semantics of the released v1 format (the retitle-trigger sentence
  becomes test-only after unit 7 folds v1 `retitle`, but the field semantics
  stay).
- L661–662 deferred import in `_upgrade_v1` — KEEP: 5.8 unit 2 (D2)
  explicitly retains the types↔import cycle as "the documented compatibility
  shim"; this comment *is* that documentation. Carries its constraint
  directly.
- L666–668, L673–676 pydantic-refusal comments — KEEP (2): pydantic's
  model-input rules for subclasses are external and unreshapeable.
- L679–684 dict-branch comment — KEEP (2/4): pre-`schema_version` disk data
  (None→1 convention), the markerless-v2-kwargs nuance, and the
  v1-error-shape compatibility contract for custom stores calling the public
  `ConversationRecord` validator.
- L386 `ConversationRecordV2` docstring — KEEP (4): exported symbol;
  one-line identity statement. Flag rejected.

**REWRITE-AS-CODE:**
- L136–139 `ui_message_count` — **5.8 unit 3** (D4 visible-input iterator
  centralizes the index-math sites) + **unit 8** (mechanism note explicitly
  lists "the `ui_message_count` comment (`replay_ui` is gone)" — verified:
  `replay_ui` no longer exists anywhere; the comment is stale *and*
  prose-enforced).
- L719–723 `new_conversation_id` — collision/last-writer-wins caveat is a
  prose-confessed latent bug; **new work** (uuid4 is stdlib; 5.8's
  no-behavior-change boundary pushes it after 5.8).

**DELETE:**
- L30, L58 error-catalogue helper one-liners (restated by adjacent code).
- L213–216 `ConversationRecordV1.meta()` docstring (cross-refs the kept
  `size_bytes` contract).
- L267–271 `set_current_leaf` narration (duplicates the kept
  `selected_child` field semantics; the body shows the walk).
- L324 `CapturedMessage` docstring (restates name + capture site).
- L540 `open_inputless_exchange` docstring (restates name).
- L185–189 **clause** "(plan section 7.6)" — rest of the exported
  `ConversationRecordV1` docstring stays (exception 4).
- L641–656 **clause** "(plan section 7.6, decision D1)" — rest of the
  exported `ConversationRecord` docstring stays (exception 4).

### 2.3 `_history_store.py` (T3) — 13 flags

**KEEP (flags rejected):**
- L103–105 `_WriteState.ui_node_digest` — KEEP (2): last-write-wins
  re-append rule is forced by the released v1 `ui.jsonl` append-only format.
  Dies naturally with the Deferred v1-write-path removal (Phase 7 candidate).
- L403–405 validate-before-write — KEEP (2): fail-closed rejection of
  on-disk records from other schema versions before any directory mutation.
- L433–438 stale v1 side-file removal ordering — KEEP (2): v1 file layout
  + atomic-replace semantics on the upgrade path (dies with the deferred
  v1 write path).
- L530–532 write-before-append — KEEP (2): released v1 append-only
  journaling/rollback semantics (same deferred death).
- L583–585 `list()` ordering + `(#372)` — KEEP (5): the issue link explains
  the created_at-vs-updated_at cache-coherence constraint the code cannot
  express, tied to the public newest-first contract.

**DRIVER:** L733 `sanitize_scope` dots/path-traversal comment — see §5.

**DELETE:**
- L299–300 stale-cache narration.
- L418–422 **and** L662–664 lazy-conversion comments (deduped; plan §7.5/D4
  refs die; the one-way overwrite rule is raised by the adjacent
  `ValueError`).
- L649 `_put_v2` docstring (atomicity contract lives on the public
  `FileConversationStore` docstring).
- L671–673 mirrors-`FileConversationStore.put` narration.
- L713 `"auto"` branch narration.
- L789 concurrent-session race narration.

### 2.4 `_history_import.py` (T4) — 20 flags

**KEEP (auditor-kept, confirmed):** module docstring fidelity paragraph
(L9–13) — exception 2 (pins display behavior to released py 0.7.2 output);
`import_v1_record(_with_warnings)`, `stored_pointer`, `effective_selected`,
`has_bare`, `mapped`, `covering_exchanges`, `continuations_after`,
`_turn_entry_kind`, `_display_messages` docstrings — exceptions 2/4
(v1 pointer/fallback/display semantics of released writers; entry-point
contracts). All confirmed against code.

**REWRITE-AS-CODE:**
- L56–57 `_TURNS_STATE_KEY` "mirrors `_history_recorder`" — **5.8 unit 3**
  (mechanism note verbatim: "`TURNS_STATE_KEY` defined once and imported
  (replacing the 'mirrors `_history_recorder`' comment)").
- L156–157 synthesized-root collision — **5.8 unit 3** (D5: the `n_0000_1`
  collision handling moves behind the `root_id` property, with a new test).
- L380–381 active-path-walk narration — **5.8 unit 3** (D4: one ancestor-walk
  helper covers "the importer's active-path walk").
- L480 lazy `from ._history import ...` — **5.8 unit 2** (D2 moves
  `_strip_attachment_content`/`derive_node_ui` into `_history_import`,
  "deleting the `_history_import → _history` lazy import cycle").

**DELETE:**
- L1 title clause "(plan sections 7.3-7.5)".
- L8 clause "(plan section 7.4)" — fidelity paragraph itself stays (2).
- L59 node-classes comment; L93–94 orphan-root narration;
  L193–194 no-bare narration; L208–212 exchange-per-node block;
  L224–226 pair-exchange narration; L233–234 else-branch enumeration;
  L245–247 "Driver-approved synthesis (2026-10-15)" (approval trail; the
  ternary below states the rule); L271–273 sibling-order narration;
  L319–325 one-sided-links block (incl. "section 7.4 fidelity contract" ref);
  L331–342 pointer post-pass; L351–357 active-leaf rationale; L372–377
  no-active-leaf rationale; L454 `_best_effort_leaf` docstring.

**DRIVER:** L14–25 "Structure mapping" module-docstring paragraph — see §5.

### 2.5 `_history_recorder.py` (T4) — 4 flags

- L1–11 module docstring — REWRITE-AS-CODE, **5.8 unit 4** for the "do not
  split into per-role locks" directive (D6: recorder-owned locking makes the
  constraint structural); the "The R port mirrors this structure" sentence
  DELETEs (cross-repo narration; §5 group item). The ownership-inventory
  paragraph: DRIVER (§5).
- L50–55 `_TURN_BASELINE_INVALID` sentinel comment — REWRITE-AS-CODE,
  **new work** (type the baseline `list[str] | None`, or an explicit invalid
  flag; kills both the fingerprint-collision argument and the aliasing
  warning). Realistic; not covered by 5.8.
- L89–90 `_canonical_turns` delegation-wrapper comment — REWRITE-AS-CODE,
  **new work** (delete the wrapper, call `canonical_turns` at its two call
  sites; trivial).
- L60 class docstring ("Private v2 capture owner...") — DELETE (restates
  module docstring + name).

### 2.6 `_history_plan.py` (T4) — 4 flags

- L1–9 module docstring — "The R port mirrors this module's structure"
  DELETEs; purity-inventory paragraph: DRIVER (§5).
- L87 `canonical_turns` docstring — DELETE (restates body; omits the
  key-validation step it also performs).
- L256–261 `materialize_live_restore_turns` "intentionally" sentence —
  DELETE; deduped with `_history.py` L866–867 (same ordering rationale,
  one disposition).
- L296–306 `preflight_state` consolidation sentence — DELETE (refactor-history
  narration clause; the per-parameter semantics sentences stay).

### 2.7 `_history_client.py` (T4) — 3 flags

- L99 TurnDict-pointer comment — DELETE (the kept `TurnDict` docstring
  carries the constraint).
- L246 "mirrors R's `ellmer_turn_effective_role`" — DELETE (R port is our own
  code; parity belongs in the shared test suite). See §5 group item.
- L260 defensive-join narration — DELETE.

### 2.8 `_history_bookmark.py` — 0 flags. Auditor keeps confirmed sound
(exception 2: `shiny.bookmark._global` private-module accessor, Connect
bookmark hooks).

### 2.9 `_history_title.py` (T4) — 2 flags

- L51 `_truncate_fallback` docstring — DELETE.
- L61–66 `fallback_title_from_text` docstring — DELETE (caller narration).

### 2.10 Planning-artifact reference group

**17 comment sites** in the nine modules reference `_plan/`, `plan §x.y`,
D-numbers, kata ids, dated driver sign-offs, or phase ids:

| # | Site | Refs | Disposition |
|---|---|---|---|
| 1 | `_history.py:511` | plan §7.5, mechanism D1/D4 | dies via 5.8 unit 1 |
| 2 | `_history.py:543` | P5.6.8 audit | dies via 5.8 unit 4 |
| 3 | `_history.py:572` | phase-5.7 D8: `tgdt` | DELETE clause (units 7/8) |
| 4 | `_history.py:604` | phase-5.7 D8: `tgdt` | DELETE clause (units 7/8) |
| 5 | `_history.py:1839` | D5 | prefix dies; replaceState constraint stays (unit 6 names the strategy) |
| 6 | `_history.py:1877–82` | `shinychat#dmgt`, plan §7.8, `shinychat#4b9z` | comment stays (2); strip refs |
| 7 | `_history.py:2000–06` | `shinychat#dmgt`, plan §7.8 | stays (2); strip refs |
| 8 | `_history.py:2032–37` | `shinychat#dmgt`, plan §7.8, `shinychat#e0x2` | stays (2); strip refs |
| 9 | `_history_types.py:187` | plan section 7.6 | DELETE clause |
| 10 | `_history_types.py:649–50` | plan section 7.6, decision D1 | DELETE clause |
| 11 | `_history_store.py:418–22` | plan section 7.5, mechanism D4 | DELETE (whole comment) |
| 12 | `_history_store.py:662–64` | plan section 7.5, mechanism D4 | DELETE (whole comment) |
| 13 | `_history_import.py:1` | plan sections 7.3–7.5 | DELETE clause |
| 14 | `_history_import.py:9` | plan section 7.4 | DELETE clause |
| 15 | `_history_import.py:245–47` | Driver-approved synthesis (2026-10-15) | DELETE (whole comment) |
| 16 | `_history_import.py:319–25` | "section 7.4 fidelity contract" | DELETE (whole comment) |
| 17 | (none further — grep-verified complete) | | |

Rule applied: where the referenced decision genuinely constrains the code,
the surviving comment carries the constraint directly (e.g. #1's upgrade
semantics are re-expressed by unit 1's wiring; #5 keeps only the
pushState/replaceState sentence). Sites 6–8 keep their on-disk-format
constraint prose but must lose the plan/kata pointers; the bare kata ids
(`shinychat#dmgt` etc.) are issue links that may qualify under exception 5
only if they explain a constraint code cannot express — driver confirm in §5.

---

## 3. MUST KILL dispositions (30 raised)

### Mapped to Phase 5.8 units (10)

| Flag | Symbol | 5.8 unit |
|---|---|---|
| T1 #5 | active-id/record identity ownership | **Unit 4** (D6 sole-owner invariant; unit 8 fixes the stale identity-path comment) |
| T1 #6 | `_get_record` silent in-place v1→v2 upgrade | **Unit 1** (D1 rewires the read-gate) |
| T1 #8 | `on_response` prose-only concurrency safety | **Unit 4** (D6 recorder-owned locking) |
| T1 #9 | `switch_to` success-only hook invocation | **Unit 6** (D8 named callback-slot strategy) |
| T2 | `_on_new` mirrors the other input effects | **Unit 6** (D8 `_transition_effect` helper) |
| T2 | `_on_switch_restored` D5 note | **Unit 6** (naming; constraint clause kept under exception 2) |
| T3 | `ConversationNode.ui_message_count` mirror invariant | **Unit 3** (D4 iterator) + **Unit 8** (stale `replay_ui` ref; confirmed gone) |
| T4 | `_TURNS_STATE_KEY` duplicated constant | **Unit 3** (verbatim in the mechanism note) |
| T4 | `_history_import → _history` lazy-import cycle | **Unit 2** (D2 deletes the cycle) |
| T4 | `_ExchangeRecorder._lock` no-split directive | **Unit 4** (D6 routes mutations through recorder methods) |

### Realistic, not covered by 5.8 → new work (8, +1 contingent)

| Flag | Symbol | New-work refactor |
|---|---|---|
| T1 #4 (re-aimed) | `HistoryController` save/restore callback lists | Explicit registration API (the auditor's "copy" refactor would break post-`_start()` registration — rejected as stated) |
| T2 | `resubmit` preserve_live_turns branch | Extract the sibling-open path |
| T2 | `ChatHistory._effects` bare list | Effect-registry object (adjacent to unit 6 but unnamed) |
| T2 | `_initial_history_initialized` bool | Admitted-guard object |
| T2 | `finish_initial` ordering invariant | Fold the authoritative `send_history_update` into the helper |
| T3 | `new_conversation_id` last-writer-wins | Collision-free id scheme (uuid4); stdlib, but a new-record format change → after 5.8's no-behavior-change boundary |
| T4 | `_TURN_BASELINE_INVALID` sentinel | Type baseline as `list[str] | None` (or explicit invalid flag) |
| T4 | `_ExchangeRecorder._canonical_turns` wrapper | Delete the wrapper; call `canonical_turns` at its two call sites |
| T2 (contingent) | `ChatHistory._teardown` docstring | Owner-object refactor only if the driver rules the docstring dies (§5) |

### Rejected (10) and driver (1)

See §4 and §5.

---

## 4. Rejected flags, with reasons

**Flags rejected (comment stays):**

1. `_history.py:206` — docstring pins the released on-disk serialized shape
   (exception 2), not narration.
2. `_history.py:234–237` — subtraction-at-upgrade is the only remediation for
   content already written to disk by released v1 versions; "delete when v1 is
   retired" is a data-format lifecycle, not a planning artifact. Its MUST KILL
   ("derive at write time") is impossible retroactively.
3. `_history.py:265–266` — the swallow guards replay against arbitrary
   malformed attachment data from older-version records (exception 2);
   narrowing the catch cannot prove safety over `model_validate` +
   normalization of stored user data.
4. `_history.py:1977–1979` — `node_id=None` tuple slot is forced by v1
   bookmarks in the wild; a typed pointer relocates the prose into the type
   rather than eliminating it.
5. `_history.py:2053–2059` (partial) — the SilentException/first-flush
   sentence documents Shiny input-delivery timing (exception 2); only the
   readiness narration dies.
6. `_history.py:1839–1845` (partial) — the replaceState-never-pushState
   constraint (server-side clientdata mutates on pushState mid-session) is
   external; only the "D5:" prefix dies.
7. `_history_types.py` (15 sites) — see §2.2: on-disk v1 format semantics
   (TypedDicts, node fields, `is_stored_ui_versioned`, `title_source`,
   `response_count`), exported-symbol contracts (`size_bytes`,
   `ConversationRecordV2`), and the `_upgrade_v1` cluster (documented
   compatibility shim per 5.8 D2; pydantic input rules are external).
8. `_history_store.py:103–105, 403–405, 433–438, 530–532` — released v1
   file-format/journaling semantics and cross-version on-disk fail-closed
   checks (exception 2); the three v1-write-path comments die with the
   Deferred Phase-7-candidate removal instead.
9. `_history_store.py:583–585` — `(#372)` is an issue link explaining a
   cache/contract coherence constraint (exception 5).

**MUST KILLs rejected (unrealistic or already structural):**

1. T1 #1 `_strip_attachment_content` derive-at-write — impossible for records
   already on disk.
2. T1 #2 narrow the strip's `except Exception` — see §4.3.
3. T1 #7 `_clear_failed_restore` typed user/dev pair — the split is already
   structural (`_restore_failure_detail` is the user-safe channel;
   `warnings.warn` the developer channel).
4. T2 `resubmit` preflight deep-copy ownership — 5.8 D4 explicitly declares
   the fail-closed preflight ordering untouched.
5. T2 `_send_sibling_metadata` clear-all payload — requires a JS/protocol
   change; 5.8's boundary forbids JS changes, and the asymmetry is
   deliberate (forks are permanent, so empty genuinely means no badge).
6. T2 `restore_initial_v2` `settle_advisory()` — over-engineering a one-line
   `except: pass` that preserves the restore error.
7. T2 `bookmark_pointer` typed pointer — see §4.4.
8. T2 `_init_history` readiness extraction — the load-bearing content is the
   external flush-timing constraint, which extraction doesn't remove.
9. T2 `_on_session_end` one-shot object — over-engineering two nullable
   bookkeeping fields.
10. T3 `ConversationRecord._upgrade_v1` restructure — 5.8 D2 retains the
    types↔import cycle as the documented compatibility shim, and the pydantic
    refusals are external behavior.

**MUST KILL → driver:** T1 #3 `_complete_history_transition` — see §5.

---

## 5. Needs driver decision

1. **Leak-safety docstring, `_history.py:732–741` (`_restore_failure_detail`).**
   Policy-strict says delete (private helper, own-code, no exception). But
   "never carries raw exception text, which can hold internal details from
   app hooks or the store" is the only prose standing between a future editor
   and reintroducing `str(failure)` into a user-facing notification. Delete
   per policy, or keep as an explicitly security-rationale exception?
2. **`_teardown` docstring, `_history.py:1606–1615`.** Part of the
   release/destroy contract is forced by Shiny's effect/session model (effects
   keep answering shared input ids after the owning `Chat` is replaced) —
   exception 2 if you accept that framing; own-code narration if not. If it
   dies, the owner-object refactor (new work) should land with it.
3. **Advisory swallow, `_history.py:358–360` (`_complete_history_transition`).**
   `except (CancelledError, Exception): pass` around a fire-and-forget client
   notification. Deliberate (the client may be gone; completion is advisory)
   — but swallowing `CancelledError` is the kind of thing reviewers flag on
   principle. Keep the comment as the constraint carrier and reject the MUST
   KILL, or narrow the catch (new work)?
4. **Import module docstring "Structure mapping" paragraph
   (`_history_import.py:14–25`).** Twelve lines of transform algebra that
   duplicate the code below — but the module is a radon-E(38) pure transform
   that the R port must mirror and that 5.8 explicitly defers rewriting. Is
   this architecture-overview documentation (keep, minus the plan pointers)
   or narration (delete and let the fixture-pinned tests carry it)?
5. **Module-docstring ownership/purity inventories**
   (`_history_recorder.py:1–11`, `_history_plan.py:1–9`). Same class of
   content: module-scope architecture contracts ("planner is pure functions;
   adapter stays visible at call sites") that the R port mirrors. These are
   exactly the "architecture-overview module docstrings" the policy doesn't
   address. Delete with unit 4/6 refactors, or keep as module contracts?
6. **Cross-port "R mirrors" notes** (`_history_recorder.py:3`,
   `_history_plan.py:9`, `_history_client.py:246`). Policy says die (our own
   code). But Phase 6 copies these modules into R, and parity markers may be
   the cheapest guard against drift. Delete (shared tests are the real
   guard), or keep as a named convention? If kept, `ellmer_turn_effective_role`
   in `_history_client.py:246` still dies (it narrates a mirror, not a
   constraint).
7. **Security rationale on own sanitizer, `_history_store.py:733`
   (`sanitize_scope`).** "Dots are excluded to prevent path-traversal
   sequences like '..'" — the regex shows the exclusion but not the reason; a
   future charset widening would silently reopen traversal. No keep exception
   strictly covers it (exception 5 is issue/RFC links). Delete per policy, or
   accept as a constraint-carrier?
8. **Kata/issue ids in kept v1-compat comments** (`shinychat#dmgt`,
   `shinychat#4b9z`, `shinychat#e0x2` at `_history.py:1877–1882`,
   `2000–2006`, `2032–2037`; `(#372)` at `_history_store.py:583–585`).
   The constraints stay under exception 2; the plan-§ pointers must go.
   Confirm whether the bare kata ids count as exception-5 issue links (keep)
   or local task-tracking IDs (strip). Recommend: strip — none of them
   explains a constraint the prose doesn't already carry.

---

## 6. Process notes

- All four tranches' line numbers resolved correctly against HEAD except
  T3's header, which printed a doubled path
  (`pkg-py/src/shinychat/pkg-py/src/shinychat/_history_types.py`) —
  cosmetic only.
- T1's self-adjusted count (42 distinct, folding its items 43–44) was
  honored; T1's item 1 (L62–63) was a kept-list cross-reference, not a flag.
- Tranche keep-lists were spot-checked, not re-audited in full; one
  over-broad application noted: T1/T2 applied exception 4 to
  `HistoryController`/`ChatHistory`/`derive_*` docstrings, which are not
  exported from `shinychat` or `shinychat.types`. None of those were flagged,
  so no disposition changes; but future audits should use the export surface
  as the exception-4 boundary.
- One tranche-4 "keep" deserves a caveat: `restore_bookmark_pointer`
  docstring (T1, L995) is kept under exception 4 but the symbol is test-only
  surface — 5.8 unit 7 (D9) folds it into tests, where the docstring follows.
