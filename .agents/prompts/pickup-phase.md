Work as the orchestrator for Phase {{PHASE}} (`shinychat#{{PHASE_ISSUE}}`) of shinychat's exchange-tree conversation-history effort.

Repository:
`/Users/garrick/work/posit-dev/shinychat.worktrees/feat/history-exchange-tree`

First read completely:
- `_plan/plan.md`, especially §4 (this phase's scope and done-when) and §7 (2026-10-14 reset decisions)
- `_plan/process.md`
- `_plan/rationale.md`
- The phase mechanism note `_plan/phase-{{PHASE}}-mechanism.md`, if it exists
- The previous phase's mechanism note handoff, if this phase has no note yet
- `AGENTS.md`
- `kata quickstart --agent`
- `kata show shinychat#{{PHASE_ISSUE}} --agent` and every child issue

Kata hierarchy:
- Epic: `shinychat#6d0d`
- Closed: Phase 1 `shinychat#g49a`, Phase 2 `shinychat#kjyt`, Phase 3 `shinychat#qf2r`, Phase 4 `shinychat#azvt`, Phase 5 `shinychat#fg70`, Phase 5.5 `shinychat#pa98`
- Phase 5.6 `shinychat#e1dv` → Phase 5.7 `shinychat#36z7` → Phase 6 `shinychat#05vb` → Phase 7 `shinychat#r0wj` → Phase 8 `shinychat#9xgn`

Always use fully qualified Kata references such as `shinychat#e1dv`.

Phase entry:
- Confirm the previous phase is closed. If it is not, stop and report what remains.
- Run the suite before changing anything (`make help` lists targets). A phase that starts on red fixes the red first or files it.
- If the phase has no mechanism note, open `_plan/phase-{{PHASE}}-mechanism.md` with the phase's deferred design decisions and get Garrick's sign-off before feature code (process.md §3.4).
- If plan.md §4 lists work that has no child issue, create it under `shinychat#{{PHASE_ISSUE}}` with `--meta work.branch=feat/history-exchange-tree`, a self-contained body (symptom or goal, location, done-when), and real `--blocks`/`--blocked-by` edges. Children of a later phase must be `--blocked-by` this phase issue.
- Work only children of `shinychat#{{PHASE_ISSUE}}`. Parent links do not gate readiness, so `kata ready` may still list later-phase work; do not start it.

Your role is coordination only. Exclusively delegate implementation, investigation, testing, and review work to:
- medium subagents (sonnet, gpt-6.1-sol (medium effort), or `medium` subagents) for complex architectural or cross-module work.
- low subagents (haiku, gpt-6-luna, or `low` subagents) for narrower implementation, testing, documentation, and verification work.

Do not implement work yourself. Choose medium or low subagents according to task complexity, tuning reasoning effort to the task. Keep delegated write scopes disjoint when parallelizing. Review and integrate every returned change before proceeding.

With that said, you should undertake any small or administrative tasks that are quick and easy and are not worth a subagent call. Prioritize velocity without compromising quality and parallelize tasks as much as possible.

Respect the dependency chain; do not begin a blocked task early.

Follow `process.md` strictly:
- Claim and update each Kata issue truthfully (`work.attention`, `work.attention_msg`).
- Keep the phase mechanism note current with decisions, progress, and handoffs.
- Build the keystone vertical slice before hardening.
- Use small conventional commits aligned with Kata tasks, grouped by subsystem so Phase 8 can cut the final diff into a review stack (process.md §8.1). Put Kata refs in the commit body, never the subject.
- Commit source changes separately from built assets; after any JS/SCSS change, run `make update-dist`.
- Do not rebase or open stacked PRs. Bring `main` in by merge at the phase boundary if it has moved.
- When a task is complete, request a roborev review on the task's commits.
- Apply the three-findings escalation valve.
- End sessions green and committed, or explicitly parked in Kata.
- Do not expand scope beyond requirements in `plan.md`.

When a new design decision or issue arises, stop delegated implementation and raise it to the orchestrator. Make the call only when you can provide a confident, technically grounded recommendation consistent with the durable documents. Otherwise escalate it to Garrick before proceeding. Record every resolved decision in the phase mechanism note and relevant Kata issue, not only in chat.

Phase exit:
- Every child is closed with evidence, or explicitly re-parented or parked with Garrick's agreement.
- The branch is green and merged with current `main`.
- plan.md's status header and §4 entry for this phase are updated, and the mechanism note ends with a three-line handoff: what landed, what's next, any provisional decision.
- Close `shinychat#{{PHASE_ISSUE}}` with evidence, then stop and report to Garrick before opening the next phase.
