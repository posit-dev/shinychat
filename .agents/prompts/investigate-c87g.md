# Investigate c87g: bookmark-mode input-restore race

You are a high-capability investigator working in the shinychat repo at
`/Users/garrick/work/posit-dev/shinychat.worktrees/feat/history-exchange-tree`
(branch `feat/history-exchange-tree`, the exchange-tree conversation-history
feature branch). Your job is to ROOT-CAUSE kata issue `shinychat#c87g` and
report a verdict with evidence and a recommended disposition. This is an
investigation, not a fix — a fix lands only after the driver rules on your
verdict (see Deliverables).

Read first: `kata show shinychat#c87g` (plus related `ht4q`, `7yc1`, `bmqg`),
`_plan/plan.md` §7.8 (bookmark restore design), and the process docs
`_plan/process.md` if you need the kata/roborev conventions.

## The failure

`pkg-py/tests/playwright/chat/history_bookmark/test_history_bookmark.py::test_bookmark_mode_switch_restores_inputs[chromium]`

Failure signature (every observed failure): `expect_filter_state(page,
"second value")` (test line 24 helper, called after setting conversation B's
filter) times out at the full 30s with `#filter_state` stuck at
`filter: none` — the app's *initial* value. Passing runs complete in ~3s.
This is a lost/raced update, never slowness.

Observed rates: ~1/3 solo; 3/3 in full local `FILTER=history` runs; 2/2 in
full CI runs (CI runs all 226 Playwright tests). Deterministic under load,
which makes this the best moment to catch it.

## What the test does (read it and `app.py` in the same directory)

The app has one auxiliary input (`filter_text`, default `"none"`), carried
through conversations via `chat.history.on_save` / `@chat.history.on_restore`
(the restore callback does `ui.update_text("filter_text",
value=str(values.get("filter_text", "none")))`). The test:

1. Conversation A: set filter to `penguins`, chat, wait for `_state_id_` URL.
2. Click drawer's **New chat** (`.shiny-chat-history-new`).
3. Set filter to `second value`, expect `filter: second value` ← **fails here**.
4. Chat conversation B, switch back to A, expect `penguins` restored.

## Leading hypothesis (verify it; do not anchor on it)

**The New-chat hard navigation races step 3's input set.** The test comment
claims "No reload happens" — but production bookmark mode's
`_update_url_bookmark` (in `_history.py`, the `_bookmark_restore_hooks`
factory) does `send_navigate(None, None, reload=True)` when the active
conversation clears, and `new_chat` *always* fires `on_active_id_change(None)`
(see `HistoryController.new_chat` in `_history_controller.py`, whose comment
explains the announce-even-when-None rationale). A sibling test
(`history_v2_restore/test_history_v2_restore.py`) even documents this: "the
New chat click, which intentionally hard-navigates to clear the URL in
bookmark mode." So step 2 triggers a full page reload. If the reload
completes before step 3's `InputText.set`, the test passes (fill sticks on
the fresh document). Under load, the fill lands on the *old* document and
the navigation wipes it — `#filter_state` then reads `none` forever.
Playwright's locator resolution does not wait out an in-flight navigation
here.

If verified, the root cause is a test-harness race against intentional
production behavior, and the fix is test-side (await the navigation / a
post-reload sentinel after clicking New chat) — subject to the driver's
scope ruling, since the PR is deliberately being kept small.

## Alternate hypotheses (rank; eliminate or confirm each)

1. **Restore-with-empty-values clobber.** The app's restore callback defaults
   to `"none"` when `values` lacks `filter_text`. Any spurious/early restore
   firing with empty or stale `values` (e.g. an initial-restore settle, a
   switch restore racing the user's edit, a restore of a conversation saved
   before the input was captured) resets the input to `none`. Trace WHICH
   restore callbacks fire, with what values, in a failing run.
2. **The hard-navigation race** (above).
3. **py-shiny input-delivery timing (upstream candidate).** Browser inputs
   are delivered after `initializedPromise`/first flush (our `_init_history`
   documents working around this with `SilentException` retries). If the
   input set is lost inside Shiny's own flush/restore machinery rather than
   by navigation, this becomes an upstream issue — but only file upstream
   with a minimal repro that isolates py-shiny from shinychat.
4. **Bookmark settlement staleness (`ht4q` relation).** `ht4q` tracks the
   bookmark state id going stale on sibling navigation between response
   saves (`settle_bookmark_state_id` / `bookmark_pointer` in
   `_history_recorder.py`). Same subsystem; check whether the failing run
   also exhibits the ht4q signature (URL pointing at a deleted/stale state
   id) — they may share a root.
5. **Test-only timing assumptions** beyond hypothesis 2 (e.g. drawer-open
   waits, `send_user_input` racing stream settlement — see also the
   settlement-pump notes in `_chat_transcript.py`).

## Unifying angle worth 30 minutes

Two sibling flakes surfaced the same week (all in `7yc1`'s family):
`test_desktop_navigation_streaming_and_history_auto_open` and a one-off
`test_v2_bookmark_switch_updates_url_in_place_and_reload_restores_target`
timeout (10s `wait_for_url` after an in-place switch). Both suites contain
intentional hard navigations (bookmark-mode New chat). Check whether the
whole family is "tests racing intentional navigations / deferred client
actions" — the merged smooth-streaming client (`js/src/chat/ChatApp.tsx`,
`ENDS_DRAIN` deferral) paces and defers non-drain-ending actions, which
widened several timing windows on 2026-10-15. If one mechanism explains all
three, say so; that changes the disposition from N harness fixes to one.

## How to reproduce and observe

- Full filter run (fails ~always): `make py-check-playwright FILTER=history`
  (~2.5 min). For a faster loop, run a subset that still triggers it —
  e.g. the history_bookmark + history_v2_restore directories together, or
  the full filter under CPU throttling (`cpulimit`, or run a busy loop in
  parallel) to widen the window.
- Solo (~1/3): `uv run pytest pkg-py/tests/playwright/chat/history_bookmark/test_history_bookmark.py::test_bookmark_mode_switch_restores_inputs -q`
- Headed/traced: `make py-check-playwright-debug FILTER=test_bookmark_mode_switch_restores_inputs`
  (slowmo, traces, video). Capture a Playwright trace of a FAILING run and
  inspect: (a) is there a navigation (`about:blank` / reload marker / URL
  change to base) after the New-chat click? (b) did the `fill` on
  `filter_text` happen before or after that navigation? (c) which websocket
  messages carry `filter_text` updates, in what order?
- Server-side probes: instrument (temporarily, uncommitted) the app's
  `on_restore` callback to log firings with values, and/or
  `_restore_app_state` in `_history_controller.py`, to see whether a restore
  fires with empty values in the failing window.
- CI evidence: `gh run view 38805879533 --log-failed` (latest) and
  `38804027725` for the two failure instances.

## Environment notes

- If provider-normalization unit tests fail with `ModuleNotFoundError`, the
  uv env is missing the providers extra: `uv sync --extra providers`.
- `make help` lists all targets. `make py-check-unit` must stay green
  (1129 passed at HEAD). CI-equivalent type gate is `make py-check-types`
  (pyright over ALL of pkg-py, tests included — not just src).
- HEAD at investigation start: `587903f1` (phase 5.8 complete + main merged,
  incl. the smooth-streaming client).

## Constraints

- Do NOT change production behavior. Temporary diagnostics stay uncommitted
  or land behind an obvious `DEBUG` marker you remove before finishing.
- Do NOT fix the test or production code as part of this investigation; the
  fix (harness wait, production ordering change, or upstream report) is a
  separate, driver-approved step. The PR is deliberately being kept small.
- No JS/SCSS changes; no R changes.
- Kata hygiene: comment findings on `shinychat#c87g` as you go (claim it and
  set `work.attention ok` while you work it); reference `shinychat#ht4q`,
  `7yc1`, `bmqg` if the root cause touches them.

## Deliverables (report back; do not close c87g yourself)

1. **Root cause**, with the discriminating evidence (trace frames, logs, or
   a minimal repro) that eliminates the other hypotheses.
2. **Verdict**, one of: (a) test-harness race (name the exact race and the
   wait that would close it); (b) production ordering bug (name the
   mechanism and the minimal fix surface); (c) upstream py-shiny issue
   (attach a minimal repro that does not involve shinychat); (d) a shared
   mechanism covering the `7yc1` family.
3. **Recommended disposition** and, if (b) or (c), a proposed kata issue /
   upstream issue body.
4. Whether `ht4q` is the same root, and whether the family members are.
5. A note on whether the root cause is something the **R port (Phase 6)
   would copy** — the answer to that gates the port of the
   bookmark-restore path.
