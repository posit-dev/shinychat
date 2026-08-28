# Phase 2 mechanism: server-authoritative core

**Status:** agreed · 2026-08-27
**Phase:** plan.md §4, Phase 2
**Kata:** parent `kjyt` under epic `6d0d`; stacked children `6s8q` →
`ch09` → `dy7g` → `47fa`

## Objective

Delete Python's browser-reported transcript as an authority. The server
records accepted user input and emitted output transactionally, and
`Chat.messages()` reads that record synchronously. This phase establishes
the in-memory capture boundary that Phase 3 will project into persistent
exchange nodes; it does not introduce the persistent node schema.

## Decisions

### Authority and transaction boundary

- Add one private Python transcript owner. `Chat` retains normalization,
  transforms, dependency processing, and transport; the owner retains
  committed message wire specs, including resolved per-message icon metadata,
  and in-flight stream accumulation.
- Mutations follow **prepare → send → commit**. A failed send never commits
  unsent content. Successfully sent stream content is committed eagerly to
  the in-flight entry so a later error cannot erase what the user saw.
- Accepted user input is committed by the priority-9999 input observer before
  application submit callbacks. It needs no transport send because the
  browser already rendered its optimistic user message.
- Complete output, clear, Chat-owned initial messages, slash-command echoes,
  and complete-message restore paths mutate through the owner. Stream
  transitions move there in `shinychat#ch09`.
- Until `shinychat#ch09`, public `Chat.messages()` retains its legacy
  browser-reported, eventually consistent behavior. The owner has a reactive
  revision for internal consumers and returns defensive projections.
- Once complete and streaming paths share the owner, `shinychat#ch09` switches
  public `Chat.messages()` to synchronous owner reads. Existing successful
  messages retain their current shape; a preserved partial adds
  `status: "cancelled"` or `status: "error"`, and an errored partial adds
  `error: {"message": ...}`. Phase 3 moves those fields onto exchange nodes
  rather than inventing a second status model.

### Exchange attribution, not scheduling

- The user-input observer opens an opaque in-memory exchange identity.
- A stream captures the exchange identity when it starts. Every later chunk
  and terminal transition uses that captured identity, never the mutable
  current exchange.
- Admitted input may open the next exchange while the previous stream remains
  active. Recording that user intent is allowed during an active stream.
- Phase 2 adds no response queue and no multi-stream client protocol. The
  current wire supports one displayed stream; attempting to start a second
  output stream fails explicitly. Response scheduling is separate from
  history attribution and remains out of scope until a user workflow enables
  overlapping submissions.
- The legacy pending-message queue is deleted. Complete output cannot be sent
  through the one-stream wire while a stream is active.

### Lifecycle settlement and destructive-state drain

- **Normal settlement:** a committed terminal response normally settles its
  private lifecycle-local consumer delivery at `reactive.on_flushed`. The
  delivery is pending until that flush and is invoked exactly once for that
  terminal response. It carries callback work and lifecycle identity, not
  response content.
- **Destructive-state preflight and drain:** every history destructive
  operation, including switch, new chat, active delete, and
  restore/rebuild/replay paths, must preflight and reject an active stream
  before any history or source mutation. After that preflight passes, drain
  all pending terminal settlements exactly once, then perform the first
  mutation. This prevents partial history mutation before
  `Chat.clear_messages()` rejects an active stream.
- A clear with no pending settlement invokes no consumers. A clear while a
  stream is active remains rejected; it does not become a waiting admission
  path or a partial clear.
- This is a private lifecycle-local pending-delivery mechanism, not a
  response/output queue. It adds no content queue, waiting stream admission,
  or client protocol change.
- Consumer failures remain isolated: one history or bookmark consumer failure
  cannot suppress other consumers or change the response, source mutation, or
  terminal outcome.

The rationale is ordering, not buffering. `reactive.on_flushed` remains the
normal path because it settles after the committed terminal response has
reached the lifecycle boundary. A destructive clear or replacement can
otherwise erase the live source before that flush callback runs; draining the
pending delivery first preserves the source long enough for each consumer to
settle once. The delivery state is private and lifecycle-local so this ordering
rule does not create response scheduling, content retention, or a client-facing
protocol.

### Revised #311 contract

Reuse #311's transaction pattern, defensive copies, segment coalescing,
replacement checkpoints, stream identity, and JSON fixture approach. Do not
reuse its single-flight admission rule or discard-on-abort behavior.

The revised fixture covers:

- complete messages, attachments, dependencies, mixed stream segments, and
  replace checkpoints;
- send failure at complete, start, chunk, and end transitions;
- accepted user input while an older stream is active;
- old-stream attribution after a newer exchange opens;
- cancellation/error preserving every successfully sent segment with status;
- clear/replace behavior and defensive reads.

### Python-only client distribution

Delete the echo reporter from JS source and build `js/dist`, then run
`make py-update-dist`. Do not run `make update-dist` in Phase 2: the R package
keeps its previous packaged client and its existing echo-based server path
until Phase 6. JS CI continues to verify that committed `js/dist` matches
source. The acceptance audit verifies that Python's packaged JS matches
`js/dist` and that R's packaged JS remains unchanged from the Phase 2 branch
point; this divergence is intentional until Phase 6.

The forged-input contract is state integrity: `${id}_messages` cannot mutate
Python transcript, bookmarks, or history. An unknown type-tagged input may be
rejected by Shiny; a graceful no-op transport response is not required.

## Stacked work

1. **Keystone complete-message slice (`shinychat#6s8q`).** Add the private
   owner, revised fixture seed, accepted-input recording, transactional
   complete sends, and owner invalidation while retaining public legacy
   `Chat.messages()` behavior.
2. **Transactional streams and attribution (`shinychat#ch09`).** Route stream
   transitions through the owner, commit sent chunks eagerly, preserve partial
   cancellation/error, bind streams to opening exchanges, delete the pending
   queue, and switch `Chat.messages()` to synchronous owner reads.
3. **Python consumer cutover (`shinychat#dy7g`).** Move bookmark and current history consumers to
   server state; replace echo-triggered settlement; remove stale-report
   deduplication, `ui_offset`, and Python's `shinychat.messages` handler.
4. **Client echo deletion and acceptance audit (`shinychat#47fa`).** Remove the JS reporter and
   snapshot builder, build JS, copy assets only to Python, add forged-input and
   end-to-end regressions, and verify no Python echo consumer/reporter remains.

Each item is a stacked PR based on its predecessor. The echo deletion is a
single-session atom and starts only after every Python consumer has moved.

## Verification

- Focused owner/fixture unit tests after each behavior lands.
- Python unit, type, and formatting checks on every stacked PR.
- JS tests/build and `make py-update-dist` for the client deletion PR.
- Asset comparison proving `js/dist` equals Python's packaged bundle while
  R's packaged bundle is unchanged from the Phase 2 branch point.
- Focused Playwright coverage for same-flush `Chat.messages()`, out-of-band
  appends, preserved partial cancellation/error, restore, and forged input.

## Handoff

- **Landed (`shinychat#6s8q`):** private Python ownership now records accepted
  input and transactional complete-message sends, including Chat-owned
  initial/restore paths and slash echoes. The shared fixture and focused
  coverage verify reactive invalidation, defensive reads, send failures, and
  complete-message wire metadata.
- **Resolved sequencing decision (2026-08-27):** retain legacy
  browser-reported `Chat.messages()` through `shinychat#6s8q`. Switching it
  before stream ownership regressed successful streamed conversations; an echo
  fallback would violate the server-authoritative boundary, and stream-end
  commits would prematurely implement an incomplete stream model. The public
  switch moves to `shinychat#ch09` after complete and streaming paths share
  the owner. Static `chat_ui(messages=...)` remains render-only.
- **History compatibility boundary (2026-08-27; `shinychat#ch09` →
  `shinychat#dy7g`):** `Chat.messages()` cuts over to the owner in
  `shinychat#ch09`. Until `shinychat#dy7g`, the legacy history effect binds
  directly to `Chat._reported_messages` so it remains browser-settlement-driven.
  This direct binding is a compatibility trigger only, not echo authority.
  Deferring the cutover and adding a terminal revision/flag are rejected. The
  regression must show partial owner visibility without a premature history
  save, followed by exactly one save after browser settlement.
- **Legacy icon disposition (2026-08-27):** while the legacy stream is active,
  its pending-message tuple drops a complete append's caller-supplied icon.
  The owner therefore records the emitted wire value (`None`), not the lost
  caller intent. `shinychat#ch09` deletes that queue. Legacy browser snapshots,
  bookmarks, and history UI records have no message-icon field, so restore
  emits and records no per-message icon until the later consumer cutovers.
- **Escalation disposition and handoff (2026-08-27; before implementation
  resumes):** a batched review of `shinychat#ch09` found the concurrent-start
  admission race, final-chunk loss on `chunk_end` failure, missing owner
  revision/history bridge (with the consumer follow-up in
  `shinychat#dy7g`), active-stream clear/restore invalidation, complete
  attribution, fixture gaps, and type gaps. The coordinator's disposition is
  **PATCH the existing transcript owner, not replace it**: these are missing
  enforcement or coverage of the already agreed transaction and attribution
  contract, and require no new mechanism. Switch this mechanism from
  iterative review to batched range review. Preserve all of that follow-up
  scope for the resumed implementation and treat this entry as the handoff
  before implementation resumes.
- **Admission decision (2026-08-27; `shinychat#ch09`):** permit one private
  fail-fast transcript admission token spanning prepare/send/commit. It
  rejects overlapping transcript mutations immediately; it never waits,
  queues, or retries, and it is cleared in `finally`. It creates no client
  protocol. Async sends yield, so atomic reservation is required to enforce
  explicit second-output failure and prevent complete append/clear/restore
  races; accepting races violates the agreed transactional contract. This is
  the narrowly approved exception to the no-new-flag tripwire, not a response
  queue.
- **Implementation landed/in review (`shinychat#ch09`; `cee6312f`):**
  implemented the approved private fail-fast transcript admission token across
  complete, stream, clear, and restore mutations; stream and complete
  attribution are captured before asynchronous transforms, terminal
  suppression closes the stream, and the history settlement compatibility
  trigger remains intact.
- **Verification (`shinychat#ch09`):** focused transcript/chat/matrix tests
  passed (68), Playwright history-idempotence passed (2), `make py-check-format`
  and `make py-check-types` passed, and `make py-check` passed (189 Playwright,
  599 non-browser tests).
- **Review handoff (2026-08-27; roborev job 1008,
  `edff995a-586d-4725-9d8a-f9ef8db076f0`; independent Luna review):**
  implementation is landed/in review. Disposition: patch the existing
  transcript owner, not replace it. Batched follow-up: terminal
  transform/final send must best-effort close the wire and owner while
  preserving the original error and partials; reserve output admission before
  async preparation; suppressed chunks retain source accumulation; replace
  preserves accumulated dependencies; greeting mutates only after successful
  clear; clear commit preserves accepted input arriving during its send; and
  terminal false cannot strand the stream. Forged-input disposition:
  `_reported_messages` remains a settlement trigger only; history content must
  come from the owner in `shinychat#ch09`; the separate bookmark consumer is
  already scoped to `shinychat#dy7g` and is not duplicated here.
- **Review fixes landed (2026-08-27; `785d3008`, `2754796e`,
  `f5c99965`):** the existing owner now holds its one fail-fast admission
  token across complete/root-stream preparation, retains accepted input across
  clear transport, commits transformed-away source, merges replacement
  dependencies, closes terminal false/error paths while preserving sent
  partials, and updates greeting state only after a clear succeeds. History
  still settles on `_reported_messages`, but now persists owner content; the
  legacy bookmark consumer remains deferred to `shinychat#dy7g`.
- **Verification:** focused Make selection passed (2 Playwright, 109
  non-browser); `make py-check-format`, `make py-check-types`, and
  `make py-check` passed (189 Playwright, 609 non-browser).
- **Historical review state (2026-08-27):** at that point,
  `shinychat#ch09` remained open pending independent rereview and
  `shinychat#dy7g` was not advanced.
- **Provisional decisions:** none.
- **Final rereview disposition (2026-08-27; Luna rereview; roborev job 1009,
  `6f6c55ed-0e0f-476b-8080-f176e35b9f91`):** retain the existing decision to
  patch the owner, not replace it. Required fixes:
  1. Preserve the original generator exception/cancelled status when terminal cleanup also fails.
  2. Propagate accumulated dependencies whenever a transformed replacement becomes visible, including after suppressed chunks.
  3. Eliminate forged report side effects.

  This explicitly supersedes the prior `_reported_messages`
  compatibility-trigger decision: browser input cannot be a settlement trigger
  because triggering a save/bookmark is state mutation. Use the existing owner
  revision/`Chat.messages()` plus checks for terminal assistant state and no
  active stream; add no new revision, flag, or queue. Move the narrow
  history/bookmark persistence authority needed for forged-input integrity into
  `shinychat#ch09`; `shinychat#dy7g` retains deletion/cleanup of the legacy
  report handler, stale deduplication, `ui_offset`, and remaining consumer
  migration. At that point, `shinychat#ch09` remained open pending the
  rereview and `shinychat#dy7g` was not advanced.
- **Final rereview fixes landed (2026-08-27; `8a903b31`, `7a0eeaa0`):**
  terminal cleanup now preserves and re-raises the original generator/body
  error or cancellation while the owner records the matching terminal status;
  transformed replacement sends and owner entries retain all accumulated
  source dependencies, including suppressed chunks; and history/automatic
  bookmark persistence now observes the existing owner revision with terminal
  assistant/no-active-stream gating. The legacy report handler remains for
  `shinychat#dy7g`, but forged reports cannot mutate transcript, history, or
  bookmarks.
- **Verification:** focused transcript/history/bookmark selection passed (16
  Playwright, 24 non-browser); full `pkg-py/tests/pytest/test_chat.py` passed
  (98); `make py-check-format` and `make py-check-types` passed; `make
  py-check` passed (191 Playwright, 616 non-browser).
- **Terminal outcome correction landed (2026-08-27; roborev job 1010):** both
  stream finalizers now classify cancellation while awaiting the terminal
  `chunk_end` after a normal body as `cancelled`, preserve no error payload,
  and re-raise `CancelledError`. Existing body error/cancellation outcomes
  still outrank cleanup failures. Job 1010's empty-message finding is covered
  by explicit `None` checks, so an original `RuntimeError("")` remains the
  recorded error rather than being replaced by a cleanup error.
- **Verification:** four direct finalizer regressions, full
  `pkg-py/tests/pytest/test_chat.py` (102), relevant Playwright stream/context
  coverage (2), `make py-check-format`, `make py-check-types`, and `make
  py-check` passed (191 Playwright, 620 non-browser).
- **Completion and next handoff (2026-08-27; `shinychat#ch09` →
  `shinychat#dy7g`):** `shinychat#ch09` is complete. Final evidence is
  implementation commit
  `e89fdf690d6b792c2c2937c2c923dd8ee34978fd`, full `make py-check` passed
  with 191 Playwright and 620 non-browser tests, Luna rereview clean,
  roborev job 1011 UUID `7ff311de-cee8-4b85-abc6-ac11d5c84eea` passed, and
  roborev jobs 1008-1011 are closed. The final fixes preserve the original
  generator exception/cancellation outcome through terminal cleanup,
  propagate accumulated dependencies through transformed replacements
  (including suppressed chunks), and eliminate forged report side effects.
  This supersedes the earlier needs-review/rereview/Next status entries.
  The next handoff is `shinychat#dy7g`, which remains open: `shinychat#ch09`
  owns the narrow history/bookmark persistence authority required for
  forged-input integrity, while `shinychat#dy7g` owns the remaining consumer
  migration and legacy report-handler cleanup, including stale
  deduplication, `ui_offset`, the Python report handler/input surface, and
  restore/switch/clear/out-of-band/etc consumer migration. `dy7g` work is not
  complete.
- **Lifecycle settlement and scope decision (2026-08-27; `shinychat#dy7g` →
  `shinychat#47fa`):** `_transcript_revision` is `Chat.messages()` invalidation
  only, not persistence settlement. Add one private lifecycle-local response
  callback scheduled via `reactive.on_flushed` after committed complete
  assistant sends and after every stream terminal outcome: ok, error,
  cancelled, or terminal failure. Replay/restore, clear, input, chunks, and
  initial messages do not schedule it; history and automatic bookmarking
  register callbacks. The temporary v1 bridge is removed when Phase 3
  persists at the choke point. It is not a durable settlement event, queue,
  flag, cursor, or new revision. Required tests include an old stream
  terminating after newer input and still invoking the correct lifecycle
  settlement behavior. The Python `shinychat.messages` handler,
  `messages_input_id`, and parser deletion moves from `shinychat#dy7g` into
  `shinychat#47fa`, so the JS and server protocol disappear atomically.
  `shinychat#dy7g` removes consumers, stale deduplication, `ui_offset`, and
  installs the lifecycle callback bridge.
- **Implementation ready for review (2026-08-27; `shinychat#dy7g`;
  `703ecb95`, `76adae55`):** complete assistant appends and every committed
  stream terminal state now schedule lifecycle-local callbacks through
  `reactive.on_flushed(..., once=True)`. The flush hook starts a one-shot
  reactive effect so history and automatic bookmark callbacks retain Shiny's
  reactive context; callback failures warn and cannot alter stream outcomes.
  Initial/replay/restore/clear/input/chunk mutations do not schedule a
  callback. V1 history rebuilds its active-path UI from the server transcript,
  assigns each response's UI to the response node following its input, and
  removes stale-report deduplication and `ui_offset`. The legacy
  `messages_input_id` bookmark exclusion is retained because its typed input
  is not bookmark-serializable. The Python `shinychat.messages` handler,
  input ID, and parser remain untouched for `shinychat#47fa`; JS, R, and
  assets are unchanged.
- **Verification (2026-08-27):** focused history/bookmark/lifecycle Make
  selection passed (42 Playwright, 270 non-browser); focused transcript/chat
  units passed (200); Ruff and Pyright passed. Full `make py-check` passed
  lint and types and reached 190/191 Playwright tests; its sole failure was
  an unrelated, untouched page-navigation resize timing assertion, which
  passed on immediate isolated rerun. `shinychat#dy7g` remains open with
  `needs-review`.
- **Blocking review fix landed (2026-08-27; `shinychat#dy7g`):** response
  callbacks now run directly in their originating
  `reactive.on_flushed(..., once=True)` turn under a temporary Shiny session
  and reactive context. The hook no longer installs a reactive effect or adds
  another flush, so a new-chat clear cannot run between a terminal response
  and its history/bookmark settlement. Direct regressions require single-flush
  settlement, preserve the source response across the immediate new-chat
  clear, and verify automatic bookmark serialization captures that source
  response exactly once. Verification passed focused lifecycle/history
  selections, `make py-check-format`, `make py-check-types`, and full
  `make py-check` (191 Playwright, 632 non-browser). `shinychat#dy7g`
  remains open with `needs-review`.
- **Approved settlement-drain handoff (2026-08-28; `shinychat#dy7g`):**
  terminal responses normally settle consumers at `reactive.on_flushed`.
  Every history destructive operation, including switch, new chat, active
  delete, and restore/rebuild/replay paths, preflights and rejects an active
  stream before any history or source mutation; after that preflight passes,
  it drains pending terminal settlements exactly once and then mutates. This
  prevents partial history mutation before `Chat.clear_messages()` rejects
  an active stream. A clear with no pending settlement invokes no consumers.
  A clear while a stream is active remains rejected.
  This is private lifecycle-local pending delivery, not a response/output
  queue: no content queue, waiting stream admission, or client protocol
  change.
  Consumer failures stay isolated. Carry these invariants into the
  implementation and regression review; leave the normal `on_flushed` path,
  issue status/owner/relationships, `needs-review`, and
  `work.attention="ok"` unchanged.
- **Settlement-drain implementation landed/in review (2026-08-28;
  `shinychat#dy7g`; `c225bb8e`):** each terminal response now has a private
  pending lifecycle-local delivery. Normal `reactive.on_flushed` settlement
  remains unchanged; clear and destructive history paths first reject an
  active stream, drain every pending delivery once, then mutate. The covered
  paths are clear, switch, new chat, delete, replay, branch navigation/edit,
  and initial restore/rebuild. Consumer failures remain isolated.
- **Verification:** focused terminal/history regressions passed, including
  pre-clear automatic bookmark serialization, original-history attribution on
  new chat, no-consumer clear, batched complete appends, active-stream
  zero-mutation rejection, stream terminal outcomes, and old-stream
  attribution. Focused history/bookmark/action Playwright tests passed (7).
  `make py-check` passed: Ruff, Pyright, 191 Playwright tests, and 640
  non-browser tests. JS, R, packaged assets, and the legacy
  `shinychat.messages` handler/input/parser remain untouched for
  `shinychat#47fa`. `shinychat#dy7g` remains open with `needs-review`.
- **Mechanism closeout evidence (2026-08-28; `shinychat#dy7g`;
  `a8f85899`, `f1ffcce5`, `4c59c81d` after `4c4356d2`):** lifecycle settlement
  hardening now waits for pending or in-flight external delivery to drain
  before destructive mutation, settles cancellation after scheduling,
  isolates warning-as-error consumer failures, and rejects direct or
  child-task reentrant destructive mutations. After reactive-lock arbitration,
  browser input/replay needs no new protocol. Full Python verification passed:
  Ruff, Pyright, 191 Playwright tests, and 645 non-browser tests. No JS, R,
  packaged-asset, or `shinychat#47fa` changes landed. Roborev rereview job
  `1012` was clean with no issues found.
- **Settlement pump replacement handoff (2026-08-28; `shinychat#dy7g`):**
  roborev review `1015` invoked the three-findings escalation valve, and the
  user selected **DELETE/REPLACE** of the N-independent per-delivery
  settlement-task topology. Commit `8e63c43b` implements exactly one
  Chat-owned FIFO pump: one callback-tuple deque, one runner, and one
  `on_flushed` wake-up. It preserves no response content, shielded
  normal/destructive joins, cancellation isolation, unsubscribe,
  `ContextVar` reentrancy rejection, active-stream preflight, terminal
  outcomes, and session-teardown cancellation. Terra's high-reasoning
  architectural review found no Phase 2 defect, and the deletion pass found
  no old per-delivery settlement abstractions. The focused FIFO test passed
  (1 selected); Ruff passed; Pyright reported 0 errors. Full
  `UV_CACHE_DIR=/tmp/shinychat-uv-cache make py-check` could not proceed past
  `uv run playwright install`, which was network-idle for more than five
  minutes; therefore no current full-suite result or known `.md` MIME result
  was obtained. No JS/R/assets or `shinychat#47fa` files changed. Next action:
  retry full `py-check` where Playwright setup completes.
- **Direct-suite follow-up (2026-08-28; `shinychat#dy7g`):** bypassing the
  installer yielded 652 non-browser passes, 1 skip, and the known unrelated
  `.md` MIME failure in `test_attachment_from_path`. All 191 Playwright tests
  fail before application assertions when Chromium launch returns
  `bootstrap_check_in ... Permission denied`; this applied to the restricted
  runner, not the feature. An unrestricted exact full-gate retry passed Ruff,
  Pyright, and all 191 Playwright tests. Its non-browser result was 652
  passes, 1 skip, and only the known unrelated `.md` MIME failure, so
  `make py-check` exits nonzero solely for that pre-existing test. No source
  files changed.
- **Approved private-callback invariant (2026-08-28; job 1017;
  `8a42c535`):** the `ContextVar` carries the source `Chat` plus the exact
  immutable callback tuple. While that tuple remains pending or running in
  `source_chat._pending_response_settlements`, any destructive `Chat`
  mutation in that task lineage fails fast, regardless of the target `Chat`.
  After dequeue, a copied child context is no longer blocked. This prevents
  cross-`Chat` settlement deadlocks without adding a stack, lock, registry,
  response queue, or client protocol; FIFO topology remains one deque, one
  runner, and one wake-up.
- **Verification:** 30 focused tests passed; Ruff and Pyright passed; the
  full 191-test Playwright suite passed, with 654 tests passed, 1 skipped,
  and the known MIME failure.
