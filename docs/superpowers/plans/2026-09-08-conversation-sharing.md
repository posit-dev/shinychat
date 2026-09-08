# Conversation Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opt-in per-conversation sharing: an owner mints a tokenized share link; recipients view a snapshot and fork it into their own history by typing.

**Architecture:** Snapshots are ordinary `ConversationRecordV2` records stored in a reserved partition `(chat_id, "__shared__")`, keyed by a high-entropy token. Opening a link installs an unpersisted copy through the normal restore transaction; the recipient's first message persists it into their own partition via the existing capture path (fork-on-write). Revoke = delete the token record.

**Tech Stack:** Python (shiny, pydantic), TypeScript/React (vitest), Playwright.

**Spec:** `docs/superpowers/specs/2026-09-08-conversation-sharing-design.md`

## Global Constraints

- Work on branch `feat/conversation-sharing`, stacked on `feat/history-exchange-tree` (PR #379, a draft that may change — if a rebase changes the surfaces named below, stop and flag it rather than adapting silently).
- **No changes to the `ConversationStore` ABC** (`pkg-py/src/shinychat/_history_store.py:40`). Custom backends must inherit the feature unchanged.
- The only record-model change is one additive field: `share_token: str | None = None` on `ConversationRecordV2`.
- New CSS identifiers use the `shiny-chat` prefix (`.shiny-chat-*`); never `shinychat-`.
- All Python tests: `make py-check-tests FILTER=<pytest -k expr>`; full checks `make py-check`. JS tests: `make js-test`. After ANY change under `js/`, `make update-dist` is required before Playwright tests or completion claims (packages serve their own asset copies).
- TDD: every task writes the failing test first. Python tests are `@pytest.mark.anyio` where async.
- Commit source changes independently of built-asset updates (assets in Task 9).
- No underscore prefix on new module-level functions in private modules (`_history*.py` are already private).

## File Structure

- `pkg-py/src/shinychat/_history_types.py` — `share_token` field, `new_share_token()`, `extract_shared_snapshot()`, `ConversationMeta.shared`.
- `pkg-py/src/shinychat/_history_store.py` — `SHARED_SCOPE` constant only.
- `pkg-py/src/shinychat/_history.py` — controller `share`/`unshare`/`open_shared`/cascade; `HistoryOptions.share`; input ids + handlers; `ChatHistory.share()/unshare()`; scope guard.
- `js/src/transport/types.ts`, `js/src/transport/shiny-transport.ts` — protocol additions.
- `js/src/chat/currentConversation.ts`, `js/src/chat/chat-entry.ts` — `?shinychat_share=` plumbing.
- `js/src/chat/historyStore.ts`, `js/src/chat/state.ts`, `js/src/chat/ChatApp.tsx` — client state + action routing + banner.
- Create: `js/src/chat/ShareDialog.tsx`; modify `js/src/chat/ChatHistoryDrawer.tsx` (menu item), `js/src/chat/chat.scss`.
- Create: `pkg-py/tests/playwright/chat/history_share/{app.py,test_history_share.py}`.

---

### Task 1: Record model — token, snapshot extraction, shared meta flag

**Files:**
- Modify: `pkg-py/src/shinychat/_history_types.py` (`ConversationRecordV2` at ~line 315, `ConversationMeta`, module-level helpers near `new_conversation_id()` at ~line 566)
- Test: `pkg-py/tests/test_history_types.py`

**Interfaces:**
- Produces: `ConversationRecordV2.share_token: str | None` (default `None`); `new_share_token() -> str`; `extract_shared_snapshot(record: ConversationRecordV2, *, token: str) -> ConversationRecordV2`; `ConversationMeta.shared: bool` (default `False`, set from `share_token` in `ConversationRecordV2.meta()`).

- [ ] **Step 1: Write the failing tests** (append to `pkg-py/tests/test_history_types.py`; reuse that file's existing imports/fixture helpers for building v2 records — `new_conversation_record_v2` plus `open_exchange`/`append_message` with `StoredMessage`/`CapturedMessage`, matching the file's existing v2 tests):

```python
def _v2_with_branch() -> ConversationRecordV2:
    """Root -> e1 -> e2, plus abandoned sibling e2b under e1."""
    rec = new_conversation_record_v2(title="Trip", client_info={"provider": "x"})
    rec.open_exchange("e1", _stored("user", "hi"))
    rec.append_message("e1", _captured("assistant", "hello"))
    rec.open_exchange("e2b", _stored("user", "old branch"))
    rec.set_active_leaf("e1")
    rec.open_exchange("e2", _stored("user", "new branch"))
    rec.append_message("e2", _captured("assistant", "ok"))
    rec.values = {"dataset": "cars"}
    rec.bookmark_state_id = "abc123"
    return rec


def test_new_share_token_is_long_and_conv_id_safe():
    from shinychat._history_store import CONV_ID_RE

    token = new_share_token()
    assert len(token) >= 40
    assert CONV_ID_RE.fullmatch(token)
    assert token != new_share_token()


def test_extract_shared_snapshot_keeps_active_path_only():
    rec = _v2_with_branch()
    snap = extract_shared_snapshot(rec, token="tok123")
    assert set(snap.nodes) == {"n_0000", "e1", "e2"}
    assert "e2b" not in snap.nodes
    assert snap.nodes["e1"].children == ["e2"]
    assert snap.nodes["e1"].selected_child == "e2"
    assert snap.active_leaf == "e2"
    assert snap.path_node_ids() == ["n_0000", "e1", "e2"]


def test_extract_shared_snapshot_scrubs_and_copies():
    rec = _v2_with_branch()
    snap = extract_shared_snapshot(rec, token="tok123")
    assert snap.id == "tok123"
    assert snap.share_token is None
    assert snap.bookmark_state_id is None
    assert snap.title == "Trip"
    assert snap.values == {"dataset": "cars"}
    # Deep copy: mutating the snapshot must not touch the original.
    snap.nodes["e2"].messages.clear()
    assert rec.nodes["e2"].messages
    assert rec.nodes["e1"].children == ["e2b", "e2"]  # original untouched


def test_v2_meta_reports_shared_flag():
    rec = _v2_with_branch()
    assert rec.meta(size_bytes=1).shared is False
    rec.share_token = "tok123"
    assert rec.meta(size_bytes=1).shared is True
```

If `test_history_types.py` lacks `_stored`/`_captured` helpers, add them (StoredMessage/CapturedMessage with one markdown segment, mirroring `_stored_message` in `test_history_controller.py:536`).

- [ ] **Step 2: Run tests, verify they fail** — `make py-check-tests FILTER="share_token or shared_snapshot or shared_flag"`. Expected: ImportError/AttributeError.

- [ ] **Step 3: Implement** in `_history_types.py`:

```python
# On ConversationMeta:
shared: bool = False

# On ConversationRecordV2, after bookmark_state_id:
share_token: str | None = None

# In ConversationRecordV2.meta(), add:
shared=self.share_token is not None,

# Module level, near new_conversation_id():
def new_share_token() -> str:
    # ~256 bits; doubles as the snapshot's storage key, so it must satisfy
    # the store's CONV_ID_RE (token_urlsafe output is [A-Za-z0-9_-]).
    return secrets.token_urlsafe(32)


def extract_shared_snapshot(
    record: ConversationRecordV2, *, token: str
) -> ConversationRecordV2:
    """A standalone copy of the active path, safe to hand to other users.

    Off-path branches, the owner's bookmark pointer, and the share stamp
    are stripped; the token becomes the snapshot's id (= storage key).
    """
    path = record.path_node_ids()
    snap = record.model_copy(deep=True)
    snap.id = token
    snap.share_token = None
    snap.bookmark_state_id = None
    snap.nodes = {nid: snap.nodes[nid] for nid in path}
    for i, nid in enumerate(path):
        nxt = path[i + 1] if i + 1 < len(path) else None
        node = snap.nodes[nid]
        node.children = [nxt] if nxt is not None else []
        node.selected_child = nxt
    return snap
```

`ConversationMeta`'s v1 `meta()` needs no change (`shared` defaults to `False`).

- [ ] **Step 4: Run tests, verify pass** — same FILTER. Also run `make py-check-tests FILTER=test_history_types` to catch regressions.

- [ ] **Step 5: Commit** — `git add pkg-py/src/shinychat/_history_types.py pkg-py/tests/test_history_types.py && git commit -m "feat(py): share token + active-path snapshot extraction"`

---

### Task 2: Reserved shared partition — constant + store round-trip proof

**Files:**
- Modify: `pkg-py/src/shinychat/_history_store.py` (constant near `HISTORY_BOOKMARK_ID`, ~line 24)
- Test: `pkg-py/tests/test_history_store.py`

**Interfaces:**
- Produces: `SHARED_SCOPE: str = "__shared__"` in `_history_store.py`.
- Consumes: `new_share_token()`, `extract_shared_snapshot()` from Task 1.

- [ ] **Step 1: Write the failing test.** `test_history_store.py` has a store fixture parametrized over `FileConversationStore`/`InMemoryConversationStore` (see its `store` fixture used by e.g. `test_v2_put_get_round_trip_uses_one_atomic_document`) — reuse it:

```python
@pytest.mark.anyio
async def test_shared_partition_round_trips_token_keyed_snapshots(store):
    from shinychat._history_store import SHARED_SCOPE
    from shinychat._history_types import (
        extract_shared_snapshot,
        new_conversation_record_v2,
        new_share_token,
    )

    rec = new_conversation_record_v2(title="t", client_info={})
    token = new_share_token()
    snap = extract_shared_snapshot(rec, token=token)
    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)

    await store.put(shared, snap)
    loaded = await store.get(shared, token)
    assert loaded is not None and loaded.id == token
    # Owner partition unaffected:
    assert await store.get(part(), token) is None
    await store.delete(shared, token)
    assert await store.get(shared, token) is None
```

- [ ] **Step 2: Run, verify fail** — `make py-check-tests FILTER=shared_partition_round_trips`. Expected: ImportError (`SHARED_SCOPE`).

- [ ] **Step 3: Implement** — in `_history_store.py` next to `HISTORY_BOOKMARK_ID`:

```python
# Reserved scope for share-link snapshots. Not a user scope: HistoryOptions
# rejects it, eviction skips it, and its conv ids are share tokens.
SHARED_SCOPE = "__shared__"
```

- [ ] **Step 4: Run, verify pass** (both store parametrizations).

- [ ] **Step 5: Commit** — `git commit -am "test(py): prove shared partition works through unchanged store ABC"`

---

### Task 3: Controller `share()` / `unshare()` + `history_share_state`

**Files:**
- Modify: `pkg-py/src/shinychat/_history.py` (`HistoryController`, after `switch_to`/`new_chat` block ~line 1705)
- Test: `pkg-py/tests/test_history_controller.py`

**Interfaces:**
- Consumes: Task 1 helpers; `SHARED_SCOPE` (Task 2); existing `_exchange_mutation()`, `_get_record`, `_put_record`, `_ExchangeRecorder.save_current_locked()/_persist_record()`, `send_history_update()`.
- Produces: `HistoryController.shared_partition -> ConversationPartition` (property, raises if `partition is None`); `async HistoryController.share(conv_id: str) -> str` (returns relative `?shinychat_share=<token>` URL); `async HistoryController.unshare(conv_id: str) -> None`. Both raise `RuntimeError` for unknown/non-v2 conversations. Neither sends `history_share_state` — the reactive handlers do (Task 5).

- [ ] **Step 1: Write failing tests** in `test_history_controller.py`, using its `_make_controller(store=..., use_exchange_tree=True)` helper (line ~480), `part()`, and `_FakeChat.actions`:

```python
def _persisted_v2(title: str = "t") -> ConversationRecordV2:
    rec = new_conversation_record_v2(title=title, client_info={})
    rec.open_exchange("e1", _stored_message("user", "hi"))
    rec.finish_exchange("e1", "ok", None)
    return rec


@pytest.mark.anyio
async def test_share_snapshots_into_shared_partition_and_stamps_owner():
    from shinychat._history_store import SHARED_SCOPE

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2()
    await store.put(part(), rec)

    url = await controller.share(rec.id)

    token = url.removeprefix("?shinychat_share=")
    assert url.startswith("?shinychat_share=") and len(token) >= 40
    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)
    snap = await store.get(shared, token)
    assert snap is not None and snap.id == token
    owner = await store.get(part(), rec.id)
    assert owner is not None and owner.share_token == token


@pytest.mark.anyio
async def test_share_reuses_existing_token_and_refreshes_snapshot():
    from shinychat._history_store import SHARED_SCOPE

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2()
    await store.put(part(), rec)
    url1 = await controller.share(rec.id)
    rec2 = await store.get(part(), rec.id)
    rec2.title = "renamed"
    await store.put(part(), rec2)

    url2 = await controller.share(rec.id)

    assert url1 == url2
    token = url1.removeprefix("?shinychat_share=")
    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)
    snap = await store.get(shared, token)
    assert snap.title == "renamed"


@pytest.mark.anyio
async def test_unshare_deletes_snapshot_and_clears_stamp():
    from shinychat._history_store import SHARED_SCOPE

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2()
    await store.put(part(), rec)
    url = await controller.share(rec.id)
    token = url.removeprefix("?shinychat_share=")

    await controller.unshare(rec.id)

    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)
    assert await store.get(shared, token) is None
    owner = await store.get(part(), rec.id)
    assert owner.share_token is None


@pytest.mark.anyio
async def test_share_rejects_unknown_conversation():
    controller, _ = _make_controller(
        store=InMemoryConversationStore(), use_exchange_tree=True
    )
    with pytest.raises(RuntimeError, match="not found"):
        await controller.share("c_deadbeef00")
```

- [ ] **Step 2: Run, verify fail** — `make py-check-tests FILTER="share_snapshots or reuses_existing_token or unshare_deletes or share_rejects_unknown"`.

- [ ] **Step 3: Implement** on `HistoryController` (import `SHARED_SCOPE` from `._history_store`, `extract_shared_snapshot`/`new_share_token` from `._history_types`):

```python
@property
def shared_partition(self) -> ConversationPartition:
    if self.partition is None:
        raise RuntimeError("HistoryController not initialized")
    return ConversationPartition(
        chat_id=self.partition.chat_id, scope=SHARED_SCOPE
    )

async def share(self, conv_id: str) -> str:
    if self.partition is None:
        raise RuntimeError("HistoryController not initialized")
    recorder = self._exchange_recorder
    if recorder is None:
        raise RuntimeError("Sharing requires exchange-tree history.")
    async with self._exchange_mutation():
        record = await self._shareable_record_locked(conv_id)
        token = record.share_token or new_share_token()
        await self.store.put(
            self.shared_partition, extract_shared_snapshot(record, token=token)
        )
        if record.share_token != token:
            record.share_token = token
            await self._persist_share_stamp_locked(record)
        await self.send_history_update()
    return f"?shinychat_share={token}"

async def unshare(self, conv_id: str) -> None:
    if self.partition is None:
        raise RuntimeError("HistoryController not initialized")
    if self._exchange_recorder is None:
        raise RuntimeError("Sharing requires exchange-tree history.")
    async with self._exchange_mutation():
        record = await self._shareable_record_locked(conv_id)
        token = record.share_token
        if token is None:
            return
        await self.store.delete(self.shared_partition, token)
        record.share_token = None
        await self._persist_share_stamp_locked(record)
        await self.send_history_update()

async def _shareable_record_locked(self, conv_id: str) -> ConversationRecordV2:
    """The live record when it's the target (saving it first), else a load
    from the caller's own partition — which is what makes foreign conv ids
    unshareable. Caller holds the exchange lock."""
    recorder = self._exchange_recorder
    assert recorder is not None and self.partition is not None
    live = recorder.record
    if live is not None and live.id == conv_id:
        await recorder.save_current_locked()
        return live
    loaded = await self._get_record(self.partition, conv_id)
    if not isinstance(loaded, ConversationRecordV2):
        raise RuntimeError(f"Conversation {conv_id!r} not found.")
    return loaded

async def _persist_share_stamp_locked(self, record: ConversationRecordV2) -> None:
    recorder = self._exchange_recorder
    assert recorder is not None and self.partition is not None
    if recorder.record is record:
        await recorder._persist_record()
    else:
        await self._put_record(self.partition, record)
```

- [ ] **Step 4: Run, verify pass.** Also `make py-check-tests FILTER=test_history_controller` for regressions (this file is big — expect a few minutes).

- [ ] **Step 5: Commit** — `git commit -am "feat(py): controller share/unshare with token-keyed snapshots"`

---

### Task 4: Cascade revocation on delete and eviction

**Files:**
- Modify: `pkg-py/src/shinychat/_history.py` (`HistoryController.delete` ~line 1949, `_evict_one` ~line 1300)
- Test: `pkg-py/tests/test_history_controller.py`

**Interfaces:**
- Consumes: Task 3's `shared_partition`.
- Produces: `async HistoryController._revoke_share_if_any(conv_id: str) -> None` (best-effort: never raises), called from `delete()` and `_evict_one()` before the owner-record delete.

- [ ] **Step 1: Failing tests:**

```python
@pytest.mark.anyio
async def test_delete_revokes_share():
    from shinychat._history_store import SHARED_SCOPE

    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2()
    await store.put(part(), rec)
    url = await controller.share(rec.id)
    token = url.removeprefix("?shinychat_share=")

    await controller.delete(rec.id)

    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)
    assert await store.get(shared, token) is None


@pytest.mark.anyio
async def test_delete_survives_snapshot_revocation_failure():
    store = InMemoryConversationStore()
    controller, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2()
    await store.put(part(), rec)
    await controller.share(rec.id)

    original_delete = store.delete

    async def failing_delete(partition, conv_id):
        if partition.scope == "__shared__":
            raise OSError("disk gone")
        await original_delete(partition, conv_id)

    store.delete = failing_delete  # type: ignore[method-assign]
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        await controller.delete(rec.id)  # must not raise
    assert await store.get(part(), rec.id) is None
```

Also add the eviction variant: share a record, then force `_evict_one(rec.id)` and assert the snapshot is gone (mirror how existing eviction tests in this file drive `_evict_one`/`_evict_if_needed`).

- [ ] **Step 2: Run, verify fail** — `FILTER="delete_revokes_share or revocation_failure"`.

- [ ] **Step 3: Implement:**

```python
async def _revoke_share_if_any(self, conv_id: str) -> None:
    """Best-effort share cleanup for a conversation being removed. A failure
    must never block the removal itself."""
    if self.partition is None or self._exchange_recorder is None:
        return
    try:
        live = self._exchange_recorder.record
        if live is not None and live.id == conv_id:
            token = live.share_token
        else:
            loaded = await self.store.get(self.partition, conv_id)
            token = (
                loaded.share_token
                if isinstance(loaded, ConversationRecordV2)
                else None
            )
        if token is not None:
            await self.store.delete(self.shared_partition, token)
    except Exception as e:
        warnings.warn(f"Could not revoke share link: {e}", stacklevel=1)
```

In `delete()`, immediately after entering `_exchange_mutation()` (before `on_evict`/`store.delete`), and in `_evict_one()` before its `store.delete`, add `await self._revoke_share_if_any(conv_id)`.

- [ ] **Step 4: Run, verify pass** (including the eviction variant).

- [ ] **Step 5: Commit** — `git commit -am "feat(py): revoke share links when conversations are deleted or evicted"`

---

### Task 5: Options, scope guard, input handlers, public API

**Files:**
- Modify: `pkg-py/src/shinychat/_history.py` (`HistoryInputIds` ~line 103, `HistoryOptions` ~line 138, `ChatHistory` ~line 2274, `_start()` handler block ~line 2863)
- Test: `pkg-py/tests/test_chat_history.py` (options/guard), `pkg-py/tests/test_history_controller.py` if a helper fits better

**Interfaces:**
- Produces: `HistoryOptions(share: bool = True)`; `HistoryInputIds.share/.unshare/.share_token` (`{chat_id}_history_share`, `{chat_id}_history_unshare`, `{chat_id}_history_share_token`); `ensure_scope_not_reserved(scope: str) -> None` (module-level in `_history.py`, raises `ValueError` on `SHARED_SCOPE`); `async ChatHistory.share(conv_id: str | None = None) -> str`; `async ChatHistory.unshare(conv_id: str | None = None) -> None`. Reactive handlers `_on_share`/`_on_unshare` reply with `{"type": "history_share_state", "conversation_id": <id>, "url": <str|None>}`.
- Consumes: Task 3's `controller.share/unshare`.

- [ ] **Step 1: Failing tests** (in `test_chat_history.py`, following its existing `HistoryOptions` tests):

```python
def test_history_options_share_defaults_on():
    assert HistoryOptions().share is True
    assert HistoryOptions(share=False).share is False


def test_reserved_scope_rejected():
    from shinychat._history import ensure_scope_not_reserved

    with pytest.raises(ValueError, match="__shared__"):
        ensure_scope_not_reserved("__shared__")
    ensure_scope_not_reserved("alice")  # no raise
```

- [ ] **Step 2: Run, verify fail** — `FILTER="share_defaults_on or reserved_scope"`.

- [ ] **Step 3: Implement:**

`HistoryInputIds`: add fields `share`, `unshare`, `share_token`; extend `for_chat()` with `share=RID(f"{chat_id}_history_share")`, `unshare=RID(f"{chat_id}_history_unshare")`, `share_token=RID(f"{chat_id}_history_share_token")` (`all_ids()` picks them up via dataclass fields, keeping them bookmark-excluded).

`HistoryOptions.__init__`: add `share: bool = True` parameter + `self.share = share`, and this docstring entry (keep the existing entries untouched — the broader `scope` rewording ships as a separate PR off `main`):

```
share
    Whether users can share conversations. When ``True`` (the default),
    each conversation's menu offers a Share action that mints a revocable
    link (``?shinychat_share=<token>``); anyone who can access the app can
    open the link to view a snapshot and continue it as their own copy.
    Sharing requires a store that all sessions can reach and is only
    useful when the app is deployed somewhere recipients can access.
    Set ``False`` to disable the UI and reject share actions.

    A shared snapshot carries the conversation's saved ``values``, and a
    recipient's ``on_restore`` callbacks run with the sharer's values —
    treat ``on_restore`` input as data, not a trust signal, and don't
    stash identity or authorization state in ``values``.
```

Module level:

```python
def ensure_scope_not_reserved(scope: str) -> None:
    if scope == SHARED_SCOPE:
        raise ValueError(
            f"scope {SHARED_SCOPE!r} is reserved for conversation sharing; "
            "choose a different scope string."
        )
```

Call it in `_init_history` right after `owner_scope = scope()` (before building the partition).

`ChatHistory`: store the flag in `__init__`/`_start` (`self._share_enabled = options.share`, mirroring how other options flow), and add public methods after `save()` (~line 2365), following `save()`'s controller-guard pattern:

```python
async def share(self, conv_id: str | None = None) -> str:
    """Mint (or refresh) a share link for a conversation.

    Returns the relative URL (``?shinychat_share=<token>``); combine with
    the app's own URL to produce the absolute link. Defaults to the active
    conversation.
    """
    controller = self._controller
    if controller is None or controller.partition is None:
        raise RuntimeError("Chat history is not initialized")
    if not self._share_enabled:
        raise RuntimeError("Sharing is disabled for this chat.")
    if conv_id is None:
        conv_id = controller._active_id_now()
        if conv_id is None:
            raise RuntimeError("No active conversation to share.")
    return await controller.share(conv_id)

async def unshare(self, conv_id: str | None = None) -> None:
    """Revoke a conversation's share link (no-op when not shared)."""
    controller = self._controller
    if controller is None or controller.partition is None:
        raise RuntimeError("Chat history is not initialized")
    if not self._share_enabled:
        raise RuntimeError("Sharing is disabled for this chat.")
    if conv_id is None:
        conv_id = controller._active_id_now()
        if conv_id is None:
            raise RuntimeError("No active conversation to unshare.")
    await controller.unshare(conv_id)
```

Reactive handlers in `_start()` beside `_on_rename` (~line 2890), same shape:

```python
@reactive.effect
@reactive.event(chat._session.input[ids.share])
async def _on_share():
    payload = chat._session.input[ids.share]()
    try:
        if not self._history_action_admitted():
            return
        if controller.partition is None:
            return
        if not self._share_enabled:
            raise RuntimeError("Sharing is disabled for this chat.")
        conv_id = str(payload["id"])
        url = await controller.share(conv_id)
        await chat._send_action(
            {
                "type": "history_share_state",
                "conversation_id": conv_id,
                "url": url,
            }
        )
    except Exception as e:
        await notify_error("Could not share conversation", e)


@reactive.effect
@reactive.event(chat._session.input[ids.unshare])
async def _on_unshare():
    payload = chat._session.input[ids.unshare]()
    try:
        if not self._history_action_admitted():
            return
        if controller.partition is None:
            return
        if not self._share_enabled:
            raise RuntimeError("Sharing is disabled for this chat.")
        conv_id = str(payload["id"])
        await controller.unshare(conv_id)
        await chat._send_action(
            {
                "type": "history_share_state",
                "conversation_id": conv_id,
                "url": None,
            }
        )
    except Exception as e:
        await notify_error("Could not update sharing", e)
```

If `chat._send_action`'s parameter is typed against a Python-side action union/TypedDict set, add a `HistoryShareStateAction` TypedDict beside the existing action types (match how `HistoryNavigateAction` is defined) rather than passing a bare dict.

- [ ] **Step 4: Run, verify pass**, then `make py-check-types` (new public methods must type-check).

- [ ] **Step 5: Commit** — `git commit -am "feat(py): share option, reserved-scope guard, share/unshare actions and API"`

---

### Task 6: Share-open, unpersisted install, fork-on-write

**Files:**
- Modify: `pkg-py/src/shinychat/_history.py` (`_restore_initial_exchange_record` ~line 1562, `_restore_exchange_record_locked` ~line 1479, `_ExchangeRecorder._persist_record` ~line 736, `new_chat` ~line 1683, `switch_to` v2 branch ~line 1650, `_init_history` ~line 2707)
- Test: `pkg-py/tests/test_history_controller.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `async HistoryController.open_shared(token: str) -> bool` (False = unknown token / not v2; True = installed as unpersisted view). Sends `{"type": "history_shared_view", "title": <str>, "active": True}` on success. `HistoryController._shared_view_pending: bool` (init False). `async HistoryController._notify_shared_fork_persisted(record) -> None` called from `_ExchangeRecorder._persist_record` after a successful `store.put`; when pending it clears the flag, calls `send_navigate(None, record.id)`, and sends `{"type": "history_shared_view", "title": None, "active": False}`. `_restore_initial_exchange_record`/`_restore_exchange_record_locked` gain keyword `publish_active_id: bool = True`.

- [ ] **Step 1: Failing tests:**

```python
async def _shared_setup() -> tuple[HistoryController, InMemoryConversationStore, str]:
    store = InMemoryConversationStore()
    owner, _ = _make_controller(store=store, use_exchange_tree=True)
    rec = _persisted_v2(title="Trip")
    await store.put(part(), rec)
    url = await owner.share(rec.id)
    token = url.removeprefix("?shinychat_share=")
    recipient, _ = _make_controller(store=store, use_exchange_tree=True)
    recipient.partition = ConversationPartition(
        chat_id="chat", scope="recipient-scope"
    )
    return recipient, store, token


@pytest.mark.anyio
async def test_open_shared_installs_without_persisting():
    recipient, store, token = await _shared_setup()

    assert await recipient.open_shared(token) is True

    recorder = recipient._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.id != token  # fresh id
    assert recorder.record.share_token is None
    # Nothing persisted into the recipient's partition yet:
    assert await store.list(recipient.partition) == []
    chat = cast(_FakeChat, recipient.chat)
    assert {"type": "history_shared_view", "title": "Trip", "active": True} in chat.actions


@pytest.mark.anyio
async def test_open_shared_unknown_token_returns_false():
    recipient, _, _ = await _shared_setup()
    assert await recipient.open_shared("nope123") is False
    assert recipient._exchange_recorder.record is None


@pytest.mark.anyio
async def test_first_input_forks_into_recipient_partition():
    recipient, store, token = await _shared_setup()
    await recipient.open_shared(token)
    recorder = recipient._exchange_recorder

    await recorder.accepted_input("e_fork", _stored_message("user", "and now?"))

    metas = await store.list(recipient.partition)
    assert len(metas) == 1 and metas[0].title == "Trip"
    forked = await store.get(recipient.partition, recorder.record.id)
    assert "e_fork" in forked.nodes
    chat = cast(_FakeChat, recipient.chat)
    assert {"type": "history_shared_view", "title": None, "active": False} in chat.actions
    navigates = [a for a in chat.actions if a.get("type") == "history_navigate"]
    assert navigates and navigates[-1]["url"] is None
    assert navigates[-1]["active_id"] == recorder.record.id
    # Owner's snapshot untouched:
    from shinychat._history_store import SHARED_SCOPE
    shared = ConversationPartition(chat_id="chat", scope=SHARED_SCOPE)
    assert (await store.get(shared, token)) is not None
```

Note: `_make_controller` uses `_FakeChat`; if `open_shared`'s restore path needs chat methods the fake lacks (`clear_messages`, `set_greeting`, `_restore_bookmark_message`, `_destructive_history_mutation`), extend `_FakeChat` the way existing v2 restore tests in this file already do — copy the fake used by the `test_v2_..._restore` tests.

- [ ] **Step 2: Run, verify fail** — `FILTER="open_shared or forks_into_recipient"`.

- [ ] **Step 3: Implement.**

Thread `publish_active_id` through the restore transaction. In `_restore_exchange_record_locked`, replace the two active-id lines:

```python
if publish_active_id:
    await self._set_active_id(target.id)
    recorder.mark_active_id_published(target)
else:
    # Shared-view install: identity is set (conversation_id() works,
    # accepted_input persists under it) but not published — no URL
    # rewrite / localStorage write until the recipient forks.
    self._active_id.set(target.id)
```

`_restore_initial_exchange_record(..., publish_active_id: bool = True)` forwards it. Then:

```python
async def open_shared(self, token: str) -> bool:
    """Install a share-link snapshot as an unpersisted view. False means
    the token resolves to nothing (revoked/garbage) — callers fall back
    to the normal restore chain."""
    if self.partition is None:
        raise RuntimeError("HistoryController not initialized")
    if self._exchange_recorder is None:
        return False
    snapshot = await self.store.get(self.shared_partition, token)
    if not isinstance(snapshot, ConversationRecordV2):
        return False
    target = snapshot.model_copy(deep=True)
    target.id = new_conversation_id()
    await self._restore_initial_exchange_record(target, publish_active_id=False)
    self._shared_view_pending = True
    await self.chat._send_action(
        {"type": "history_shared_view", "title": target.title, "active": True}
    )
    return True

async def _notify_shared_fork_persisted(self, record: ConversationRecordV2) -> None:
    if not self._shared_view_pending:
        return
    self._shared_view_pending = False
    # Clears ?shinychat_share= from the address bar (url=None) and records
    # the fork as current (browser mode); url-mode's on_active_id_change
    # then writes the fork's own query param.
    await self.send_navigate(None, record.id)
    await self.chat._send_action(
        {"type": "history_shared_view", "title": None, "active": False}
    )
```

Init `self._shared_view_pending = False` in `HistoryController.__init__`. In `_ExchangeRecorder._persist_record`, after the `await self._controller.store.put(partition, record)` line, add `await self._controller._notify_shared_fork_persisted(record)`.

Leaving the shared view without forking must clear the flag and banner: at the top of `new_chat()`'s mutation body and `switch_to()`'s v2 branch (and in `delete()` when the deleted id is the active one), add:

```python
if self._shared_view_pending:
    self._shared_view_pending = False
    await self.chat._send_action(
        {"type": "history_shared_view", "title": None, "active": False}
    )
```

(Extract as `async def _clear_shared_view(self) -> None` and call it from all three sites.)

Wire the init effect (`_init_history`, before the Priority-1 bookmark block; `ids.share_token` input arrives on the same flush as `url_id` — the `scope()` req already delays to that flush):

```python
raw_token = chat._session.input[ids.share_token]()
share_token = str(raw_token) if raw_token else None
if share_token and self._share_enabled:
    opened = False
    try:
        opened = await controller.open_shared(share_token)
    except Exception as e:
        await notify_error("Could not open shared conversation", e)
    if opened:
        await finish_initial(True)
        return
    from shiny import ui as shiny_ui
    with session_context(session):
        shiny_ui.notification_show(
            "This shared link is no longer available.", type="warning"
        )
    # fall through to the normal restore chain
```

(`open_shared` already ran `_restore_exchange_record_locked`, whose tail sends `send_history_update` — the "authoritative history_update before finish_initial" contract holds.)

- [ ] **Step 4: Run, verify pass**, then the full file: `make py-check-tests FILTER=test_history_controller`, and `make py-check-types`.

- [ ] **Step 5: Commit** — `git commit -am "feat(py): open shared snapshots as unpersisted views that fork on first input"`

---

### Task 7: JS protocol — types, transport, URL plumbing, history store

**Files:**
- Modify: `js/src/transport/types.ts` (`ConversationMeta` line 8, `ChatAction` union line 72, `ChatTransport` line 197)
- Modify: `js/src/transport/shiny-transport.ts` (beside `sendHistoryRename` line 140)
- Modify: `js/src/chat/currentConversation.ts`, `js/src/chat/chat-entry.ts` (~lines 182, 252–265), `js/src/chat/historyStore.ts`, `js/src/chat/state.ts` (action switch ~line 1215), `js/src/chat/ChatApp.tsx` (history action routing ~line 214)
- Test: `js/tests/chat/historyStore.test.ts`, `js/tests/transport/shiny-transport.test.ts`, `js/tests/chat/chat-entry.test.ts`

**Interfaces:**
- Produces (consumed by Task 8):
  - `ConversationMeta.shared?: boolean`
  - Actions: `{ type: "history_share_state"; conversation_id: string; url: string | null }` and `{ type: "history_shared_view"; title: string | null; active: boolean }`
  - `ChatTransport.sendHistoryShare(id: string, convId: string): void`, `sendHistoryUnshare(id: string, convId: string): void` → `setInputValue("${id}_history_share", { id: convId }, { priority: "event" })` (same for unshare)
  - `getShareTokenFromUrl(): string | null` in `currentConversation.ts` (param `shinychat_share`)
  - `HistorySnapshot.shareState: { conversationId: string; url: string | null } | null` (latest `history_share_state`, cleared by `clearShareState()`), `HistorySnapshot.sharedView: { title: string | null } | null`
  - `HistoryActions.share(id: string): void`, `HistoryActions.unshare(id: string): void`
  - `HistoryStore.applyShareState(action)`, `HistoryStore.applySharedView(action)`, `HistoryStore.clearShareState()`

- [ ] **Step 1: Failing tests.** In `js/tests/chat/historyStore.test.ts` (follow its existing action/transport-mock patterns):

```ts
it("routes share and unshare through the transport", () => {
  const { store, transport } = makeConnectedStore() // reuse file's helper
  store.actions.share("c1")
  expect(transport.sendHistoryShare).toHaveBeenCalledWith("el", "c1")
  store.actions.unshare("c1")
  expect(transport.sendHistoryUnshare).toHaveBeenCalledWith("el", "c1")
})

it("tracks share state and shared view from server actions", () => {
  const { store } = makeConnectedStore()
  store.applyShareState({
    type: "history_share_state",
    conversation_id: "c1",
    url: "?shinychat_share=tok",
  })
  expect(store.getSnapshot().shareState).toEqual({
    conversationId: "c1",
    url: "?shinychat_share=tok",
  })
  store.applySharedView({
    type: "history_shared_view",
    title: "Trip",
    active: true,
  })
  expect(store.getSnapshot().sharedView).toEqual({ title: "Trip" })
  store.applySharedView({
    type: "history_shared_view",
    title: null,
    active: false,
  })
  expect(store.getSnapshot().sharedView).toBeNull()
})

it("propagates shared flag changes through updateHistory", () => {
  const { store } = makeConnectedStore()
  const conv = { id: "c1", title: "t", created_at: "a", updated_at: "b" }
  store.updateHistory({ enabled: true, conversations: [conv], activeId: null })
  const before = store.getSnapshot().conversations
  store.updateHistory({
    enabled: true,
    conversations: [{ ...conv, shared: true }],
    activeId: null,
  })
  expect(store.getSnapshot().conversations).not.toBe(before)
  expect(store.getSnapshot().conversations[0].shared).toBe(true)
})
```

In `shiny-transport.test.ts`: `sendHistoryShare`/`sendHistoryUnshare` set the right input ids/payloads (mirror the `sendHistoryRename` test). In `chat-entry.test.ts`: with `?shinychat_share=tok` in the URL, `${elementId}_history_share_token` is sent as `"tok"` and `restorePending` treats the token like a stored conversation id (greeting held) — mirror the existing url-id tests.

- [ ] **Step 2: Run, verify fail** — `make js-test`.

- [ ] **Step 3: Implement.**

`types.ts`: add `shared?: boolean` to `ConversationMeta`; append the two action variants to `ChatAction`; add the two transport methods to `ChatTransport`.

`shiny-transport.ts` (beside `sendHistoryRename`):

```ts
sendHistoryShare(id: string, convId: string): void {
  if (!window.Shiny?.setInputValue) return
  window.Shiny.setInputValue(
    `${id}_history_share`,
    { id: convId },
    { priority: "event" },
  )
}

sendHistoryUnshare(id: string, convId: string): void {
  if (!window.Shiny?.setInputValue) return
  window.Shiny.setInputValue(
    `${id}_history_unshare`,
    { id: convId },
    { priority: "event" },
  )
}
```

`currentConversation.ts`:

```ts
const URL_SHARE_PARAM = "shinychat_share"

export function getShareTokenFromUrl(): string | null {
  try {
    return new URLSearchParams(window.location.search).get(URL_SHARE_PARAM)
  } catch {
    return null
  }
}
```

`chat-entry.ts`: include `getShareTokenFromUrl() != null` in the `restorePending` disjunction (line ~182), and in the `initializedPromise.then()` block add:

```ts
window.Shiny?.setInputValue?.(
  `${elementId}_history_share_token`,
  getShareTokenFromUrl() ?? "",
)
```

`historyStore.ts`: extend `HistorySnapshot` with `shareState`/`sharedView` (both `null` in `initialSnapshot`), extend `HistoryActions` with `share`/`unshare` (transport-guarded like `rename` — allowed while `busy` is irrelevant here, follow `rename`'s no-busy-check shape), add the three methods (`applyShareState`, `applySharedView` — active false ⇒ `sharedView: null`, `clearShareState`), carry both fields through `updateHistory`/`setBusy` publishes, extend `conversationsEqual` to compare `shared`, and extend `snapshotsEqual` with the two new fields (reference equality).

`ChatApp.tsx` / `state.ts`: route `history_share_state` → `historyStore.applyShareState(action)` and `history_shared_view` → `historyStore.applySharedView(action)` in the same place `history_update` is routed (ChatApp line ~240; add corresponding no-op/state cases in `state.ts`'s action switch if the exhaustive union check demands them).

- [ ] **Step 4: Run, verify pass** — `make js-test`. Also `make js-lint`.

- [ ] **Step 5: Commit** — `git commit -am "feat(js): share protocol plumbing (actions, transport, url token, store state)"`

---

### Task 8: JS UI — share dialog, drawer menu item, shared-view banner

**Files:**
- Create: `js/src/chat/ShareDialog.tsx`
- Modify: `js/src/chat/ChatHistoryDrawer.tsx` (item menu ~lines 208–335), `js/src/chat/ChatApp.tsx` (banner), `js/src/chat/chat.scss`
- Test: create `js/tests/chat/ShareDialog.test.tsx`; extend `js/tests/chat/ChatHistoryDrawer.test.tsx`, `js/tests/chat/ChatApp.test.tsx`

**Interfaces:**
- Consumes: Task 7's `HistoryActions.share/unshare`, `shareState`, `sharedView`, `ConversationMeta.shared`.
- Produces: `ShareDialog` component:

```ts
export interface ShareDialogProps {
  conversationId: string
  conversationTitle: string
  shared: boolean
  shareState: { conversationId: string; url: string | null } | null
  onShare: (id: string) => void
  onUnshare: (id: string) => void
  onClose: () => void
  /** Injectable for tests; defaults to window.location.hostname. */
  hostname?: string
}
```

- [ ] **Step 1: Failing tests** (`ShareDialog.test.tsx`, react-testing-library like the other component tests):

```tsx
const LOCAL_NOTE = /running on your machine.*won't work for anyone else/i

it("offers link creation for an unshared conversation", () => {
  const onShare = vi.fn()
  render(
    <ShareDialog
      conversationId="c1"
      conversationTitle="Trip"
      shared={false}
      shareState={null}
      onShare={onShare}
      onUnshare={vi.fn()}
      onClose={vi.fn()}
      hostname="example.com"
    />,
  )
  fireEvent.click(screen.getByRole("button", { name: /create link/i }))
  expect(onShare).toHaveBeenCalledWith("c1")
  expect(screen.queryByText(LOCAL_NOTE)).toBeNull()
})

it("shows the absolute link with copy, update, and stop sharing", () => {
  render(
    <ShareDialog
      conversationId="c1"
      conversationTitle="Trip"
      shared={true}
      shareState={{ conversationId: "c1", url: "?shinychat_share=tok" }}
      onShare={vi.fn()}
      onUnshare={vi.fn()}
      onClose={vi.fn()}
      hostname="example.com"
    />,
  )
  const input = screen.getByRole("textbox") as HTMLInputElement
  expect(input.value).toBe(
    `${window.location.origin}${window.location.pathname}?shinychat_share=tok`,
  )
  expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: /update snapshot/i }),
  ).toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: /stop sharing/i }),
  ).toBeInTheDocument()
})

it.each(["localhost", "127.0.0.1", "[::1]", "0.0.0.0"])(
  "shows a prominent local-app warning on %s",
  (hostname) => {
    render(
      <ShareDialog
        conversationId="c1"
        conversationTitle="Trip"
        shared={false}
        shareState={null}
        onShare={vi.fn()}
        onUnshare={vi.fn()}
        onClose={vi.fn()}
        hostname={hostname}
      />,
    )
    const note = screen.getByRole("alert")
    expect(note.textContent).toMatch(LOCAL_NOTE)
  },
)
```

Drawer test: a conversation with `shared: true` shows a "Manage share…" item-menu entry, `shared: false`/absent shows "Share…", and sharing disabled (`enabled` history but store without transport? no —) when the app was configured without sharing the server never advertises it; the menu item renders whenever history is enabled, so no extra gating test needed client-side. ChatApp test: when the store's `sharedView` is `{title: "Trip"}`, a `role="status"` banner containing "shared conversation" renders above the transcript; `null` renders none.

- [ ] **Step 2: Run, verify fail** — `make js-test`.

- [ ] **Step 3: Implement.**

`ShareDialog.tsx` — modal-ish panel following `ChatHistoryDrawer`'s dialog conventions (`role="dialog"`, Escape-to-close via the same portal/focus patterns; reuse its portal context if exported, else render inline in the drawer item like the delete-confirm flow):

- Unshared: explanatory line ("Anyone who can access this app can open the link.") + **Create link** button → `onShare(conversationId)`. When `shareState` for this conversation arrives (prop update), switch to the shared layout.
- Shared: readonly `<input>` with the absolute URL — `window.location.origin + window.location.pathname + url` — **Copy** button (`navigator.clipboard.writeText`, fall back to `input.select()` + `document.execCommand("copy")`), **Update snapshot** → `onShare(conversationId)`, **Stop sharing** → `onUnshare(conversationId)`.
- Localhost warning: computed from `hostname ?? window.location.hostname`; hosts `["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]` ⇒ render `role="alert"` box, text: **"This app is running on your machine — this link won't work for anyone else. Deploy the app to share it."** Styled as a warning callout (not fine print).

`ChatHistoryDrawer.tsx`: add a menu entry between Rename and Delete — label `c.shared ? "Manage share…" : "Share…"` — that opens the ShareDialog for that conversation (state `sharingFor: string | null` beside `confirmingDelete`), wiring `onShare={actions.share}`, `onUnshare={actions.unshare}`, `shareState={snapshot.shareState}` and clearing `shareState` on close via `store.clearShareState()`. Plumb a small "shared" badge on shared items (e.g. a link icon with `aria-label="Shared"`).

`ChatApp.tsx`: render the banner when `historySnapshot.sharedView` is non-null, above the messages list:

```tsx
{sharedView && (
  <div className="shiny-chat-shared-banner" role="status">
    You're viewing a shared conversation. Send a message to continue it as
    your own copy.
  </div>
)}
```

`chat.scss`: `.shiny-chat-shared-banner` (subtle pinned bar), `.shiny-chat-share-dialog`, `.shiny-chat-share-warning` (visually prominent: warning background, icon-friendly), following the file's existing custom-property conventions (`--shiny-chat-*` with fallbacks).

- [ ] **Step 4: Run, verify pass** — `make js-test && make js-lint`.

- [ ] **Step 5: Commit** — `git commit -am "feat(js): share dialog, drawer menu entry, shared-view banner"`

---

### Task 9: Built assets + Playwright end-to-end

**Files:**
- Create: `pkg-py/tests/playwright/chat/history_share/app.py`, `pkg-py/tests/playwright/chat/history_share/test_history_share.py`
- Generated: `make update-dist` output (js/dist, pkg-py/src/shinychat/www, pkg-r/inst/lib/shiny)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Rebuild assets** — `make update-dist`. Without this the Playwright apps serve stale JS and every new-UI assertion fails.

- [ ] **Step 2: Write the app.** Follow the structure of an existing v2 history app (e.g. `pkg-py/tests/playwright/chat/history_v2_restore/app.py`) — echo-style client, `InMemoryConversationStore()` **instance created at module level** so both browser contexts share one store while browser-token scopes keep them in separate partitions:

```python
from shiny import App, ui
from shinychat import Chat, HistoryOptions
from shinychat._history_store import InMemoryConversationStore

# One store instance for the whole process: both Playwright browser
# contexts must see the same shared partition.
STORE = InMemoryConversationStore()

app_ui = ui.page_fluid(ui.chat_ui("chat"))


def server(input, output, session):
    chat = Chat(
        "chat",
        client=EchoClient(),  # copy the echo client from history_v2_restore
        history=HistoryOptions(store=STORE, restore_mode="url"),
    )


app = App(app_ui, server)
```

(Copy the exact echo-client class the reference app uses; `restore_mode="url"` makes post-fork URL assertions easy.)

- [ ] **Step 3: Write the failing e2e test** (`test_history_share.py`), following the two-context patterns and helpers (`open_drawer`, message send/expect utilities) used by the existing history Playwright tests:

Test 1 `test_share_open_fork_revoke` — the full lifecycle:
1. Context A: send "hello" → wait for response → open drawer → item menu → **Share…** → **Create link** → read the absolute URL from the dialog's textbox.
2. Context B (fresh browser context = fresh browser token = separate scope): `page.goto(share_url)` → expect the `role="status"` banner ("shared conversation"), the transcript showing "hello", and an empty drawer (no conversations listed).
3. Context B: send "continuing" → banner disappears → drawer now lists one conversation titled like A's → URL query no longer contains `shinychat_share` (and in url mode contains `shinychat_conversation_id`).
4. Context A: drawer unchanged (still exactly its own conversation); original transcript lacks "continuing".
5. Context A: dialog → **Stop sharing**. Context C (third context): `page.goto(share_url)` → expect notification text "This shared link is no longer available." and an empty chat.

Test 2 `test_forged_share_action_rejected`:

```python
page.evaluate(
    """() => window.Shiny.setInputValue(
        "chat_history_share", {id: "c_0000000000000ffffffffff"}, {priority: "event"}
    )"""
)
expect(page.get_by_text("Could not share conversation")).to_be_visible()
```

Test 3 `test_localhost_warning_visible` — Playwright runs against localhost, so the dialog must show the local-app warning (`role="alert"` with "running on your machine").

- [ ] **Step 4: Run** — `make py-check-tests FILTER=history_share` (Playwright tests run under pytest; check how existing history e2e tests are invoked in the Makefile/pytest config and use that). Iterate until green.

- [ ] **Step 5: Commit source and assets separately:**

```bash
git add pkg-py/tests/playwright/chat/history_share
git commit -m "test(py): end-to-end share/open/fork/revoke coverage"
git add js/dist pkg-py/src/shinychat/www pkg-r/inst/lib/shiny
git commit -m "chore: update built chat assets"
```

---

### Task 10: Changelog + full verification

**Files:**
- Modify: `pkg-py/CHANGELOG.md` (unreleased section)

- [ ] **Step 1: Changelog entry** under an `## [Unreleased]` / new-features heading (create the section if absent), written for users:

```markdown
* Conversations can now be shared. Each conversation's menu offers a Share
  action that mints a revocable link; anyone who can access the app can open
  the link to view the conversation as it was when shared, and continue it
  as their own copy by sending a message (the original is never modified).
  Programmatic access via `chat.history.share()` / `chat.history.unshare()`;
  disable with `HistoryOptions(share=False)`. (#TBD-PR-NUMBER)
```

(Replace `#TBD-PR-NUMBER` with the real PR number when opening the PR — this is the one allowed deferred value.)

- [ ] **Step 2: Full verification** — run and confirm output, in order: `make js-test`, `make js-lint`, `make py-check` (format + types + all Python tests including Playwright). Fix anything red before claiming done.

- [ ] **Step 3: Commit** — `git commit -am "docs(py): changelog entry for conversation sharing"`

- [ ] **Step 4: Do NOT push or open a PR without explicit user confirmation.** Report completion, note that the branch stacks on #379, and remind that the R port and the `scope`-docs reframing PR (off `main`) are tracked separately.

---

## Out of scope for this plan

- The R implementation (follows #379's R port; the spec's behavior matrix is the contract).
- The `scope` documentation reframing (separate small PR off `main`).
- Share expiry, per-recipient ACLs, `values` opt-out (explicitly YAGNI'd in the spec).
