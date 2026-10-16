# Investigate tn7c: bookmark soft-switch CI timeout

> **Historical investigation prompt (2026-10-16).** Investigation captured
> two same-signature failures: the outer row's visible non-interactive region
> received the click while its enabled select button was off-screen during
> drawer opening; no selection input was dispatched. Garrick approved the
> two test-only actual-button locator changes and the verification plan.
> `shinychat#tn7c` is closed with driver-approved scoped evidence: exact
> pushed HEAD `78819fa0` (source fix `506d92ab`) passed all CI on attempt 1.
> The local full suite's known pre-existing modal-test failure was explicitly
> retained and accepted for closure. See the issue for evidence and review
> dispositions. The historical instructions below do not authorize more
> retries, sibling fixes, restacking, or the R port.

You are a high-capability investigator in shinychat, working at:

`/Users/garrick/work/posit-dev/shinychat.worktrees/feat/history-exchange-tree`

Branch: `feat/history-exchange-tree`. Task: **`shinychat#tn7c`**.

**Investigation only.** Locate the first failed boundary with discriminating
browser/server evidence, report the root cause and smallest justified fix,
and ask Garrick to approve the disposition. Do not implement a fix, file an
upstream issue, close the task, or start the R port/restacking in this session.
Temporary diagnostics must not change behavior and must be removed before
handoff. This issue covers eventual resolution too, so investigation alone
is not completion.

## Why this is next / driver decision

On 2026-10-16 Garrick decided to resolve the remaining CI blocker before
reorganizing the Python work into reviewable stacked PRs, requesting review,
or starting the R port. The R work will stack on that Python foundation.
Green CI on the combined branch is the first gate; each stacked PR must then
be verified against its intended base. Do not keep retrying until green.

`tn7c` is parented to epic `shinychat#6d0d` and blocks `shinychat#05vb`
(R port) and `shinychat#9xgn` (stack preparation). Existing phase/dependency
reorganization is separate work: do not change the rest of the task graph.
The dated 2026-10-16 gate in `_plan/plan.md` supersedes the older sequencing
that said R was next and stack cutting happened only after the whole port.
`shinychat#73pm` is already CLOSED; do not reopen it or treat it as a new
approval task. Draft PR #379 remains the branch pointer:
https://github.com/posit-dev/shinychat/pull/379

## Read first and establish your baseline

1. `AGENTS.md`; `kata quickstart --agent`.
2. `kata show shinychat#tn7c --agent`, then the relevant comments on
   `shinychat#c87g` and `shinychat#7yc1`.
3. `_plan/plan.md`: current dated gate, §4, §7 (including bookmark design);
   `_plan/process.md`; `_plan/phase-5.8-mechanism.md` follow-up notes.
4. The failing test and `app_bookmark.py` / `app.py` in its directory.
5. `make help` before selecting development/testing commands.

Claim `shinychat#tn7c`, set `work.attention=ok`, and stamp
`work.branch=feat/history-exchange-tree`. Keep findings on the issue as you
work. At handoff set `work.attention=needs-human` and a precise
`work.attention_msg` describing the decision needed.

The evidence baseline is **`f7a75c5c29e42a2724c90df061984827b6fc8c22`**.
The c87g test fix is `70f991f245d73f82b4107e9b2fc78f10e5723e30`; f7a75c5c
only added durable notes. The handoff commit advances HEAD with documentation
only. Check `git status -sb`, `git log -5 --oneline`, and
`git diff f7a75c5c --stat`; confirm actual runtime equivalence rather than
assuming this stays true if later work lands. Do not reset another person's
changes. Source references below are at the evidence baseline and may shift.

## Exact failure and existing evidence

Test:

`pkg-py/tests/playwright/chat/history_v2_restore/test_history_v2_restore.py::test_v2_bookmark_switch_updates_url_in_place_and_reload_restores_target[chromium-app_bookmark.py]`

At lines 519–520 the test clicks **the outer history item** for A, then waits
10 seconds for `page.url == url_a`. Both recent CI attempts failed at that
B-to-A URL wait, not during auxiliary-input setup or final page reload.

| Evidence | Result |
| --- | --- |
| py-check run **38929075781**, attempt **1**, f7a75c5c | 225 passed / 1 failed; 513.01 s; sole failure is this test at line 520 |
| Same run, attempt **2**, same SHA | 225 passed / 1 failed; 509.89 s; same failure point |
| Three local untraced `FILTER=history` suites at the same runtime | 53/53 each, including this test; ~153–154 s |
| Earlier CI run **38804027725** | Same B-to-A URL timeout, recorded before the c87g fix |
| Subsequent earlier run **38805879533** | This test passed; c87g was the remaining failure then |

Run: https://github.com/posit-dev/shinychat/actions/runs/38929075781
Attempt-2 failed job:
https://github.com/posit-dev/shinychat/actions/runs/38929075781/job/117072664387

Recover the exact attempts, not just the latest log:

```bash
gh run view 38929075781 --attempt 1 --log-failed
gh run view 38929075781 --attempt 2 --log-failed
```

Preserved local artifacts (ephemeral; reconstruct from GitHub if missing):

- `/tmp/c87g-verification/ci-py-failed.log` — attempt 1.
- `/tmp/c87g-verification/ci-py-retry-failed.log` — attempt 2.
- `/tmp/c87g-verification/history-{1,2,3}.log` — passing local suites.
- `/tmp/c87g-investigation/c87g_probe.py` — prior external observation plugin;
  inspect/adapt if useful, not a drop-in repro for this different test.

All other checks were green at f7a75c5c: Python lint/types and unit jobs on
3.10–3.14, JS asset verification, R matrix. R initially had a Launchpad
HTTP-500 failure during dependency setup; run 38929076166 attempt 2 passed
without code changes. A local watcher TLS timeout was also infrastructure,
not a test result. No third Playwright retry was requested.

### What c87g does and does not tell you

**c87g is CLOSED.** Its test edited an old document after New chat initiated
an intentional bookmark-mode hard reload. The document died before Shiny's
normal debounced input update was sent; no restore callback fired in that
captured failure. The fix waits for the bare-URL document to load before
editing B's Shiny-bound input. Verified: 20 untraced solo passes, three
53-test history suites, both recent full CI target passes, 1129 unit tests,
clean lint/types, and clean roborev 1608. Overall CI was still red solely on
this soft-switch test; Garrick explicitly approved scoped c87g closure.

Do not reopen c87g or assume its root explains tn7c. The old
`investigate-c87g.md` prompt is historical, not current evidence: its family
hypotheses and claims about traces were corrected during investigation.
`7yc1` retains its separate desktop-navigation failure; its comments first
collected this soft-switch failure, whose ownership now moves to tn7c.
`ht4q` bookmark-pointer staleness and `bmqg` are also separate unless new
observations establish a relationship. Load sensitivity alone is not a root.

## Test workflow and production path to read

The fixture uses a local EchoChatClient, FileConversationStore, scope
`test-user`, `title=None`, and bookmark restore mode. `app_bookmark.py` wraps
`app.py` with `bookmark_store="server"`. No provider credentials are needed.
The installed Shiny pytest plugin supplies `local_app`.

The test creates A, captures `url_a`, clicks New chat, and waits for the
**drawer to be hidden**, not for a new document. It then creates B, captures
`url_b`, sets `window.__noReloadMarker = true`, selects A, and waits for
`url_a` (the failure). It later selects B, checks the no-reload marker and
transcript for both switches, reloads, and verifies B's restoration.
New chat intentionally hard-navigates; subsequent A/B switches should not.

Verified source map:

- **DOM target:** `js/src/chat/ChatHistoryDrawer.tsx`, `ConversationItem`, around
  460–475: outer `.shiny-chat-history-item` has no click handler; inner
  `.shiny-chat-history-item-select` button owns selection and is disabled
  while busy/disconnected. `handleSelect` around 236 returns early while
  busy/disconnected. An outer-div click does not express Playwright's
  readiness check for the actual select button; measure the hit target.
- **Readiness:** `js/src/chat/ChatContainer.tsx` around 1166 passes
  `busy={history.busy || history.historyTransitionPending !== null}` and
  `connected`. `js/src/chat/ChatApp.tsx` around 517 derives store busy from
  streaming state and completion-v2 input disablement. Seeing the full echo
  text is not automatically evidence all these gates have cleared.
- **Store/send:** `js/src/chat/historyStore.ts`, `actions.select` around
  50 and `isMutationBlocked` / `activeTransport`: select sends only when the
  transport is active and mutations are unblocked. Selection itself does
  not begin a transition. `actions.create` may use a completion request ID;
  inspect actual protocol/pending state rather than assuming it is absent.
  `js/src/transport/shiny-transport.ts`, `sendHistorySelect` around 122 sends
  `chat_history_select` for chat id `chat`, with `{id, ts}` and event priority;
  it returns if `Shiny.setInputValue` is unavailable.
- **Server receive:** `pkg-py/src/shinychat/_history.py`, `_on_select` around
  808: ignores an uninitialized partition, calls `controller.switch_to`,
  and reports exceptions as "Could not open conversation" notifications.
- **Server transaction:** `pkg-py/src/shinychat/_history_controller.py`,
  `HistoryController.switch_to` around 689: same-active-id no-op; record
  lookup; running-stream rejection; save current / restore target under
  mutation contexts; then `on_switch_restored(target)`.
- **Bookmark URL:** `pkg-py/src/shinychat/_history.py`,
  `_bookmark_restore_hooks` around 286, particularly `_on_switch_restored`
  around 328: send the target record's `bookmark_state_id`, or `url=None`
  if absent. Controller `send_navigate` around 1147 emits `history_navigate`.
- **Client receive/apply:** `js/src/chat/ChatApp.tsx` around 255 handles
  `history_navigate`; `js/src/utils/navigate.ts` calls `history.replaceState`
  for the soft path and `window.location.assign` when `reload=true`.
- **Important correction:** `history_navigate` IS IN `ENDS_DRAIN`
  (`ChatApp.tsx` around 62–75, receiver around 391–404). It flushes a finishing
  stream before handling the action, rather than waiting behind the tail.
  Other actions, including `history_update`, can be deferred and affect
  readiness. Do not describe navigation itself as tail-queued without
  evidence of a different mechanism.

## Investigation: discriminate, do not patch the symptom

Build a single chronology through the failed selection:

1. **Before/at the click:** record document/session identity, actual target,
   select-button disabled state, drawer state, busy/connected/pending state,
   active conversation, `url_a`, and `url_b`. Observe preceding New-chat
   navigation and B's terminal/settlement actions.
2. **Did selection leave the browser?** Observe `chat_history_select` input
   and websocket frames. Drawer hiding is useful context, not proof the
   store actually dispatched selection. If nothing is sent, identify which
   DOM/store/transport gate blocked it.
3. **Did the server receive and complete it?** Observe `_on_select`, target
   id, active id, stream status, mutation/restore entry/exit, exceptions,
   `on_switch_restored`, and the target bookmark state id.
4. **Did the action arrive and apply?** Observe emitted/received
   `history_navigate` payload, its URL/reload flag, `replaceState`, subsequent
   actions that might overwrite the URL, and transcript/active-id changes.
5. **Is the expected URL still valid?** Compare `url_a` with the target's
   current bookmark state id; inspect the actual bookmark mint/delete path
   if they differ. New chat's `save_current_locked()` is not by itself proof
   that A's bookmark is re-minted. Trace the callback that would mint it.

Competing hypotheses, NONE proven: blocked/misdirected outer-item click;
New-chat document/readiness race; incomplete B settlement; server switch or
restore failure; stale expected bookmark; client delivery/application issue;
upstream Shiny behavior only if isolated independently. The R-port concern
must be answered from the verified mechanism, not a generic timing concern.

## Reproduce and observe without masking it

Use supported Make targets; run commands expected to take time in the
background and wait for completion notifications, not foreground polling.

```bash
# Fast untraced target; record the outcome rather than assuming it fails.
PYTEST_ADDOPTS='--tracing=off' make py-check-playwright \
  FILTER=test_v2_bookmark_switch_updates_url_in_place_and_reload_restores_target

# Broader order/load context (~2.5 min locally).
PYTEST_ADDOPTS='--tracing=off' make py-check-playwright FILTER=history

# Exact full-suite scope used by CI (~8.5 min in the observed CI runs).
PYTEST_ADDOPTS='--tracing=off' make py-check-playwright
```

Run the unchanged baseline before adding probes. Local target/history passes
are expected possibilities; they do not refute two CI failures. If necessary,
use a bounded series of independent runs or the full suite to catch it.
Any artificial throttling/load must be labeled and corroborated; it is not
the primary evidence. No invented local failure rate or "always fails" claim.

Prefer observation-only browser lifecycle, input, websocket and server logs.
For c87g, full screenshot/DOM-snapshot tracing masked the race in observed
runs; lightweight API tracing captured it. That is a warning about perturbing
timing, not proof this issue behaves identically. Preserve a FAILING capture;
passing traced runs do not establish stability. Don't add waits, sleeps,
force-click, or replace the outer locator before capturing the original
failure. Don't log credentials. If CI-only reproduction persists and local
probes cannot discriminate, report that limit and ask permission for bounded
CI diagnostics instead of guessing or quietly changing the workflow.

Python gates: `make py-check-format`, `make py-check-types` (ALL pkg-py,
including tests), `make py-check-unit` (1129 at baseline). CI uses Python 3.14;
local evidence used Python 3.14.0 / Shiny 1.7.0. Capture actual installed
versions because the environment can change. If provider-normalization unit
tests fail with missing modules, `uv sync --extra providers` repaired the
previous local environment. Do not silently change dependency pins.

## Constraints and report back

- No production behavior changes, committed diagnostics, JS/SCSS/R edits,
  skips, timeout increases, retry policy changes, or weakened assertions.
  Use external browser probes / temporary observation-only Python logging;
  remove them and verify the original files before handing back.
- No restore guards, queues, timers, or new ordering flags. No branch rebase,
  force-push, stack creation, PR opening/readying, or unrelated backlog fixes.
- If JS/SCSS work becomes justified later, it needs approval and
  `make update-dist` before testing package-served assets. Do not diagnose
  changed JS source against stale distributed assets.
- No upstream report without evidence and a minimal reproduction independent
  of shinychat. Propose its body for driver approval rather than filing it.
- Leave tn7c OPEN. Investigation artifacts and verdict go on tn7c, with
  relevant cross-links and accurate attention metadata. Do not claim overall
  CI green just because the target passes.

Deliver:

1. Reproduction conditions and failing chronology locating the first failed
   boundary; artifact paths and SHA/versions.
2. Root cause and evidence excluding alternatives, or an explicit unresolved
   verdict naming what evidence is missing. No fabricated certainty.
3. Verdict: harness race, shinychat production defect, upstream defect, or
   unresolved. For a relationship to another issue, prove it separately.
4. Smallest proposed fix and why it preserves the intended behavior. Name
   its exact surface and whether R would copy the defect; flag parity work.
5. Regression/verification proposal: repeat untraced target and broader
   runs, retain A/B URL/no-reload/transcript/reload checks, applicable static
   and unit gates, external review, and green full-suite CI at the exact
   approved fix SHA before closure. Retain initial failing evidence.
6. Cleanup/worktree status and a clear driver decision request. Subsequent
   implementation is a separate approved step, not implicit in this prompt.
