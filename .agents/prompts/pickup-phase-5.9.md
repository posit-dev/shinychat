# Pick up Phase 5.9 — Python history review-stack reconstruction

Pick up **`shinychat#f9hc`** in the exchange-tree history effort. The user has approved the preparation and now wants the current giant Python feature branch converted into reviewable stacked PRs. Follow the kata feature process, but honor the driver-approved review-slice exception below. Do not reopen completed Phase 5 work or begin the R port.

## 1. The approval contract — read this before the older map

Plannotator approved the three Phase 5.9 documents at `a972aee6` with three guidance comments. The disposition is committed in **`e7bd68a2`**, in `_plan/plan.md` §7.1 and `_plan/process.md` §8.1, and at the top of the kata task body.

**Intermediate PRs are review slices, not independently working releases.** The user explicitly does not want compatibility churn just to keep each layer internally consistent or green. Require correctness, source equivalence and full verification at the **completed stack tip**. Disclose expected intermediate dependency gaps/test failures; do not conceal them with stubs, skips or weakened assertions.

The reviewed map still contains the earlier, now-superseded per-layer-green requirements and staged compatibility suggestions. Read it for concerns, source/test ownership and verification navigation, not as a mandate to implement those superseded mechanisms. In particular:

- Do not introduce or retain a temporary V1 public alias, legacy readiness adapter, store-narrowing assertion, always-allow stub, or extra line-level surgery solely to make an intermediate PR work.
- Prefer straightforward final-state composition within the approved three review concerns. Keep real guards that serve the final feature; this is not permission to simplify away actual admission/failure semantics.
- The "reviewer questions" are reading guides for future collaborators, not unresolved questions the driver must answer about an already implemented feature.
- Approval of this plan is NOT human approval of the future published Python foundation before R. That later gate still exists unless the driver explicitly waives it with exact accepted stack SHAs.
- Approval does not authorize bypassing branch protection/required checks or merging broken slices individually. Determine a whole-stack landing method before publication/merge; ask the driver if repository constraints require a choice. Do not merge automatically.

There is no need to restart the interview, resubmit the already approved preparation, or rewrite the reviewed artifacts over approval guidance. Record implementation state and decisions on the task and governing plan.

## 2. Read order and source of truth

1. `AGENTS.md` — including the scoped Python-only asset policy.
2. `kata quickstart --agent`, then `kata show shinychat#f9hc --agent`; this task is OPEN, owned by garrick, with planning approval recorded.
3. `_plan/plan.md` current status, Phase 5.9 scope, and §7.1 approval disposition.
4. `_plan/process.md` — unit-of-work review, scope discipline and current review-slice exception.
5. `_plan/phase-5.9-mechanism.md` — reviewed workflow, interpreted under the newer approval disposition.
6. `_plan/phase-5.9-stack-map.md` and `_plan/phase-5.9-change-inventory.csv` — fixed-snapshot preparation evidence; see the supersession warning above.
7. `_plan/phase-5.8-mechanism.md` latest handoff only if earlier source/test dispositions are needed. Do not start from older `.agents/prompts/pickup-task.md` / `pickup-phase.md` or stale `_dev` planning copies.

The current plan and approval disposition win over the older artifact's per-rung compatibility text. Do not rely on `/tmp` research reports or session logs being available.

## 3. Exact pickup state

Working source branch/worktree:

- Branch: `feat/history-exchange-tree`
- Worktree: `/Users/garrick/work/posit-dev/shinychat.worktrees/feat/history-exchange-tree`
- Main checkout: `/Users/garrick/work/posit-dev/shinychat` (already has `main` checked out; do not switch branches in someone else's worktree).
- Latest pre-handoff source HEAD: `e7bd68a247c8b599378e97b0559415221f7844a4`. The commit adding this prompt will be a documentation-only child: inspect and preserve the ACTUAL HEAD, not blindly the hash in this paragraph.
- Policy commit: `93e82051`; concrete map/inventory commit: `a972aee6`; approval disposition: `e7bd68a2`.
- Runtime analysis source: `b382c176`, compared with provisional base `0bf2364a`. Inventory: 177 paths, including 15 excluded working-artifact paths. That is a historical snapshot, not the final refreshed feature diff.
- Recorded history-feature all-green CI: `78819fa0`, not the later documentation HEADs. Do not claim those later HEADs ran CI.
- Local `origin/main` at handoff: `2fa02a27fdac0fb1e956719048c7388a63bf2b05`; fetch/pin anew when execution starts rather than assuming it stayed fixed.

**Modal prerequisite is resolved.** Unparented `shinychat#8ej9` was fixed separately from main, merged as PR #430 / `2fa02a27`. Its tree matches recorded CI-green PR head `c6ac0d9f`; the previous main snapshot differs only in the modal test. Do not redo the investigation or carry the earlier modal-test waiver. Integrate and verify the fix in the actual feature reference.

At handoff: clean worktree; no archive/reference/`history-tree/*` branches or stack PRs created by this preparation; no upstream integration, reconstruction experiments, builds or runtime tests performed here. Refresh status/refs/task state before relying on these observations.

## 4. First execution unit: preserve and validate the reference

1. Check git status and worktrees, task ownership/attention, and `make help`. Keep `work.branch` and the attention message truthful as execution moves to new worktrees.
2. Preserve the actual original source HEAD under a recorded immutable archive reference BEFORE reconstruction. Check for name collisions; do not replace existing refs. Keep the original branch/draft PR #379 recoverable. No reset/rebase/force push of that source branch; no cleanup of unrelated worktrees.
3. Fetch upstream, pin the actual main SHA, and create a separate integration reference/worktree from the archived source. Bring main in BY MERGE, not by rebasing the historical development commits. Resolve against the approved feature, preserving newer main changes such as #428 mock-session hooks and #430 modal synchronization instead of reverting them with old snapshot files.
4. Verify that integrated reference before recomposition. Use existing Make targets: `make js-lint`, `make js-test`, `make py-check`, `make r-check`, plus focused diagnostics if useful. Type checks must include configured tests scope, not a narrower source-only invocation. Run long commands in the background per harness rules; do not poll/sleep waiting for them.
5. If the full reference is red, diagnose/file the issue before continuing; this is not an expected review-slice failure. Do not retry until green, suppress tests, expand the old modal waiver, or build new feature code on an unverified baseline.
6. Record archive/base/integration SHAs, commands/results and any conflict resolution on `f9hc`. Regenerate the path inventory for this validated pair; retain the old CSV snapshot's provenance rather than silently substituting numbers.

No requirement to reproduce all 542 development commits, planning detours or per-commit automated-review fixes. The goal is final-state reconstruction with understandable semantic commits and credit/evidence mapping.

## 5. Reconstruct the approved concern-based stack

Proposed branch chain:

1. **`history-tree/records`** — record/type model, shared turn serialization, pure v1 import and its fixtures/tests.
2. **`history-tree/transcript`** — server transcript/stream/settlement ownership plus client protocol/UI primitives, with their tests and Python assets.
3. **`history-tree/exchange-history`** — complete live history/store/recorder/controller/state-plan/restore/branching integration and remaining acceptance tests.

Create new branches/worktrees based on the pinned main/predecessors. The detailed map is a starting point, not an instruction to fabricate temporary APIs or micro-split mixed hunks to support legacy intermediate execution. Whole final-file transfers or selected coherent final hunks are preferable where they reduce churn. Intermediate module/type/test-collection incompatibilities may be expected until later layers compose; describe their actual causes in the review guide.

Keep each PR focused for reading and use small semantic commits with implementation and decisive tests together where practical. Subjects must explain the change to other developers. Kata IDs and roborev numbers, if retained, belong ONLY as optional additional details in the commit BODY. Preserve contribution credits and source-to-new evidence mapping; private development IDs are not the reviewer contract.

No new features, new R implementation, opportunistic backlog fixes, runtime-selection flags, placeholder hosts, duplicate engines or compatibility frameworks. If the three review concerns need a material change, discuss that with the driver; don't use normal packaging adjustments as a reason to reopen completed design decisions.

## 6. Assets and working-document exclusions

- This Python stack updates `js/dist/` and `pkg-py/src/shinychat/www/` only. At a changed JS level, run `make js-build` and THEN `make py-update-dist` (separate ordered commands, not parallel Make goals).
- Preserve **all** `pkg-r/inst/lib/shiny/` bytes, including its `GIT_VERSION`, from the pinned main base. Do NOT use `make update-dist` or `make r-update-dist` in the reconstructed Python layers: they refresh R too. Outside this scoped policy normal dual-package distribution still applies.
- R test fixtures may advance independently: use `make r-sync-fixtures` where needed, with every canonical input named by the intermediate target present. That is not an R served-asset update.
- Keep Python assets current in the responsible review layer; do not defer their refresh until the final tip. Verify copies and account for provenance stamps; do not blanket-ignore bundles/source maps in the equivalence proof.
- Omit `_plan/` and effort-local `.agents` handoffs from EVERY reconstructed level. Retain them with the source archive. `1gjh` audits absence; do not invent a final deletion PR for files never introduced. Preserve unrelated project configuration; the scoped `AGENTS.md` build guidance is not an effort-local scratch note.
- Keep the JS legacy protocol compatibility path required for R. An opening Phase 6 action will refresh R assets from the verified Python foundation; do not start that port or refresh here.

## 7. Completed-tip proof, review and publication

The assembled tip must implement the full existing feature, not merely compile. Compare it with the validated integration reference using an explicit difference manifest: omitted working artifacts; intentionally pinned R assets; explained asset provenance. No unexplained source, test, public-doc or runtime-bundle changes. Do not drop source behavior simply because an intermediate reviewer or type checker reports a dependency not yet present there.

Run full unfiltered `make py-check`, complete JS lint/test/build checks and `make r-check` on the composed tree, with correct Python/R asset policy. Record exact SHAs, results and applicable CI. `FILTER=...` is supported pytest keyword selection for diagnostics, not a substitute for full checks and not `make -k`.

Review coherent reconstructed units under the kata/roborev process, in context of the completed tip. Missing later-layer dependencies are not instructions to add temporary fixes. Genuine final regressions need fixes plus tests; real out-of-scope findings go to backlog. Three findings on the same mechanism trigger the scope/escalation valve. Documentation-only/asset-only administration is self-reviewed, not a reason to request another large external review.

Before publication, confirm a whole-stack landing strategy that respects required checks/protection despite possibly red intermediate review branches. Stop for a driver decision if needed; do not disable checks, self-approve or auto-merge. Publish with accurate bases, a bottom-to-top review guide, dependency/failure disclosures and final-tip evidence. Close draft #379 only when the replacement review stack opens, leaving its source archive recoverable.

Keep `f9hc` OPEN until its verification/publication/human-approval contract is actually fulfilled. Phase 6 `05vb` stays blocked until the resulting Python foundation is published, fully verified and human-approved (or the driver explicitly waives that last requirement). Phase 8 remains final packaging after R/docs; this is Phase 5.9.

## 8. Session exit and handoff

End committed with full-reference/tip evidence, or explicitly park incomplete construction on `f9hc`. Partial review branches need not be green, but do not present them as validated release candidates. Keep the archived source and validated reference recoverable, update exact branch/SHAs and attention, and record what landed / next / provisional decisions. Leave no hidden test exceptions or stale approval claims.

## Prompt self-review

**96/100:** clarity 25/25, comprehensiveness 24/25, feasibility 22/25, consistency 25/25.

- [x] Put the approved-with-guidance contract ahead of superseded staged-map details; no extra planning approval required.
- [x] Distinguish the historical analysis snapshot, actual archive HEAD, resolved main-based prerequisite and unverified integration reference.
- [x] Preserve source/refs, pin R assets, exclude working documents, and retain strict full-tip verification and the later R approval gate.
- [x] Keep publication/merge protection choices explicit rather than promising individually mergeable red layers.
- [ ] Execution proof and whole-stack landing mechanism are deliberately the next agent's work, not claims made by this handoff.

Final check: the prompt is ready for pickup. It authorizes the approved workflow without claiming source integration, reconstruction, green final-tip checks or publication already occurred.
