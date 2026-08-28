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
- **Next:** `shinychat#ch09` remains open and `needs-review` for independent
  rereview; do not move on to `shinychat#dy7g`.
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
  migration. Keep `shinychat#ch09` open with `needs-review` and truthful
  attention metadata. **Next:** finish the `shinychat#ch09` rereview; do not
  close or advance it.
