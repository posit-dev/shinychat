# Process: how agents work through this plan

**Companion to:** [plan.md](plan.md) · 2026-08-26
**Status:** normative for this effort. If scratch docs contradict this
document, this document wins; if this document contradicts plan.md, plan.md
wins — amend whichever is wrong rather than forking the truth.
**Lifecycle:** keep `_plan/` tracked and current during implementation. Remove
the directory in the final cleanup before the completed effort merges to
`main`.

## 1. Standing structure

- **Human-led review before closure.** The user handles review cycles. Leave
  each kata task open until it has gone through at least one round of review,
  and record any findings and dispositions before closing it.
- **Coordinator + subagent structure**, with the review-loop rules in §4.
- **Kata is the system of record** (the `kata` CLI issue tracker; the
  session environment provides its usage conventions). One issue per work
  item; decisions and dispositions land on issues, never only in chat
  scrollback. See `kata quickstart --agent` for usage details.
- **Shared JSON fixture matrices** are the cross-language parity contract.
- **One adversarial critical-review pass** at subsystem completion,
  scheduled explicitly in Phase 5.

## 2. Scope discipline

1. **Requirements are the boundary.** Every mechanism must trace to a
   requirement line in plan.md §2. Before building any guard, gate, cache,
   counter, or invariant, name the requirement it serves. If you cannot,
   stop and ask.
2. **"Real, out of scope → backlog" is a standing disposition.** A reviewer
   or agent finding that is genuinely real but traces to no requirement gets
   a kata issue and a `backlog` label — *not* a fix on this effort. Never
   let "real" default to "required." When in doubt, backlog it and say so in
   the commit message.
3. **Multi-writer/CAS, greeting entanglement, bookmark fidelity beyond the
   pointer, cross-language loading, MarkdownStream: pre-refused.** Do not
   accept these from any reviewer, human or automated, without a plan.md §2
   amendment.
4. **Deletion pass with teeth.** Weekly, and at every pivot or re-plan: list
   what mechanism could be deleted, and count top-level abstractions against
   the plan's sketch. A pivot triggers a *scope* re-review, never just a
   re-sequencing.

## 3. Sequencing discipline

1. **Keystone-first, per phase.** The end-to-end data flow (capture → store
   → restore, ugly and flag-guarded) lands before any hardening of it. If
   your first commits on a phase are guards for code that doesn't exist yet,
   stop — you are hardening a mechanism that may not survive contact with
   the flow.
2. **Python to shape-stability, then the R port.** No commit-lockstep. A
   mechanism is shape-stable when it is reviewed, its finding-chains have
   terminated, and its fixtures exist. Parity is enforced by shared fixtures
   and structurally parallel error messages (same conditions, same
   information — not byte-identical strings), never by paired commits — and
   **parity is never a reason to suppress a correctness fix.** If a fix
   would diverge the languages, take the fix and file the parity delta as a
   kata issue.
3. **Port with the structure in hand.** When the R port begins, the
   implementer gets the Python structure as an explicit anchor document —
   port the structure first, then the behavior.
4. **Phase-gate mechanism notes.** Each phase opens with a one-page note
   resolving that phase's deferred mechanism decisions (field names, hook
   signatures, store layout — plan.md intentionally leaves these open),
   signed off by the driver *before* code. Mechanism decisions land on
   paper at the moment they're needed — not on day one (they churn) and not
   mid-commit (they hide).

## 4. Review-loop discipline

1. **The escalation valve.** Three review findings against the same
   mechanism = mandatory stop. The coordinator (or the human) answers one
   question before the next fix: *patch, or delete/replace?* Expect the
   answer to be delete/replace more often than patch — recurrence chains
   almost never converge by ordinary patching, and long ones generate
   defects of their own. When the valve fires, also flip that mechanism from
   iterative review to batched range review.
2. **Local correctness is not progress.** A reviewer verifies a change
   against its baseline; nobody in that loop checks the global shape.
   The shape checks live elsewhere: the requirements trace (§2.1), the
   deletion pass (§2.4), and the escalation valve (§4.1). Do not treat a
   green review as evidence the design is right.
3. **Fix-chains end in commits, not conversations.** If a finding is
   consciously deferred or declined, record the disposition on the kata
   issue so the next agent doesn't re-litigate it.

## 5. Verification discipline

1. **No feature code on unverified instruments.** Before Phase 3 feature
   work, verify (not repair — `main`'s instruments were confirmed healthy
   2026-08-27): the Playwright suite runs green at the branch point; the
   shared history-behavior matrix harness demonstrably discriminates (a
   deliberately broken fixture fails it in both languages); no pins or
   skips that can never fail have crept in; fixtures cover the value
   classes that matter (doubles, malformed lines, unreplayable turns).
   File and fix any gap before feature code.
2. **Fail openly.** A harness that can't run a case fails loudly; it never
   stubs, skips silently, or passes on aliased references. Tests exercise
   production paths, not test-only bypasses.
3. **A P1 caught by review and not by the suite is two bugs.** Fix the code
   and add the missing test in the same commit, or file the test gap as its
   own kata issue.

## 6. Context and knowledge hygiene (agents consume what we write)

1. **Stale context is an operational hazard.** When a decision supersedes an
   issue body or doc section, mark it *at supersession time* (edit the body,
   strike the section). At every phase transition, prune the working doc set
   the next agent will be pointed at.
2. **plan.md, rationale.md, and this document are the durable references.**
   Anything else that accumulates under this directory is scratch and must
   be treated as possibly stale.
   If scratch contradicts plan.md, plan.md wins; if plan.md is wrong, amend
   plan.md — don't fork the truth into a new doc.
3. **Decisions land in the plan, not in chat.** Any open-question resolution
   (plan.md §5) is recorded by editing plan.md with the answer and date. An
   open question that has been answered but not written down is still open.
4. **Design granularity:** commit domain-level decisions early; leave
   mechanism-level decisions to the phase that implements them (§3.4). If a
   mechanism decision must be made ahead of its phase, mark it provisional.

## 7. Working the plan (mechanics)

1. **One kata issue per work item**, parented appropriately; claim with
   `work.attention ok`, stamp `work.branch`, keep the attention pair
   truthful, close with evidence. Never end a session with the signal stale.
2. **Small conventional commits**, one logical change each, kata refs in the
   body.
3. **Every JS/SCSS change** rebuilds and copies dist assets in the same
   commit (`make update-dist` builds JS assets and copies them in one command) —
   the packages serve their own asset copies; skipping this ships stale JS.
4. **Escalate early on these tripwires** — each is a known money pit:
   anything touching the init/restore window; anything that wants a timer,
   a queue, or a second flag to manage ordering; anything that stores
   display-shaped content; anything where the fix is "add a guard for the
   guard." Stop and consult before building.

## 8. Multi-session structure (the feature will span many sessions)

Design against the failure mode where many locally-correct sessions add up
to an unmergeable whole. The defense: **every landed unit leaves the work
strictly better and mergeable** — so stopping at any point leaves value,
not wreckage.

1. **Phase 1 lands as independent PRs on `main`. Phases 2+ live on one
   long-running feature branch, worked as stacked PRs.** Each unit of work
   is a small, independently reviewable PR in the stack (each based on its
   predecessor) — never loose commits reviewed as one monolithic branch
   diff. Keep the stack rebased on `main`; drift is a finding. Settled
   segments merge from the bottom of the stack to `main` at phase
   boundaries, flag-guarded where the feature is incomplete, so finished
   value reaches the trunk instead of accumulating in the branch. A stack
   segment sitting unreviewed for more than a few sessions is itself a
   finding — stop and settle it.
2. **Slice vertically, not horizontally.** Within a phase, build one thin
   end-to-end case first (one submit → one captured node → one stored
   record → one restored display), then widen to more cases. Do not build
   layers of machinery before an end-to-end flow exists — we tried that and
   it didn't work; every layer was obsolete by the time the flow existed.
3. **Some changes are single-session atoms** — start them only with room to
   finish, land them whole, never leave them straddling a session boundary:
   a record-schema change, a wire-action change, the echo deletion, a store
   format change. Everything else can pause mid-phase safely.
4. **Session entry ritual:** read plan.md's current phase + this doc + the
   phase's mechanism note; check the kata board for the claimed item; run
   the suite *before* changing anything (a session that starts on red fixes
   the red first or files it — it does not build on it).
5. **Session exit ritual:** end green and committed (or explicitly parked
   with a kata issue holding the context). Update the kata item — close with
   evidence, or set the attention pair truthfully. Append a three-line
   handoff to the phase's mechanism note: what landed, what's next, any
   provisional decision taken. Prune or mark stale anything a future session
   would be misled by.
6. **When time runs short in a session, cut breadth, not integrity.** Ship
   the vertical slice for fewer cases rather than a half-done layer for all
   cases. A smaller finished thing beats a larger broken one every time.
7. **Prioritize phases by stranded value** — what's left on `main` if the
   effort halts right after each phase: after Phase 1, security and
   durability fixes shipped; after Phase 2, the echo and its bug class are
   gone; after Phases 3–4, Python has the feature; after Phase 6, parity.
   This is why settled stack segments merge at phase boundaries (§8.1):
   every phase boundary remains an acceptable permanent stopping point,
   and the ordering exists so the most valuable-if-stranded work happens
   first. Value still sitting in the unmerged stack when the effort halts
   is not stranded value — it is wreckage.
