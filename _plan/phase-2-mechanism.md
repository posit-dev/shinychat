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
  committed message specs and in-flight stream accumulation.
- Mutations follow **prepare → send → commit**. A failed send never commits
  unsent content. Successfully sent stream content is committed eagerly to
  the in-flight entry so a later error cannot erase what the user saw.
- Accepted user input is committed by the priority-9999 input observer before
  application submit callbacks. It needs no transport send because the
  browser already rendered its optimistic user message.
- Complete output, stream start/chunk/end, clear, initial messages, slash
  command echoes, and restore paths all mutate through the owner.
- Public `Chat.messages()` takes a reactive dependency on owner revision and
  returns defensive projections. Existing successful messages keep their
  current shape; a preserved partial adds `status: "cancelled"` or
  `status: "error"`, and an errored partial adds `error: {"message": ...}`.
  Phase 3 moves those fields onto exchange nodes rather than inventing a
  second status model.

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

1. **Keystone complete-message slice (`6s8q`).** Add the private owner, revised fixture
   seed, accepted-input recording, transactional complete sends, and
   synchronous `Chat.messages()` while leaving the browser echo temporarily
   unused by that API.
2. **Transactional streams and attribution (`ch09`).** Route stream transitions through
   the owner, commit sent chunks eagerly, preserve partial cancellation/error,
   bind streams to opening exchanges, and delete the pending queue.
3. **Python consumer cutover (`dy7g`).** Move bookmark and current history consumers to
   server state; replace echo-triggered settlement; remove stale-report
   deduplication, `ui_offset`, and Python's `shinychat.messages` handler.
4. **Client echo deletion and acceptance audit (`47fa`).** Remove the JS reporter and
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

- **Landed:** design investigation and Phase 2 mechanism decisions.
- **Next:** claim `shinychat#6s8q` and begin the keystone complete-message
  slice.
- **Provisional decisions:** none.
