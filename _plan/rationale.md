# Rationale: why the exchange tree

**Companion to:** [plan.md](plan.md) · 2026-08-26
**Audience:** the shinychat team — this records why the converged design was
chosen, what alternatives were seriously considered, and what each camp's
concern gets in return.

## 1. Context

The `feat/turn-history-sync-redesign` branch was stopped after nine days and
297 commits; the [retrospective](../_dev/todos/pending/2026-08-13_client-turns-history-sync/retrospective/report.md)
diagnosed unbounded design scope meeting a process with no global-shape
sensor, and recommended a fork: rebuild on PR #311's skeleton (**Option A**,
display transcript as truth) or go turns-only (**Option B**, client turns as
truth). Planning for both options converged instead on a single design after
two insights from the maintainer, evaluated against the actual streaming
infrastructure in both packages.

## 2. The concerns on the table

Three positions had to be answered simultaneously:

- **The fidelity camp:** what was displayed must restore as displayed.
  shinychat supports usage entirely disconnected from ellmer/chatlas —
  manual `chat_append()` apps, multiple agents in one conversation — and a
  history feature must not orphan them.
- **The simplicity camp** (the retrospective's verdict): the failed branch
  died coordinating two histories (display messages vs client turns) with
  cursors, fingerprints, sweeps, and gates. Any successor must not manage
  that problem — it must not *have* it.
- **The divergence principle:** show the LLM one thing and the user another,
  or at least keep room for the two to evolve independently.

Option A and Option B each satisfy two camps and fail one. The converged
design satisfies all three, and the mechanism of *how* is the content of
this document.

## 3. The two insights that collapsed the fork

**Insight 1 — conversations branch only at user input.** Control returns to
the user only between exchanges, so the exchange (one user input plus
everything until the next user action, tool loops included) is the atomic
unit of history. This is integration-agnostic: it is as true for a manual
multi-agent app as for a chatlas one. It makes the record a *tree of
exchanges*, and it collapses edit, retry, and regenerate into one primitive
(create a sibling). It also resolved the long-standing shape mismatch
between provider turns (user/assistant/tool-result interleaved) and
shinychat display (one assistant block per submission): the exchange *is*
the display grouping, recorded at write time instead of reconstructed by
heuristics.

**Insight 2 — always capture what was sent; store turns adjacently.** The
server already sees every content spec it sends (a single choke-point
function in each language) and already accumulates streams as it sends them.
Capturing `messages` universally gives exact display fidelity to every app,
integration or not. The client turn delta is then stored *next to* the
messages on the same node — not derived from them, not reconciled with them.

## 4. Why this is not the failed branch's two-history problem

The branch's pain was **reconciliation**: two independently-evolving
histories plus machinery (cursor, prefix fingerprints, settlement sweep,
positional alignment) to keep them *in agreement* after the fact — and every
bug was a disagreement. Here the two facts are correlated **at write time**
by living on the same node, there is **no invariant that they agree**, and
nothing ever recomputes their relationship. Display truth and model truth
are allowed to differ *by design* — which is precisely the divergence
principle (R5). Disagreement stopped being a bug class and became a feature.

## 5. Why not Option A (display transcript as truth)

- It keeps `main`'s positional turn↔display attachment heuristic
  (`extend_record_linear`) — "an unverified two-history correlation in
  miniature" — and every roadmap feature that mutates the graph (edit, fork,
  retry, actions) multiplies exposure to it.
- It restores *pixels, not conversations*. For the multi-agent and manual
  apps the fidelity camp defends, a display-only record reloads looking
  right and being unable to continue — no client state comes back. The
  example used against coupling is the example where display-as-truth
  quietly fails.
- Its fidelity win is fully retained by the converged design's universal
  `messages` capture; nothing A does well is lost.

## 6. Why not Option B (pure turns-only)

- **Failure durability is delegated to SDK commit behavior.** Under
  turns-only, what survives a failed exchange is whatever the client
  happened to commit — ellmer/chatlas store partial results on
  interruption, but a hard failure before any response can leave nothing,
  and the user's input and display-only content are not guaranteed to
  survive. Retries (a roadmap feature) degrade to in-session-only. In the
  converged design a failure is just a node with `status: error` —
  durability is a property of the record, not of SDK internals.
- **Fidelity is capped at what turns encode.** UI-only appends and custom
  display content are lost; the divergence principle becomes fragile,
  because restore-time display would be a projection of turns that depends
  on the app's display methods being loaded and unchanged.
- **The coupling objection is real as product identity.** Pure turns-only
  makes shinychat's history a feature of ellmer/chatlas apps only. The
  converged design gives *every* app durable display history and branching
  automatically, and reserves state-resume as the blessed integration's
  (and later, custom payloads') value-add.

## 7. What each concern gets

| Concern | Answer in the converged design |
|---|---|
| Displayed = durable | Universal choke-point capture; restore replays sent specs through the live pipeline. Exact, automatic, integration-free. |
| No two-history machinery | One record; correlation at write time; no reconciliation, no cursor, no sweep, no settlement event (lazy close). |
| LLM/user divergence | `messages` and `turns` are separate facts on one node; content types + display methods stay the live mechanism; capture makes divergence durable. |
| Not coupled to ellmer/chatlas | Tree schema and `messages` are shinychat-owned and universal; turns are one named `state` entry behind generic capture/restore/rewind hooks. |
| Opinionated product | The blessed path is first-class and zero-config; the manual path is the same mechanism with fewer payloads, not a parallel world. The old duality collapses into default-vs-override. |
| Simple to articulate | "A conversation is a tree of exchanges; each node records what was shown and what the model saw; restore replays each to its own consumer." |
| Roadmap (edit/fork/retry/actions) | All are the sibling primitive or a pointer move on the tree; exchange id is the stable handle for actions. |

## 8. Costs accepted, on the record

1. **Provider format ownership for turn payloads.** ellmer
   `contents_record()` / chatlas `model_dump()` envelopes are the stored
   format; a provider schema change is a shinychat storage event. Mitigated
   by version-stamped payloads and degrade-with-warning replay; accepted
   because the alternative (a shinychat-owned turn schema) is a permanent
   translation layer — the thing this effort exists to delete.
2. **Archive semantics.** Restore shows what was shown then. Evolving a
   display method changes future exchanges only. (The tree leaves room for
   an opt-in "re-project from turns" mode later; it is not in scope. One
   scoped exception exists by design: the root node's live-bootstrap
   restore option, plan §3.4.)
3. **Cross-language history loading is off the table** (provider-serialized
   payloads).
4. **Mid-conversation `system`-role appends are not captured in `messages`**
   (never displayed, never on the wire); pre-input system state — the system
   prompt and app-attached turns — *is* captured, by the root-node baseline
   snapshot (plan §3.4).
5. **MarkdownStream is out of scope** (separate component and channel).

## 9. Relationship to prior decisions

- The 2026-08-14 ADR ("neither frozen HTML nor server re-derivation; store
  the wire message") is **upheld** for display — `messages` are stored wire
  specs — while re-derivation is adopted only where it is exact by
  definition: client state from the client's own recorded turns.
- The failed branch's preserve-partial abort decision is carried forward
  (a cancelled node keeps its captured partial) and was strengthened on
  2026-08-27 into the record-verbatim principle (plan §3.4, "shinychat
  records, it doesn't decide"): the client SDKs themselves store partial
  results on interruption, so discarding the display record cannot
  un-commit the model-side partial — preserve-partial is the only option
  where the two facts stay coherent. The Phase 2 re-derivation deliberately
  departs from #311's `abort()` (which discards) on this point.
- #311 is neither merged as-is nor discarded: its echo deletion,
  transactional send, and shared fixture instrument are the Phase 2 core;
  its display-transcript persistence layer is superseded by the exchange
  record.
- The infrastructure findings this design leans on (single choke points,
  existing turn-grouping and delta machinery, stream-finish signals, the R
  stream-correlation gap, the Python pending-flush bug) were verified
  against `main` on 2026-08-26 in both packages.
