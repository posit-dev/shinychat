# Conversation Sharing — Design

**Date:** 2026-09-08
**Status:** Approved design, not yet planned/implemented. Not committed to git (AI-generated planning doc).

## Base branch context — read this first

This design is written **on top of PR #379 (`feat/history-exchange-tree`)**, the
exchange-tree history rewrite (studied at commit `52857be5`). That PR is a
**draft under structural review and is likely to change**. Consequences:

- All mechanism-level references here (`ConversationRecordV2`, `ExchangeNode`,
  the draft/persist-on-first-capture lifecycle, restore transaction names) are
  to that branch, not `main`. If #379's record model or lifecycle changes in
  review, the *mechanism* sections of this spec must be revisited; the
  *product* decisions are model-independent and stand regardless.
- Implementation is a **stacked PR** on `feat/history-exchange-tree`, not
  `main`. Building this against `main`'s v1 record model was explicitly
  rejected: v1 is scheduled for replacement and the R port will be built from
  #379's model.
- One piece is orthogonal to #379 and ships separately off `main` right away:
  the documentation reframing of the `scope` option (see "Related docs change"
  at the end).

## Problem

Today the single `scope` string couples three things: where conversations are
saved, where restore-by-ID looks, and what the history drawer lists. The docs
recommend `scope="global"` (or a group value) as *the* way to share history —
but a merged namespace is the wrong abstraction for sharing: everyone sees,
renames, and deletes everyone's conversations, and the `max_store_mb` eviction
budget becomes a shared pool. Meanwhile the 99% use case — per-user history
with opt-in sharing of a single conversation — is currently impossible: with
per-user scope, another user's restore-by-ID lookup happens in their own
partition and misses.

This feature adds real, opt-in, per-conversation sharing. `scope` keeps its
legitimate job (owner identity / storage namespace; shared team workspaces
remain a supported niche) and stops being marketed as the sharing mechanism.

## Product decisions (model-independent, locked)

| Decision | Choice |
| --- | --- |
| Recipient semantics | **Snapshot + fork.** Recipient sees the conversation as it was at share time. Sending a message forks it into a new conversation in *their* scope, seeded with the shared exchanges. Owner's copy never touched. |
| Access | **Explicit share action mints a high-entropy token.** Bare conversation IDs never grant access (v1-era IDs have ~40 bits of entropy and embed the timestamp). |
| Revocation | **Revocable.** Unshare invalidates the link. Already-forked copies are unaffected. |
| Default | **On wherever history is enabled**, author-disable via history options. Share dialog shows a prominent, unambiguous warning when the app runs on localhost (the link only works on that machine). |
| Content | **Active path only.** Abandoned edit branches stay private. Snapshots survive later owner *edits*; owner *delete* (or eviction) revokes the share (see storage policy). |
| Delivery | Spec covers Python + R; Python first (stacked on #379); R port follows #379's R port. JS/UI layer is shared and written once. |

## Architecture: reserved share partition + draft fork

Chosen over two alternatives:

- **B — token → pointer index, no copy:** saves storage but couples link
  lifetime to the owner's live record (eviction/deletion silently breaks
  links), needs path-reconstruction-from-historical-leaf at read time, and
  snapshot semantics become emergent rather than guaranteed.
- **C — piggyback on Shiny server bookmarks:** requires
  `bookmark_store="server"`, no revocation story, bypasses the conversation
  store (custom backends excluded), and bookmark-state restore is a known
  security-sensitive surface.

### Mechanism

Snapshots are ordinary conversation records stored in a **reserved partition**
`ConversationPartition(chat_id, "__shared__")`, keyed by the share token as
the conversation ID. `secrets.token_urlsafe(32)` (~256 bits, charset
`[A-Za-z0-9_-]`) passes the store's existing `CONV_ID_RE` validation, so the
`ConversationStore` ABC needs **zero changes** — custom backends inherit the
feature.

### Flows

**Share** (drawer item menu, or programmatic):

1. Client sends `history_share` with a conversation ID. Server verifies the ID
   exists in the **caller's own partition** (no minting shares of foreign
   conversations by guessed ID).
2. Server extracts the active path: deep-copy path nodes only; strip off-path
   `children`/`selected_child`; null `bookmark_state_id` (points at the
   owner's server bookmark); keep title and `values`.
3. Mint token; store snapshot with `record.id = token` under
   `(chat_id, "__shared__")`.
4. Stamp the token on the owner's record via a new **additive** field
   `share_token: str | None = None` on `ConversationRecordV2`
   (coordinate with #379 — one optional field). This powers: "currently
   shared" dialog state, *Update snapshot* (re-put under same token), and
   delete/evict cascade revocation.
5. Reply with the share URL. Server-side it is always the *relative* form
   (`?shinychat_share=<token>`) — the server doesn't reliably know its public
   URL behind proxies. The client dialog composes the absolute link from
   `window.location`; the programmatic `share()` returns the relative form.

**Open** (recipient):

1. Client reads `?shinychat_share=` and sends it as a startup input (sibling
   to the existing `{id}_history_url_id` plumbing). Server checks it **first**
   in the init effect — precedence: share token → bookmark restore context →
   mode-specific restore (browser/url). Runs inside the initial history
   decision so #379's input-admission gating covers it.
2. `store.get((chat_id, "__shared__"), token)`. Missing (revoked/garbage):
   non-blocking "This shared link is no longer available" notification, then
   normal startup. Found: copy with a **fresh conversation ID**, install
   through the standard fail-closed restore transaction, **do not persist** —
   this is #379's existing draft state (record in memory, nothing on disk,
   nothing in the drawer).
3. Client shows a pinned banner: "You're viewing a shared conversation. Send a
   message to continue it as your own copy." Input stays enabled — typing *is*
   the fork gesture.

**Fork** (recipient sends a message): no new machinery. The normal
`accepted_input` → capture → persist flow writes the installed record into the
recipient's partition on first exchange. Title carries over (so auto-retitle
doesn't fire); the conversation appears in their drawer; the client drops the
share param from the URL so reload lands on the fork.

**Revoke**: delete the token record from the shared partition; clear
`share_token` on the owner's record. Un-forked link holders get the
"no longer available" path.

### Storage policy

The shared partition sits **outside** `max_store_mb` eviction. Boundedness
comes from invariants instead: at most one live token per conversation
(re-share replaces), and deleting or evicting a conversation cascades to
revoke its share (via the `share_token` stamp — an orphaned snapshot would
have no owner-side handle and could never be cleaned up). Shared-partition
size is therefore proportional to real usage.

### Guards

- `scope="__shared__"` (string, or callable resolving to it) raises at setup;
  the string is reserved.
- Share/unshare actions are rejected server-side when sharing is disabled
  (forged client messages can't mint links).
- Share is absent for legacy v1 records (v2 only).

## API surface

### Python

- `HistoryOptions(share: bool = True)` — `False` hides the Share UI and
  rejects share/unshare server-side.
- `await chat.history.share(conv_id=None) -> str` (relative
  `?shinychat_share=<token>` URL; defaults to active conversation);
  `await chat.history.unshare(conv_id=None)`. Mirrors
  existing controller methods; the test suite wants them anyway.
- Model change: only the additive `share_token` field on
  `ConversationRecordV2`. No `ConversationStore` ABC changes.

### R

`history_options(share = TRUE)`; `share()` / `unshare()` on the history
handle, mirroring the Python controller. Same wire protocol; JS unchanged
between languages. Implemented in the R work cycle after #379's R port.

### Wire protocol (additions to the typed action union)

- Client → server: `sendHistoryShare(id, conversationId)`,
  `sendHistoryUnshare(id, conversationId)`; startup input
  `{id}_history_share_token` from the `?shinychat_share=` query param.
- Server → client:
  - `{type: "history_share_state", conversation_id, url: string | null}` —
    response to share/unshare; drives the dialog.
  - `{type: "history_shared_view", title}` — sent when a snapshot installs;
    switches the client into banner/shared-view state until fork.
  - `ConversationMeta.shared: boolean` in `history_update` — drawer badge and
    "Share…" vs "Manage share…" menu label.

### UI

- Drawer item overflow menu (with Rename/Delete): **Share…** /
  **Manage share…** → dialog.
- Dialog: link + copy button; **Update snapshot** and **Stop sharing** when
  already shared; localhost warning as a can't-miss alert (driven by
  `window.location.hostname`): "This app is running on your machine — this
  link won't work for anyone else. Deploy the app to share it."
- Shared-view banner pinned above the transcript; disappears on fork.
- All new CSS under the `.shiny-chat-*` prefix (project convention).

## Edge cases & error handling

- **Dead/invalid token**: revoked, cascade-deleted, or garbage all hit
  `get() -> None` → notification → normal startup. Store I/O errors go
  through the existing `notify_error` path.
- **Unreplayable turns** (provider mismatch in recipient's session): #379's
  degraded path applies unchanged — display restores, warning fires, fork
  proceeds with recoverable turn state.
- **`values`**: carried into the snapshot; recipient's `on_restore` runs with
  the owner's values (same-app state is the point). Documented caveat:
  `on_restore` input is data, not a trust signal — don't stash identity or
  authorization state in `values`. No opt-out in v1.
- **Reload**: before fork, the share URL re-opens the snapshot fresh; after
  fork, the param is gone and normal restore applies.
- **Concurrency**: simultaneous recipients get independent copies with
  distinct fresh IDs; no shared-write path exists. Revoke mid-view: the
  viewer keeps their in-memory snapshot and may still fork it.
- **Self-open**: owner opening their own link forks like anyone else; not
  special-cased.
- **Greeting**: restore transaction already clears it; share-open inherits.
- **Modules**: partition `chat_id` is the resolved/namespaced ID — a share
  link from one chat widget cannot open in another.

## Testing

**Python unit (TDD):** snapshot extraction (path-only, branches +
`selected_child` stripped, `bookmark_state_id` nulled, fresh ID, title/values
kept); token lifecycle (mint, re-share replaces, unshare deletes + clears
stamp, delete/evict cascade); guards (`scope="__shared__"` raises,
share rejected when disabled / for foreign conversation IDs / for v1
records); two-session controller lifecycle (share → open installs without
persisting or listing → fork persists to recipient partition, title carried,
owner untouched); dead-token fallthrough.

**Store contract:** extend the existing store test matrix
(File/InMemory-parametrized) with shared-partition token-keyed round trips,
proving the ABC is untouched.

**JS (vitest):** historyStore share/unshare actions and new action handling;
dialog component incl. localhost warning via injected hostname (the
non-localhost case can't be exercised in e2e, which runs on localhost); URL
param plumbing in and out (param dropped on fork).

**Playwright:** new `history_share/` app; two browser contexts against one
app (distinct browser tokens = distinct scopes = real cross-user sharing
without auth). Share → open in second context (banner shown, drawer
unchanged) → fork (appears in second drawer, first untouched) → revoke →
"no longer available". Plus a forged-action rejection test, consistent with
#379's existing ones.

**R:** same behavior matrix via testthat + shinytest2, in the R cycle.

## Related docs change (ships separately, off `main`, now)

Reword the `scope` docs in both packages: frame it as "owner identity /
storage namespace"; demote shared-string usage to a "shared team workspace"
pattern with an explicit warning (mutual visibility, mutual rename/delete,
shared eviction budget); stop recommending `scope="global"` as the way to
share. Untouched by #379.
