Work on `shinychat#{{TASK}}` in shinychat's exchange-tree conversation-history effort.

Repository:
`/Users/garrick/work/posit-dev/shinychat.worktrees/feat/history-exchange-tree`

First read:
- `kata quickstart --agent`
- `kata show shinychat#{{TASK}} --agent`, its parent phase issue, and any issues it links to
- `_plan/plan.md`: the current phase in §4 and the reset decisions in §7
- `_plan/process.md`
- The current phase's mechanism note in `_plan/`, if it exists
- `AGENTS.md`
- `_plan/rationale.md` when the task touches design rather than mechanics

Kata hierarchy:
- Epic: `shinychat#6d0d`
- Phase 5.6 `shinychat#e1dv` → Phase 5.7 `shinychat#36z7` → Phase 6 `shinychat#05vb` → Phase 7 `shinychat#r0wj` → Phase 8 `shinychat#9xgn`

Always use fully qualified Kata references such as `shinychat#{{TASK}}`.

Before starting:
- Check that the task is not blocked (`kata show` lists `blocked-by` links) and that its phase is the current phase. Parent links do not gate readiness, so `kata ready` alone is not proof. If either check fails, stop and report.
- Claim it: `kata claim shinychat#{{TASK}}`, then `kata meta set shinychat#{{TASK}} work.attention ok`. Confirm `work.branch` is `feat/history-exchange-tree`.
- Run the relevant suite before changing anything (`make help` lists targets and filters). If it starts red, fix the red first or file it; do not build on it.

Doing the work:
- Implement the task yourself. You may delegate narrow investigation, verification, or review to subagents, but you own every change.
- Stay inside the issue's scope and the requirements in `plan.md`. If you find adjacent problems, file them as Kata issues under the right phase instead of fixing them here.
- Use small conventional commits, one logical change each, with Kata refs in the body and never in the subject. Group changes by subsystem so Phase 8 can cut the final diff into a review stack.
- Commit source changes separately from built assets; after any JS/SCSS change, run `make update-dist`.
- Do not rebase, force-push, or open PRs.
- When a mechanism or design decision comes up that the issue and durable documents do not settle, stop. Make the call only when you can give a confident, technically grounded recommendation consistent with `plan.md` and `rationale.md`; otherwise set `work.attention needs-human` with a `work.attention_msg` and ask Garrick. Record every resolved decision on the Kata issue and in the phase mechanism note, not only in chat.
- Apply the three-findings escalation valve (process.md §4).

Finishing:
- Run the full relevant gate (for Python work, `make py-check`; add `make js-lint js-test` or `make r-check` if you touched those areas).
- Request a roborev review on the task's commits and address or disposition every finding on the Kata issue.
- Close with evidence: `kata close shinychat#{{TASK}} --done --commit <sha> --message "<scope and verification>"`. If it is not complete, leave it open with `work.attention` and `work.attention_msg` set truthfully and a comment on what remains.
- Append a three-line handoff to the phase mechanism note: what landed, what's next, any provisional decision.
- End green and committed, then stop and report to Garrick.
