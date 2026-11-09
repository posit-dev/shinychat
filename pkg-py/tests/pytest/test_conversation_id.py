"""
Tests for stable conversation identity: the active conversation ID is
allocated at first submission (before model work), retained across
failure/cancellation, adopted by the first saved record, and cleared on
new-chat/delete. The ID is handed to the chatlas client before model work so
the client can annotate its own OpenTelemetry spans with
`gen_ai.conversation.id` (shinychat itself does not create spans).

Mirrors pkg-r/tests/testthat/test-conversation-id.R, including its
"Active conversation title" section (see the title section below).
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from _session_api_contract import FakeSessionReactiveApi
from shiny import Inputs, Session, reactive
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat._history import HistoryOptions
from shinychat._history_client import TurnsAdapter
from shinychat._history_controller import HistoryController
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)
from shinychat._history_types import (
    ConversationRecordV1,
    ConversationRecordV2,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def run_async(coro_fn: Any) -> None:
    """Run an async function in a separate thread to avoid event loop conflicts."""
    exc: list[BaseException] = []

    def _run() -> None:
        try:
            asyncio.run(coro_fn())
        except BaseException as err:
            exc.append(err)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exc:
        raise exc[0]


@pytest.fixture(scope="module", autouse=True)
def _drain_foreign_effects() -> None:
    """Flush out effects left pending by other test modules.

    The reactive environment is process-global, and earlier test modules
    create Chat effects that never flush (their mock sessions lack
    `_decrement_busy_count`, so their post-run callback raises
    AttributeError). Drain them here — one erroring effect per flush — so
    this module's flushes only run its own effects.
    """

    async def drain() -> None:
        for _ in range(500):
            try:
                await reactive.flush()
            except Exception:
                continue
            break

    run_async(drain)


def make_turns(
    user_text: str = "Hi", asst_text: str = "Hello"
) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "contents": [{"content_type": "text", "text": user_text}],
        },
        {
            "role": "assistant",
            "contents": [{"content_type": "text", "text": asst_text}],
        },
    ]


class MockClient:
    """Minimal non-chatlas client: turns are plain JSON dicts."""

    def __init__(self) -> None:
        self._turns: list[Any] = []
        self.system_prompt: str | None = None
        self._tools: list[Any] = []
        self.conversation_id: str | None = None

    def get_turns(self) -> list[Any]:
        return list(self._turns)

    def set_turns(self, turns: list[Any]) -> None:
        self._turns = list(turns)

    def get_tools(self) -> list[Any]:
        return list(self._tools)

    def set_tools(self, tools: list[Any]) -> None:
        self._tools = list(tools)


class StubChat:
    """Minimal stand-in for Chat for HistoryController unit tests."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self._session: Any = None

    def _messages_for_bookmark(self) -> list[dict[str, Any]]:
        return self.messages

    @asynccontextmanager
    async def _destructive_history_mutation(self, *, block_input: bool = False):
        yield

    async def _clear_messages_screen_only(
        self, *, greeting: bool = False
    ) -> None:
        self.messages.clear()

    async def set_greeting(self, greeting: Any, **kwargs: Any) -> None:
        pass

    async def _restore_bookmark_message(self, message_dict: Any) -> None:
        # Emulate the client echoing restored messages back.
        self.messages.append(message_dict)

    async def _send_action(self, action: Any, html_deps: Any = None) -> None:
        self.actions.append(action)


def make_controller(
    *,
    store: InMemoryConversationStore | None = None,
    client: MockClient | None = None,
    chat: StubChat | None = None,
) -> HistoryController:
    client = client or MockClient()
    ctrl = HistoryController(
        chat=cast(Any, chat or StubChat()),
        adapter=TurnsAdapter(client),
        store=store or InMemoryConversationStore(),
        title_fn=None,
        title_enabled=False,
        client=client,
    )
    ctrl.partition = ConversationPartition(chat_id="chat", scope="test-user")
    return ctrl


def active_id(ctrl: HistoryController) -> str | None:
    return ctrl._active_id_now()


# ---------------------------------------------------------------------------
# Controller lifecycle
# ---------------------------------------------------------------------------


def test_new_controller_has_no_conversation_id():
    ctrl = make_controller()
    assert active_id(ctrl) is None
    assert ctrl._exchange_recorder.record is None


def test_ensure_conversation_id_allocates_once_and_is_stable():
    async def main() -> None:
        store = InMemoryConversationStore()
        ctrl = make_controller(store=store)
        id = await ctrl.ensure_conversation_id()
        assert id.startswith("c_")
        assert await ctrl.ensure_conversation_id() == id
        assert active_id(ctrl) == id

        # An identified draft has no record and leaks nothing into the
        # store, even when no save ever happens (model call failed or was
        # cancelled).
        assert ctrl._exchange_recorder.record is None
        assert ctrl.partition is not None
        assert await ctrl.store.get(ctrl.partition, id) is None
        assert await store.list(ctrl.partition) == []

    run_async(main)


def test_new_chat_announces_cleared_id_even_from_empty_draft():
    async def main() -> None:
        ctrl = make_controller()
        calls: list[str | None] = []

        async def on_change(id: str | None) -> None:
            calls.append(id)

        ctrl.on_active_id_change = on_change

        await ctrl.new_chat()

        # URL restore mode relies on this to clear a stale conversation
        # param in the address bar even when the active ID was already
        # None (e.g. after a failed restore).
        assert calls == [None]

    run_async(main)


# ---------------------------------------------------------------------------
# Chat integration (mock session, reactive effects driven by reactive.flush)
# ---------------------------------------------------------------------------


class _MockBookmark:
    def __init__(self) -> None:
        self.exclude: list[Any] = []
        self.store = "disable"
        self._restore_context = None


class _MockApp:
    sanitize_errors = True
    sanitize_otel_errors = True


class _MockSession(FakeSessionReactiveApi):
    """Enough of a Session for Chat + history to run outside an app."""

    ns: ResolvedId = ResolvedId("")
    app: object = _MockApp()
    id: str = "mock-session"

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)
        self.bookmark = _MockBookmark()
        self.sent: list[dict[str, Any]] = []

    def is_stub_session(self) -> bool:
        return False

    def root_scope(self) -> Any:
        return self

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _decrement_busy_count(self) -> None:
        pass

    def _process_ui(self, x: Any) -> dict[str, Any]:
        return {"html": str(x), "deps": []}

    def _send_message_sync(self, msg: Any) -> None:
        pass

    async def _unhandled_error(self, e: Any) -> None:
        pass

    async def send_custom_message(self, type: str, message: Any) -> None:
        self.sent.append({"type": type, "message": message})


class StreamClient(MockClient):
    """MockClient with a chatlas-like stream_async returning an async generator."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0
        # Test hooks: on_stream fires when stream_async is called, on_consume
        # when the returned generator is consumed (where chatlas does its
        # provider I/O — and creates its spans).
        self.on_stream: Any = None
        self.on_consume: Any = None
        self.fail_first_attempt = False

    async def stream_async(self, *args: Any, **kwargs: Any) -> Any:
        self.attempts += 1
        if self.on_stream is not None:
            self.on_stream()
        attempt = self.attempts
        fail = self.fail_first_attempt and attempt == 1

        async def gen():
            if fail:
                raise RuntimeError("boom")
            if self.on_consume is not None:
                self.on_consume()
            yield "response"

        return gen()


def make_chat(
    client: StreamClient | None = None,
    *,
    history: Any = None,
    session: Session | None = None,
) -> tuple[Chat, StreamClient, Session]:
    mock = client or StreamClient()
    sess = session or cast(Session, _MockSession())
    # Pre-seed a settable (unset) user-input Value: once an effect reads the
    # input, Inputs auto-populates a read-only Value that can no longer be
    # set() to simulate later submissions.
    sess.input["chat_user_input"] = reactive.Value()
    # The browser-mode initial history effect suspends on a missing
    # current_id input (the real client always sends it with the browser
    # token); without it the initial decision never completes and every
    # history action stays unadmitted.
    sess.input["chat_history_current_id"] = reactive.Value(None)
    if history is None:
        history = HistoryOptions(store="memory", title=None)
    with session_context(sess):
        chat = Chat("chat", client=cast(Any, mock), history=history)
    return chat, mock, sess


async def submit(session: Session, text: str) -> None:
    """Simulate a user submission and let the reactive effects run."""
    session.input["chat_user_input"].set({"text": text, "attachments": []})
    await reactive.flush()


async def pump_until_idle(chat: Chat, timeout: float = 5.0) -> str:
    """Pump the event loop until the stream task settles."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    status = "initial"
    while loop.time() < deadline:
        await reactive.flush()
        await asyncio.sleep(0.01)
        with reactive.isolate():
            status = chat.latest_message_stream.status()
        if status in ("success", "error"):
            break
    # Let any follow-on effects (e.g. error handling) run.
    await reactive.flush()
    await asyncio.sleep(0)
    await reactive.flush()
    return status


async def submit_and_wait(chat: Chat, session: Session, text: str) -> str:
    await submit(session, text)
    return await pump_until_idle(chat)


def public_conversation_id(chat: Chat) -> str | None:
    with reactive.isolate():
        return chat.history.conversation_id()


def public_title(chat: Chat) -> str | None:
    with reactive.isolate():
        return chat.history.title()


def test_conversation_id_is_none_initially_and_allocated_before_model_call():
    async def main() -> None:
        chat, mock, session = make_chat()
        assert chat.history._controller is not None

        ids_seen: list[str | None] = []
        bindings_seen: list[str | None] = []

        def on_stream() -> None:
            # The managed model call must already observe a non-None ID,
            # both via the public reactive and via its own
            # `conversation_id` property.
            ids_seen.append(public_conversation_id(chat))
            bindings_seen.append(mock.conversation_id)

        mock.on_stream = on_stream

        # scope() requires the browser token before history initializes
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        assert public_conversation_id(chat) is None
        assert mock.conversation_id is None

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"

        assert len(ids_seen) == 1
        assert ids_seen[0] is not None
        assert public_conversation_id(chat) == ids_seen[0]
        assert bindings_seen == ids_seen
        assert mock.conversation_id == ids_seen[0]

    run_async(main)


def test_client_without_conversation_id_binding_is_left_alone():
    async def main() -> None:
        chat, mock, session = make_chat()
        # Older chatlas / non-chatlas clients have no `conversation_id`.
        del mock.conversation_id
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"

        assert not hasattr(mock, "conversation_id")
        assert public_conversation_id(chat) is not None

    run_async(main)


def test_public_id_matches_the_stored_record():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"

        ctrl = chat.history._controller
        assert ctrl is not None
        # The client doesn't report messages back in this harness, so drive
        # the save trigger directly.
        mock.set_turns(make_turns())
        await ctrl.on_response()

        recorder = ctrl._exchange_recorder
        assert recorder.record is not None
        assert public_conversation_id(chat) == recorder.record.id
        stored_partition = ctrl.partition
        assert stored_partition is not None
        stored = await ctrl.store.get(stored_partition, recorder.record.id)
        assert stored is not None and stored.id == public_conversation_id(chat)

    run_async(main)


def test_failed_and_retried_calls_report_the_same_id():
    async def main() -> None:
        mock = StreamClient()
        mock.fail_first_attempt = True
        chat, _, session = make_chat(mock)

        ids_seen: list[str | None] = []
        mock.on_stream = lambda: ids_seen.append(public_conversation_id(chat))

        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "hi")
        assert status == "error"

        status = await submit_and_wait(chat, session, "retry")
        assert status == "success"

        assert mock.attempts == 2
        assert len(ids_seen) == 2
        assert ids_seen[0] is not None
        assert ids_seen[0] == ids_seen[1]

    run_async(main)


def test_new_chat_and_switch_update_the_public_id():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "one")
        assert status == "success"
        mock.set_turns(make_turns("one", "reply one"))
        await ctrl.on_response()
        id1 = public_conversation_id(chat)
        assert id1 is not None

        await ctrl.new_chat()
        assert public_conversation_id(chat) is None

        status = await submit_and_wait(chat, session, "two")
        assert status == "success"
        mock.set_turns(make_turns("two", "reply two"))
        await ctrl.on_response()
        id2 = public_conversation_id(chat)
        assert id2 is not None and id2 != id1

        await ctrl.switch_to(id1)
        assert public_conversation_id(chat) == id1

    run_async(main)


def test_client_set_preserves_the_conversation_id():
    async def main() -> None:
        chat, _, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"
        id = public_conversation_id(chat)
        assert id is not None

        # Unlike R, a client swap doesn't re-register history in Python (the
        # turns adapter unwraps the live client), so the controller — and its
        # active ID — simply survives.
        assert chat.client is not None
        with reactive.isolate():
            chat.client.set(cast(Any, StreamClient()))
        await reactive.flush()

        assert public_conversation_id(chat) == id
        ctrl = chat.history._controller
        assert ctrl is not None
        assert await ctrl.ensure_conversation_id() == id

    run_async(main)


def test_history_disabled_stays_none():
    async def main() -> None:
        chat, mock, session = make_chat(history=False)
        assert chat.history._controller is None

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"
        assert public_conversation_id(chat) is None
        assert mock.conversation_id is None

    run_async(main)


# ---------------------------------------------------------------------------
# Active conversation title. Ported from the R conversation-title tests
# (shinychat#4hq3). One deliberate divergence: Python persists the record
# when the user's message is admitted, so the fallback title is published
# before the response finishes; R publishes it after the response is saved.
# ---------------------------------------------------------------------------


class FlakyStore(InMemoryConversationStore):
    """A store whose writes can be made to fail, to exercise failure ordering."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_puts = False
        self.failed_puts = 0

    async def put(
        self,
        partition: ConversationPartition,
        record: ConversationRecordV1 | ConversationRecordV2,
    ) -> None:
        if self.fail_puts:
            self.failed_puts += 1
            raise RuntimeError("store unavailable")
        await super().put(partition, record)


def active_title(ctrl: HistoryController) -> str | None:
    return ctrl._title_now()


def active_record(ctrl: HistoryController) -> ConversationRecordV2:
    recorder = ctrl._exchange_recorder
    assert recorder.record is not None
    return recorder.record


def open_history(session: Session) -> None:
    """Complete the browser-mode initial history decision (empty restore)."""
    session.input["chat_history_browser_token"] = reactive.Value("tok")
    # Flush is awaited by the caller.


def watch_value(session: Session, read: Any) -> tuple[list[Any], Any]:
    """Record every value an observer sees, to assert on invalidation.

    The read callable must NOT wrap its read in ``reactive.isolate()``:
    isolation suppresses dependency tracking, so the effect would never
    re-run.
    """
    seen: list[Any] = []
    with session_context(session):
        eff = reactive.Effect(lambda: seen.append(read()))
    return seen, eff


def blocking_title_fn() -> tuple[Any, asyncio.Event, asyncio.Event]:
    """A title_fn that blocks on an event; returns (fn, entered, release)."""
    entered = asyncio.Event()
    release = asyncio.Event()

    async def title(turns: list[dict[str, Any]]) -> str:
        entered.set()
        await release.wait()
        return "Generated"

    return title, entered, release


async def complete_exchange(
    chat: Chat,
    mock: StreamClient,
    session: Session,
    user: str,
    reply: str = "Reply",
) -> HistoryController:
    """Submit, wait for the stream, then settle the response save."""
    status = await submit_and_wait(chat, session, user)
    assert status == "success"
    ctrl = chat.history._controller
    assert ctrl is not None
    mock.set_turns(make_turns(user, reply))
    await ctrl.on_response()
    return ctrl


def test_title_is_none_for_empty_chat_and_identified_draft():
    async def main() -> None:
        ctrl = make_controller()
        assert active_title(ctrl) is None

        await ctrl.ensure_conversation_id()
        assert active_id(ctrl) is not None
        assert active_title(ctrl) is None

    run_async(main)


def test_fallback_title_appears_after_first_successful_save():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(
            chat, mock, session, "Tell me about penguins"
        )
        assert public_title(chat) == "Tell me about penguins"
        assert public_title(chat) == active_record(ctrl).title

    run_async(main)


def test_failed_first_save_keeps_title_none_until_a_save_succeeds():
    async def main() -> None:
        store = FlakyStore()
        chat, _, session = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        open_history(session)
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        # The first save happens when the user input is admitted; failing
        # it leaves the record activated in memory but never persisted.
        store.fail_puts = True
        await submit(session, "Hi")
        await pump_until_idle(chat, timeout=0.5)
        assert ctrl._exchange_recorder.record is not None
        assert public_title(chat) is None

        store.fail_puts = False
        await submit(session, "Hi")
        await pump_until_idle(chat)
        assert public_title(chat) == "Hi"

    run_async(main)


def test_title_invalidates_observers_on_each_title_change():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        seen, eff = watch_value(session, chat.history.title)
        try:
            await reactive.flush()
            assert seen == [None]

            ctrl = await complete_exchange(chat, mock, session, "Hi")
            await reactive.flush()
            assert seen == [None, "Hi"]

            await ctrl.rename(active_record(ctrl).id, "Renamed")
            await reactive.flush()

            await ctrl.new_chat()
            await reactive.flush()

            assert seen == [None, "Hi", "Renamed", None]
        finally:
            eff.destroy()

    run_async(main)


def test_rewriting_unchanged_title_does_not_invalidate_observers():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "Hi")
        assert public_title(chat) == "Hi"

        seen, eff = watch_value(session, chat.history.title)
        try:
            await reactive.flush()
            assert seen == ["Hi"]

            await ctrl.rename(active_record(ctrl).id, "Hi")
            await ctrl.save()
            await reactive.flush()

            assert seen == ["Hi"]
        finally:
            eff.destroy()

    run_async(main)


def test_active_rename_updates_title_inactive_rename_does_not():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "one")
        id1 = public_conversation_id(chat)
        assert id1 is not None

        await ctrl.new_chat()
        await complete_exchange(chat, mock, session, "two")
        assert public_title(chat) == "two"

        await ctrl.rename(id1, "Inactive rename")
        assert public_title(chat) == "two"

        await ctrl.rename(active_record(ctrl).id, "  Active   rename ")
        assert public_title(chat) == "Active rename"

    run_async(main)


def test_failed_rename_leaves_the_previous_title_in_place():
    async def main() -> None:
        store = FlakyStore()
        chat, mock, session = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "Hi")
        assert public_title(chat) == "Hi"

        record = active_record(ctrl)
        store.fail_puts = True
        with pytest.raises(RuntimeError, match="unavailable"):
            await ctrl.rename(record.id, "Nope")
        # The public title is unchanged, but the in-memory record carries
        # the failed rename until the next successful save publishes it.
        assert record.title == "Nope"
        assert public_title(chat) == "Hi"

    run_async(main)


def test_restore_switch_new_chat_and_delete_update_the_title():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "one")
        id1 = public_conversation_id(chat)
        assert id1 is not None
        assert public_title(chat) == "one"

        await ctrl.new_chat()
        assert public_title(chat) is None

        await complete_exchange(chat, mock, session, "two")
        id2 = public_conversation_id(chat)
        assert id2 is not None
        assert public_title(chat) == "two"

        await ctrl.switch_to(id1)
        assert public_title(chat) == "one"
        await ctrl.switch_to(id2)
        assert public_title(chat) == "two"

        await ctrl.delete(id1)  # inactive: unchanged
        assert public_title(chat) == "two"
        await ctrl.delete(id2)
        assert public_title(chat) is None

    run_async(main)


def test_initial_restore_adopts_the_persisted_title():
    async def main() -> None:
        store = InMemoryConversationStore()

        chat, mock, session = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "Hi")
        record = active_record(ctrl)
        await ctrl.rename(record.id, "Persisted")
        conv_id = record.id

        # A fresh chat restoring the saved conversation adopts its
        # persisted title.
        chat2, _, session2 = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        session2.input["chat_history_current_id"].set(conv_id)
        open_history(session2)
        await reactive.flush()

        assert public_conversation_id(chat2) == conv_id
        assert public_title(chat2) == "Persisted"

    run_async(main)


def test_switch_publishes_the_title_before_the_active_id_callback():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "one")
        id1 = public_conversation_id(chat)
        assert id1 is not None
        await ctrl.new_chat()
        await complete_exchange(chat, mock, session, "two")
        id2 = public_conversation_id(chat)
        assert id2 is not None

        # The switch publishes the target title before the awaited
        # active-id callback runs, so a flush (or the callback itself)
        # never observes the new id paired with the previous
        # conversation's title.
        seen: list[tuple[str | None, str | None]] = []

        async def on_change(id: str | None) -> None:
            seen.append((id, ctrl._title_now()))

        ctrl.on_active_id_change = on_change
        await ctrl.switch_to(id1)
        assert seen[-1] == (id1, "one")

    run_async(main)


def test_failed_restore_cleanup_clears_the_title():
    # Focused unit test of the cleanup path; the surrounding failed-restore
    # flow is covered by the history controller tests.
    async def main() -> None:
        ctrl = make_controller()
        ctrl._set_title("Stale")
        assert active_title(ctrl) == "Stale"

        await ctrl._clear_failed_restore()
        assert active_title(ctrl) is None

    run_async(main)


def test_title_disabled_still_exposes_fallback_and_never_retitles():
    async def main() -> None:
        # make_chat's default HistoryOptions(title=None) disables titling.
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None
        assert ctrl.title_enabled is False

        await complete_exchange(chat, mock, session, "Hi")
        assert public_title(chat) == "Hi"

        await complete_exchange(chat, mock, session, "More")
        # The second response would trigger titling when enabled; with
        # titling disabled no title task is created and the fallback stays.
        assert ctrl._title_task is None
        assert public_title(chat) == "Hi"

    run_async(main)


async def two_exchange_chat(
    title_fn: Any,
    store: InMemoryConversationStore | None = None,
) -> tuple[Chat, StreamClient, Session, HistoryController]:
    """A chat with titling enabled and two settled exchanges."""
    chat, mock, session = make_chat(
        history=HistoryOptions(
            store=store or InMemoryConversationStore(), title=title_fn
        )
    )
    open_history(session)
    await reactive.flush()

    await complete_exchange(chat, mock, session, "Hi")
    await complete_exchange(chat, mock, session, "More")
    ctrl = chat.history._controller
    assert ctrl is not None
    return chat, mock, session, ctrl


def test_automatic_retitle_updates_title_once_it_is_persisted():
    async def main() -> None:
        title_fn, _, release = blocking_title_fn()
        _, _, _, ctrl = await two_exchange_chat(title_fn)

        # The retitle is still in flight, so the fallback is still public.
        assert active_title(ctrl) == "Hi"

        release.set()
        task = ctrl._title_task
        assert task is not None
        await task

        assert active_record(ctrl).title == "Generated"
        assert active_title(ctrl) == "Generated"

    run_async(main)


def test_user_rename_wins_over_an_inflight_retitle():
    async def main() -> None:
        title_fn, entered, release = blocking_title_fn()
        _, _, _, ctrl = await two_exchange_chat(title_fn)

        await asyncio.wait_for(entered.wait(), 1)
        await ctrl.rename(active_record(ctrl).id, "Mine")

        release.set()
        task = ctrl._title_task
        assert task is not None
        await task

        assert active_record(ctrl).title == "Mine"
        assert active_title(ctrl) == "Mine"

    run_async(main)


def test_failed_retitle_persistence_leaves_title_unchanged():
    async def main() -> None:
        store = FlakyStore()
        title_fn, entered, release = blocking_title_fn()
        _, _, _, ctrl = await two_exchange_chat(title_fn, store=store)
        assert active_title(ctrl) == "Hi"

        await asyncio.wait_for(entered.wait(), 1)
        store.fail_puts = True
        release.set()
        task = ctrl._title_task
        assert task is not None
        # The retitle persists through the recorder's normal path, so the
        # failed store write surfaces as the task's exception. The chat
        # harness settles each exchange twice, so more than one retitle
        # task may be scheduled; count at least one failed put.
        (error,) = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(error, RuntimeError)
        assert store.failed_puts >= 1

        assert active_title(ctrl) == "Hi"

    run_async(main)


def test_history_title_follows_the_submission_and_response_lifecycle():
    async def main() -> None:
        chat, mock, session = make_chat()

        titles_seen: list[str | None] = []

        def on_stream() -> None:
            titles_seen.append(public_title(chat))

        mock.on_stream = on_stream

        open_history(session)
        await reactive.flush()

        assert public_title(chat) is None

        status = await submit_and_wait(chat, session, "hi there")
        assert status == "success"

        assert len(titles_seen) == 1
        assert titles_seen[0] == "hi there"

        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("hi there", "response"))
        await ctrl.on_response()
        assert public_title(chat) == active_record(ctrl).title

    run_async(main)


def test_history_disabled_title_stays_none():
    async def main() -> None:
        chat, _, session = make_chat(history=False)
        assert chat.history._controller is None

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"
        assert public_title(chat) is None

    run_async(main)


def test_client_set_preserves_the_title():
    async def main() -> None:
        chat, mock, session = make_chat()
        open_history(session)
        await reactive.flush()

        ctrl = await complete_exchange(chat, mock, session, "hi")
        await ctrl.rename(active_record(ctrl).id, "Kept title")

        # Unlike R, a client swap doesn't re-register history in Python (the
        # controller — and its published title — simply survives).
        assert chat.client is not None
        with reactive.isolate():
            chat.client.set(cast(Any, StreamClient()))
        await reactive.flush()

        assert public_title(chat) == "Kept title"

    run_async(main)
