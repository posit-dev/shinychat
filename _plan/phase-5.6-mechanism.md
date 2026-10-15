# Phase 5.6 mechanism: main sync and Python pre-port pass

**Status:** COMPLETE 2026-10-14 — decisions D1–D7 signed off by the driver;
all children closed; gates green · 2026-10-14
**Phase:** plan.md §4, Phase 5.6; reset decisions plan.md §7 (2026-10-14)
**Kata:** parent `shinychat#e1dv` under epic `shinychat#6d0d`
**Context:** `phase-5-mechanism.md` is completed context only; its handoff
names this phase's first task. This note is the Phase 5.6 gate and the only
phase-local mechanism reference for new work.

## Objective and boundary

Land the review dispositions (plan §7.9) and the pulled-in GitHub issues
(#417/#418, #422) that must be in the Python structure **before the R port
copies it** (Phase 6 ports structure first, then behavior — process.md
§3.3). The merge with `main` (P5.6.1, `ftz9`) is complete: `main` is an
ancestor of the branch at `3a2e6208`, and v1 history files took `main`'s
version as directed.

This phase is behavior-preserving except where a disposition says otherwise.
It adds no queue, timer, barrier, second owner, public API, or new
suppression semantics — Q1's disabled-until-restore-decision contract
(plan §3.5) is amended only by the accepted constant warning (§7.9 #1
secondary).

## Current state (verified by inventory, 2026-10-14)

- The v2 admission guard is the same three-clause expression inlined at
  **7** sites in `_chat.py` (`_on_slash_command` 545, `_append_complete_message`
  1164, `message_stream_context` root branch 1279, `_append_message_chunk`
  chunk-start 1390, `append_message_stream` 1697, `_record_accepted_user_input`
  2312, `_record_accepted_user_input_with_capture` 2333). The helper
  `ChatHistory._history_action_admitted()` (`_history.py:2515`) already
  exists and gates 3 input effects in `_history.py`. The "three entry
  points" comment at `_history.py:2506` is stale.
- `append_message_stream` creates its `ExtendedTask` and reserves the
  stream (`_append_message_chunk(chunk="start")` →
  `ChatTranscript._reserve_stream_start`) only inside the task body — the
  #417 race. Suppressed, it returns `None` against its
  `ExtendedTask[[], str]` annotation.
- All suppression is silent: no `warnings.warn`, no logging.
- `_ExchangeRecorder` (`_history.py:444-1157`, ~710 lines) mixes three
  roles: capture (transcript callbacks, turn capture, baseline),
  restore/rewind planning (preflight/materialize/validate), and
  persistence/bookmark. The turn-baseline invalidation sentinel is the bare
  list `[""]`, meaningful only via its comment.
- Resubmit (`_history.py:2064-2067`) and sibling navigate
  (`_history.py:2317-2321`) run `set_active_leaf` + `_persist_record`
  **before** the rewind hooks — a rewind-hook failure leaves the store
  pointing at the moved leaf. (The line ranges in `b0hf` were off; these
  are the real sites.)
- The constructor-message path: `Chat(messages=)` raises unless
  `history=False` (#381, `_chat.py:352-365`); v1 bookmark restore still
  references `_append_init_messages` and destroys `_init_chat` to suppress
  `ui.Chat(messages=)` initialization (`_chat.py:2909-2925`). The
  v2-targeted constructor suppression code and its tests were partly
  removed by the merge; the rest is `zdec`'s deletion.
- Installed py-shiny is 1.7.0 with the **sequential** flush
  (`_flush_sequential`); py-shiny#2508 (concurrent effects) is merged
  upstream but not in the installed build.
- Leftover untracked dirs `history_initial_startup_barrier/` and
  `history_q1_probe/` (only `__pycache__`) exist under
  `pkg-py/tests/playwright/chat/`.

## Mechanism decisions

### D1 — One admission predicate (P5.6.3, `e431`)

All 7 `_chat.py` sites route through `ChatHistory._history_action_admitted()`
unchanged in semantics (controller absent / recorder absent / initialized ⇒
admitted). The stale comment is rewritten. Per-site dismissal behavior
(`return` / `return False` / bare yield) is preserved; only the duplicated
condition is factored out. `message_stream_context`'s root-only scope is
preserved (nested streams bypass admission today; that is unchanged).

**Suppressed stream entry points raise (driver decision, 2026-10-14).**
`append_message_stream()` raises a clear error at the top of the method
when the admission predicate is false — before the `message` iterable is
wrapped or touched, so zero chunks are pulled from the app's (expensive,
unconsumed) LLM stream and ownership stays with the caller to close or
gate it. The same treatment extends to the root-stream branch of
`message_stream_context` (same unconsumed-producer argument), replacing
its silent `MessageStream(self, None)` yield. Rejected: `| None`
annotation (app author may never learn the stream was dropped and keeps
pulling tokens); fabricated completed task (silently misreports a stream
that never ran; test-double machinery on a production path, process.md
§5.2). The stream/append split is deliberate: an append is already-
realized content and only warns (D5); a stream is an unconsumed expensive
producer and raises.

### D2 — Synchronous stream reservation (P5.6.4, `3y60`; absorbs #418, credited)

Adopt #418's shape, adapted to the branch: `append_message_stream()`
generates the stream id and awaits the `chunk="start"` send itself — which
reserves through `ChatTranscript._reserve_stream_start()` synchronously —
before creating and invoking the `ExtendedTask`. `_append_message_stream`
takes the stream id and sends only content chunks and the end chunk.

Constraints the adaptation must preserve:

- The P5.3 valve classification: a failure of the initial `chunk="start"`
  call is `HISTORY_ERROR_STREAM_START` (lands in `e4d1b822`); it moves with
  the start call into `append_message_stream`'s synchronous prologue.
- The D1 guard still runs first; a suppressed stream never reserves.
- Absorb #418's early-cancel handling: the done-effect watches the task's
  public `status()`; if the task is cancelled before its body started, the
  effect sends the end chunk and flushes pending messages (the body would
  never run its `finally`). The branch equivalent must route the synthetic
  end chunk through the transcript's abort/settle path, not around it.
- #418's two regression tests (`append_message` after stream keeps call
  order; cancel-before-start still ends) are ported to the branch's
  transcript-level assertions.

### D3 — Recorder split (P5.6.5, `c4dx`)

Split `_ExchangeRecorder` into three role classes in a new private module
`_history_recorder.py` ( `_history.py` shrinks accordingly):

- **Capture** — transcript callbacks (`accepted_input`, `message_committed`,
  `stream_started/updated/finished`), turn capture (`_capture_turns`,
  `_canonical_turns`, baseline set/invalidate), `_capture_state`,
  `suspend_capture`, record/root lifecycle (`_new_record`,
  `_content_exchange`, `_close_root_if_inactive`,
  `install_restored_record`, `reset`).
- **State planner** — restore/rewind preflight and execution
  (`_preflight_*`, `_materialize_*`, `_validate_*`, `_restore_state`,
  `_rewind_state`, `_rewind_non_turn_state`).
- **Persistence/bookmark** — `_persist_record`, `save_current*`,
  `response_settled`, `rename_active_locked`, `bookmark_pointer`,
  `settle_bookmark_state_id`, `mark_active_id_published`, eviction.

The recorder object the controller holds becomes a thin composition of the
three, keeping one shared `asyncio.Lock` (the controller re-enters it via
`_exchange_mutation`; lock splitting is out of scope). Consolidation within
the split:

- `_preflight_restore_state` and `_preflight_rewind_state` collapse into
  one preflight function parameterized by hook kind (restore vs rewind);
  `_restore_state`/`_rewind_state` become one runner — they already share
  `_restore_turns` via `StatePathContext.bootstrap`.
- The repeated `include_system_prompt` / `kind` expressions are factored
  once.
- The `[""]` baseline-invalidation sentinel becomes a named module-level
  constant (e.g. `_TURN_BASELINE_INVALID`) with the invariant in its
  docstring. The snapshot escape hatch stays.

Behavior-preserving; the existing suite is the pin. No method is deleted
unless its callers move with it.

### D4 — Restore failure attribution + rewind ordering (P5.6.6, `b0hf`)

- Restore/rewind failures name the failing hook (entry name) or step
  (preflight, materialize, display replay, turn set) in the warning.
  Fail-to-fresh-draft (approved 2026-09-01) stays; per-entry degradation
  remains declined.
- Ordering invariant: **rewind hooks run before the leaf move is
  persisted.** Both resubmit and sibling navigate preflight against a
  deep-copied projection, so the plan exists before mutation; reorder to
  capture-current-leaf → run rewind hooks → `set_active_leaf` → persist →
  display replay. If a hook fails, neither store nor memory has moved and
  the fail-to-fresh-draft path applies cleanly. If the replay ordering
  (navigate replays display between persist and rewind today) blocks this,
  the implementer stops and records a disposition instead of building a
  compensating mechanism.

### D5 — Suppression warning (P5.6.7, `4ec9`)

One module-level constant message, emitted with `warnings.warn(...,
stacklevel=2)` (house style; no logging exists in these files) at each
suppression site — after D1, those sites all call the one predicate, and
the warning fires where work is actually dropped (not inside the
predicate, which also serves pure admission checks). Message names the
consequence: the append/stream was ignored because conversation history is
initializing, and it will not be replayed. No buffering, no replay, no
per-call variation (easy to filter). Sequenced after `e431` so it lands on
the consolidated sites.

### D6 — py-shiny#2508 ordering audit (P5.6.8, `xgzh`)

Audit, then fix or file: `_init_history` priority-10_000 against
`_init_chat`; recorder lock acquisition order under `_exchange_mutation` /
`_destructive_mutation`; `on_response` re-entrancy (absorb #422's
docstring-only argument — two guarantees: no overlapping runs of one
effect; input changes held until session effects finish); the
on-flushed-deferred response-settlement pump; startup admission reads of
`_initial_history_initialized`. Installed py-shiny 1.7.0 flushes
sequentially, so behavioral testing against concurrent effects requires a
py-shiny dev install from git main (driver decision 2026-10-14); if that
proves impossible in the environment, the shortfall is escalated, not
silently downgraded.

### D7 — Hygiene and triage (P5.6.9 `49b6`, P5.6.10 `2ym2`)

Delete the two `__pycache__`-only Playwright dirs; rename-or-delete per
`zdec`'s outcome (the test name cited in `49b6` does not exist — closest
matches are in `test_chat_history.py`; the hygiene item resolves to
verifying no stale names survive `zdec`). Triage the eight open
critical-review items under superseded epic `3403` (close as superseded /
re-parent / backlog) and close `3403` when empty.

## Sequencing

1. `zdec` (deletion) — independent; first.
2. `xgzh` audit — read-only, runs in parallel with implementation; its
   findings land as fixes here or filed issues.
3. `e431` + `3y60` together (same function; `3y60`'s body says so).
4. `4ec9` — after `e431` (writes to the same guard sites).
5. `c4dx` — `_history.py` recorder; parallel-unsafe with `b0hf`.
6. `b0hf` — after `c4dx` (same file, adjacent regions).
7. `49b6`, `2ym2` — anytime; no production code.

Each task: small conventional commits with kata refs in the body, roborev
review on the task's commits, gates green (`make py-check`, JS untouched
except where a task says otherwise).

## Progress log

- 2026-10-14: note approved (D1–D7). Suite baseline green (JS 1407; py unit
  1095; Playwright 224 + known environmental `cancel_in_modal` red per
  `ftz9`). P5.6.10 (`2ym2`) triage complete: `3403`'s 8 open findings
  disposed (2 re-parented, 5 superseded, 1 obsolete), epic `3403` closed.
  P5.6.2 (`zdec`) closed audit-no-change: the constructor-specific
  suppression was already deleted in `5248eae6`; the `ftz9` handoff note
  claiming production code remained was inaccurate. `__pycache__`-only
  Playwright dirs deleted (P5.6.9 partial). Delegated and running:
  P5.6.8 audit (`xgzh`), P5.6.3+4 (`e431`+`3y60`, wave 2), `h94s`
  verification pass (read-only, under `49b6`).
- 2026-10-14: P5.6.8 (`xgzh`) closed. **Premise correction: py-shiny#2508
  is CLOSED-unmerged; main still flushes sequentially.** Audited against
  the #2508 head ref anyway: all surfaces safe under both models; findings
  filed as backlog `3y6p` (mock session contract) and `k089`
  (concurrent-model tests); #422 docstring amendment folded into `49b6`;
  v1 no-lock `on_response` moot (5.7 retires v1). `h94s` verification
  complete: 6 moot, item 4 corrected to v1-only (v2 already guards),
  backlog `5qxa`/`x9fa`/`y5kr` filed; `h94s` closed.
- 2026-10-14: P5.6.3+4 landed: `80aeb5e1` (one admission predicate),
  `9390de71` (D1 raise on suppressed stream entry points), `8bb9e830`
  (D2 synchronous reservation, absorbing #418; plus `_unhandled_error`
  added to the test-session mocks after a leftover armed settlement
  callback polluted later flushes — same mock-contract gap as backlog
  `3y6p`, now fixed for 1.7.0). Unit 1097 green; ruff/pyright green.
  Incident: a resume-error led to a duplicate delegation; the original
  agent had landed two commits before dying at its turn limit mid-
  commit-3; the work was verified and completed by the coordinator.
  Approved deviation (orchestrator): #418's verbatim test assertions do
  not port — this branch rejects mid-stream appends rather than queueing
  them (pinned contract; process.md §7.4 forbids the queue), so the
  regression pins the raise plus post-settle ordering. Roborev job 1564
  enqueued on the three commits. P5.6.7 (`4ec9`) delegated.
- 2026-10-14: P5.6.7 landed (`ce93c76e`). Roborev chain on P5.6.3/4/7:
  1564 (F), 1565 (F), 1566 (F), 1567 (P + 3 low), 1568 (P + 1 low) — all
  findings fixed in `d19a0aec` (worker claims stream ownership),
  `f4a671a6` (ownerless-until-claim), `9200ab39` (warn at public entry;
  slash-command silent; docstring/changelog truth), `58906277`
  (`_STREAM_UNOWNED` sentinel; dead streams close their producer),
  `b095bd9e` (changelog scoping). Escalation valve fired on the
  reservation mechanism (5 findings): decision PATCH (chain converging
  High→Low, alternatives forbidden by §7.4), review flipped to batched
  range review (job 1570 on `006b58d..b095bd9e`).
- 2026-10-14: P5.6.5 (`c4dx`) landed: `edd7e002` (planner →
  `_history_plan.py`, 360 lines) + `83049007` (recorder →
  `_history_recorder.py`, 482 lines; `_history.py` 3235→2507). Roborev
  1572 enqueued. Accepted deviations: `preflight_state` gained a `phase=`
  keyword (pinned error messages), six failure-injection tests moved
  their monkeypatch seams, `_canonical_turns` stays recorder-side as a
  delegating staticmethod. Incident: the delegated agent's experiment
  harness committed two stray log commits (`.auto/`, `.agents`);
  excised from history. Delegation briefs now forbid scratch commits.
  P5.6.6 (`b0hf`) delegated.
- 2026-10-14: batched range review (1570) Pass; its 2 live findings fixed
  in `6a2eaf1b` (producer closed on early cancel; internal chunk-start
  guard raises consistently). 1569's findings fixed in `7e10cad0`.
  `e431`, `3y60`, `4ec9` closed with evidence. Driver decision: push to
  origin (and CI) waits for phase exit. `b0hf` agent hit its turn limit
  at ~70% (implementation verified coherent by coordinator: StateHookError
  + step labeling + rewind-before-persist reorder; 25 test failures are
  expected contract changes); completion delegated.
- 2026-10-14: P5.6.6 (`b0hf`) landed: `7ab34db7` (StateHookError names
  the failing entry; restore steps labeled; resubmit/navigate run rewind
  hooks before set_active_leaf + persist — committed as one commit, the
  two parts entangled at the except blocks) + `73ae308c` (#422 docstring
  absorbed with the audit's amended rationale) + `284b57a9` (roborev
  1573's Medium: raw exception text moved from user notification to
  developer warning; 16 test pins updated + restore-hook test added).
  `c4dx`, `49b6` closed. Only `b0hf` open, pending roborev 1574.
  Incident note: 1Password signing outage mid-session (driver restarted);
  a staged docs edit rode along in `7ab34db7` (harmless, noted).

## Handoff

- **What landed:** `main` sync at `3a2e6208`; one admission predicate with
  suppressed stream entry points raising; #417 synchronous stream
  reservation (batched range review 1570 Pass); `_ExchangeRecorder` split
  into `_history_plan.py` + `_history_recorder.py`; StateHookError step
  labeling with rewind-before-persist on navigate/resubmit; constant
  init-window suppression warning; py-shiny#2508 ordering audit (backlog
  `3y6p`, `k089`, `5qxa`, `x9fa`, `y5kr`, `bmqg`).
- **What's next:** Phase 5.7 (`shinychat#36z7`) — v2 parity gaps, versioned
  record types with upgrade-on-read, the v1→v2 import with per-form
  fixtures, the legacy bookmark stamp, then deletion of the v1 runtime,
  the `use_exchange_tree` flag, and the Python `completion-v1` branch.
- **Provisional decisions:** push to origin (and CI) deferred to phase
  exit; the reservation mechanism is under batched range review after the
  escalation valve fired (decision: PATCH).
