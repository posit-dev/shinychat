# Phase 5.9 mechanism: Python review-stack preparation

**Status:** Workflow reviewed by the driver; annotation feedback incorporated. The concrete PR/commit map and reconstruction execution still require approval.
**Kata:** Phase 5.9 `shinychat#f9hc`, directly under feature epic `6d0d`; blocks Phase 6 `05vb`. Independent modal prerequisite `8ej9` blocks reconstruction. Phase 8 `9xgn` remains final packaging after Phase 7.
**References:** [plan.md](plan.md) §4/§7.1–7.2; [process.md](process.md) §8.1; [phase-5.8-mechanism.md](phase-5.8-mechanism.md) latest closeout.

## Approved policies (driver discussion, 2026-10-16)

1. Review the stack as separately reviewable layers and merge/release the completed stack together. Each layer still needs a buildable, verified tree against its actual base; independent release of intermediate layers is not required.
2. Reconstruct from the final diff, as already decided in plan.md §7.2. Use small semantic commits, not the development chronology. Fold fix-ups and abandoned approaches into the changes they belong to; keep implementation and decisive tests together.
3. Commit subjects explain the change to another developer. Kata IDs and roborev review numbers are private-environment metadata: if retained, they are optional additional details in the commit body only, never the subject or a substitute for an understandable description. Preserve attribution and old-to-new evidence mapping separately from the subject.
4. Do not introduce `_plan/` or effort-local `.agents` handoff files into the reconstructed stack. Retain their history on the original development branch/archive. This supersedes introducing them and deleting them in a final PR. Audit every published stack level under cleanup task `1gjh`; do not indiscriminately remove unrelated project configuration.
5. Phase 6 remains blocked until the Python stack is published, verified, and human-approved as the R-port foundation. The driver may explicitly waive the human-approval gate later; record the waiver, its scope, and exact stack SHAs on `f9hc`/`05vb` before proceeding. Publication or green CI alone does not waive approval.
6. Reconstructed branches use `history-tree/{feat}`, for example `history-tree/transcript` or `history-tree/records`. These examples are not a final approved layer map. Keep the original branch intact; choose the exact archive/integration reference names when pinning the source.
7. The initial Python stack updates `js/dist/` and `pkg-py/src/shinychat/www/`, but preserves `pkg-r/inst/lib/shiny/` from the pinned upstream base. R keeps its working served bundle until the port begins. Refresh R assets from the verified Python foundation as an opening Phase 6 action, then validate R behavior. This is a driver-approved scoped exception to ordinary dual-package asset distribution.

## Observed source state

The initial source snapshot is `b382c176`; recorded all-green CI ran at `78819fa0`, not at this later documentation HEAD. The source fix for the last blocker is `506d92ab`. The previously accepted local modal-test exception remains historical evidence on `ftz9`/`tn7c`. New prerequisite `8ej9` owns its resolution before reconstruction; this plan does not carry that waiver into new stack verification.

Local-ref observations, without a fresh fetch: `origin/main` is `0bf2364a`, merge-base `94c4f426`; the branch has 542 commits not on that ref, while main has one commit not on the branch (`0bf2364a`, mock-session hooks, #428). The two-tip diff is 177 files, +40,095/-4,893, including working documents and assets. These numbers describe the investigation snapshot, not reviewer-facing stack size.

No branch reconstruction, archive-ref creation, force push, PR publication, upstream integration, or new test run has occurred during this planning discussion.

## Candidate review boundaries — not an approved transplant map

| Review unit | Main concern | Dependency to resolve before approving the cut |
|---|---|---|
| Transcript ownership and wire protocol | Coordinated JS/Python message ownership, stream identity and transport behavior | Client echo removal and server consumer cutover must remain compatible; retain the R-compatible protocol path until the R port. |
| Records, stores and v1 import | Exchange graph, versioned records, store boundary and released-form compatibility fixtures | Records/import use shared chat types; versioned validation and import are coupled. Do not split the validator from its required importer. |
| Exchange capture and state hooks | Recorder ownership, capture, restore/rewind plans and host contract | Recorder depends on transcript, record/store and client adapters; final chat host wiring may span several candidate units. |
| Restore, branching and app integration | Controller/wiring, bookmarks, actions, initialization, failure/retry semantics and UI affordances | Controller and recorder may need one review unit. End-to-end browser tests must exercise the actual intermediate tree. |

These are reader concerns, not directory-only copies or a promised count of four PRs. Move shared prerequisites to their first necessary layer. Combine units if a split would need placeholder APIs, a second implementation, temporary guards or an otherwise broken intermediate tree. No feature flags or production redesign solely to make the review stack thinner.

## Proposed activities

### 0. Resolve the local modal-test failure

Complete separate prerequisite `8ej9` before reconstruction. Compare the unchanged second-Escape failure on clean main and the feature source, identify whether it belongs to the test, production behavior, or environment, and verify the evidence-supported correction with repeated untraced focused runs plus the relevant full Playwright suite. Do not skip the test, weaken dismissal/cancellation assertions, or silently retain the old exception. An unavailable resolution requires an explicit driver decision, not automatic continuation. Read-only stack planning can proceed meanwhile; record how the resolution enters the integration reference.

### 1. Freeze a recoverable reference

After approval, preserve the exact original source commit under an immutable archive reference and record its recovery location. Keep the original branch/draft PR recoverable; reconstruct on new branches/worktrees named `history-tree/{feat}`, not by destructively rebasing its 542 commits. No force push to the original branch is authorized.

Fetch upstream when execution starts and pin the intended main SHA. Build a separate integration reference from the archived source, bringing main in by merge per plan.md §7.2. Validate that reference and record its exact SHA before using it as the reconstruction target. This separates upstream changes from packaging changes. If main advances later, record and verify a new reference instead of silently changing the comparison base.

### 2. Approve a concrete PR and commit map

Inventory the final source changes, including tests, fixtures, package exports, imports, public docs/changelogs and generated assets. Trace both imports and runtime/protocol dependencies. For each proposed PR record:

- Exact predecessor/base, reviewer question and supported intermediate behavior.
- Files or hunks introduced, changed or retired, with shared prerequisites assigned once.
- The small semantic commit sequence, meaningful subjects and implementation/test pairing.
- Relevant test commands and compatibility checks, including existing R behavior.
- Python asset/fixture copies, the pinned unchanged R asset snapshot, and any narrowly necessary integration edit.

Use reconstruction experiments only after the driver approves that activity; mark temporary results as experiments, not proven PR boundaries. If an experiment cannot run the case it claims to test, report the failure rather than bypassing the production path. Return the concrete map for driver approval before publishing or accepting it as the stack contract.

### 3. Construct and verify the new stack

Build each branch on its declared predecessor, using final-state code with the approved necessary adaptations. Do not replay obsolete mechanisms merely to preserve old commit boundaries. Preserve authorship/credit in the new commits where applicable and keep a source-to-new-commit mapping on the task; old review results provide context, not automatic approval of a newly adapted tree.

Run `make help` before selecting commands. Relevant supported targets include `make js-lint`, `make js-test`, `make py-check`, and `make r-check`. The Python type gate must cover the configured full scope, including tests, not an ad hoc narrower source-only check. Record exact commands, SHAs and results per PR level; use the agreed focused gates during construction and full CI before declaring each published level verified.

For this initial Python stack only, build each changed JS/SCSS level with `make js-build`, then copy it with `make py-update-dist` (run in that order, not as unordered parallel goals). Do not run `make update-dist` or `make r-update-dist` in these reconstructed levels: they replace R's served assets. Verify `pkg-r/inst/lib/shiny/` remains byte-for-byte identical to the pinned upstream base, while Python's runtime assets match that level's JS build. Keep source and asset commits separate when appropriate, but both inside the responsible PR; do not defer Python asset updates until the stack tip. Shared test-fixture synchronization is a separate concern: run `make r-sync-fixtures` when needed without refreshing R assets. Normal dual-package distribution resumes outside this scoped stack policy. At Phase 6 entry, use the verified foundation's built assets with `make r-update-dist` and verify R before port implementation.

Any new failure is a new disposition question, not permission to retry until green or skip the case. The modal prerequisite must supply resolution evidence rather than another blanket waiver. Review adapted coherent units, not every historical commit; record finding dispositions on the task and stop for a scope amendment if packaging would require a behavioral redesign.

### 4. Prove final-tree equivalence and publish

Compare the stack tip with the validated integration reference using an explicit difference manifest: omitted effort-local working documents; R asset copies deliberately held at the pinned upstream base; and reconstructed asset-provenance stamps. R asset differences from the integrated source are expected, not permission to change those assets arbitrarily: verify them against the pinned base at every level. Source, tests, public docs and JS/Python runtime asset content must have no unexplained difference. Python `GIT_VERSION` stamps will refer to reconstructed provenance; list those exact differences. Do not blanket-ignore built JS/CSS or source maps—investigate unexpected differences and require an explicit disposition.

Publish the verified initial Python stack with PRs targeted at their actual predecessors. Provide a bottom-to-top review guide, plain-language contracts/non-goals, a decisive test map and visible R/legacy/backlog follow-ups. Keep private ledger/review IDs out of commit subjects and do not make reviewers depend on private task records. Close draft #379 when its replacement stack opens, retaining the original source archive and linking the replacement PRs.

Collect human approval of the Python foundation. Changes made during review require affected-level verification, refreshed downstream bases and an updated final-tree comparison/evidence mapping. Then close `f9hc` with verification, publication and approval evidence (or an explicit driver waiver of approval), and hand the stable stack SHAs to Phase 6. Merely drafting this document or opening unverified PRs is not completion.

## Remaining decisions before execution

- The concrete hunk/commit map and actual viable PR count/order.
- Exact layer slugs under the agreed `history-tree/` prefix; archive/integration reference names; pinned upstream and validated reference SHAs.
- Exact per-level focused verification matrix and publication/review instructions.

The driver-approved policies do not resolve these mechanism choices or authorize destructive operations. Existing Phase 6/7 feature scope and backlog dispositions remain unchanged.

## Plan self-review

**96/100:** clarity 24/25, comprehensiveness 25/25, feasibility 22/25, consistency 25/25.

- [x] Name the pre-R work Phase 5.9, directly under the epic, and reserve Phase 8 for post-Phase-7 packaging to avoid a dependency cycle.
- [x] Preserve the existing final-diff decision, meaningful commit subjects, source recovery and driver approval boundaries.
- [x] Account for upstream drift and intermediate compatibility; update JS/Python assets at each responsible level while pinning R assets, and explain that difference in the final-tree comparison.
- [x] Record the branch prefix and give the local modal failure an independent pre-reconstruction task rather than carrying its historical exception.
- [x] Replace the superseded introduce-then-delete working-document policy and keep human approval as the default R gate.
- [ ] Resolve the concrete decomposition and exact verification matrix before reconstruction; current seams are intentionally provisional.

The revised workflow is sufficient to guide the next planning investigation, not proof that the four candidate cuts build independently. The driver reviewed the workflow and policies; concrete reconstruction/publication approval remains gated on the map and prerequisites.

## Annotation disposition (pn-b0caa7, 2026-10-16)

- General approval/task tracking: reuse existing `f9hc` rather than creating duplicate stack work; rename/reparent it as Phase 5.9 per the follow-up decision.
- Branch naming: adopted `history-tree/{feat}`; exact layer slugs remain part of the concrete map.
- Asset split: keep R's pinned served bundle unchanged during the Python stack; refresh R assets at port entry. Project guidance and final-tree comparison must reflect the exception.
- Modal failure: recommend and track resolution first under independent prerequisite `8ej9`; no new root cause, fix, test result or driver waiver is claimed.
