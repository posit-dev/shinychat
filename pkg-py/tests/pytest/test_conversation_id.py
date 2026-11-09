"""
Tests for stable conversation identity: the active conversation ID is
allocated at first submission (before model work), retained across
failure/cancellation, adopted by the first saved record, and cleared on
new-chat/delete. The ID is handed to the chatlas client before model work so
the client can annotate its own OpenTelemetry spans with
`gen_ai.conversation.id` (shinychat itself does not create spans).

Mirrors pkg-r/tests/testthat/test-conversation-id.R.
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
# Active conversation title (mirrors the R section of the same name)
# ---------------------------------------------------------------------------


class FlakyStore(InMemoryConversationStore):
    """A store whose writes can be made to fail, to exercise failure ordering."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_puts = False

    async def put(self, partition: Any, record: Any) -> None:
        if self.fail_puts:
            raise RuntimeError("store unavailable")
        await super().put(partition, record)


def ctrl_title(ctrl: HistoryController) -> str | None:
    return ctrl._title_now()


def watch_title(
    session: Session, read: Any
) -> tuple[list[str | None], Any]:
    """Record every value an observer sees, to assert on invalidation."""
    seen: list[str | None] = []
    with session_context(session):
        eff = reactive.Effect(lambda: seen.append(read()))
    return seen, eff


def test_title_is_none_for_empty_chat_and_identified_draft():
    async def main() -> None:
        ctrl = make_controller()
        assert ctrl_title(ctrl) is None

        await ctrl.ensure_conversation_id()
        assert ctrl._active_id_now() is not None
        assert ctrl_title(ctrl) is None

    run_async(main)


def test_fallback_title_appears_after_first_successful_save():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "Tell me about penguins")
        assert status == "success"

        # Unlike R, Python persists the record when the user input is
        # admitted (stream persistence), so the fallback title is already
        # public before the response settles.
        assert public_title(chat) == "Tell me about penguins"

        ctrl = chat.history._controller
        assert ctrl is not None
        recorder = ctrl._exchange_recorder
        assert recorder.record is not None
        assert public_title(chat) == recorder.record.title

        mock.set_turns(make_turns("Tell me about penguins", "Sure"))
        await ctrl.on_response()
        assert public_title(chat) == "Tell me about penguins"

    run_async(main)


def test_failed_first_save_keeps_title_none_until_a_save_succeeds():
    async def main() -> None:
        store = FlakyStore()
        chat, mock, session = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        # The first save happens when the user input is admitted; failing
        # it leaves the record activated in memory but never persisted.
        store.fail_puts = True
        await submit(session, "Hi")
        await pump_until_idle(chat, timeout=0.5)
        recorder = ctrl._exchange_recorder
        assert recorder.record is not None
        assert public_title(chat) is None

        store.fail_puts = False
        await submit(session, "Hi")
        await pump_until_idle(chat)
        assert public_title(chat) == "Hi"

    run_async(main)


def test_title_invalidates_observers_on_each_title_change():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        seen, eff = watch_title(session, chat.history.title)
        try:
            await reactive.flush()
            assert seen == [None]

            status = await submit_and_wait(chat, session, "Hi")
            assert status == "success"
            ctrl = chat.history._controller
            assert ctrl is not None
            await reactive.flush()
            assert seen == [None, "Hi"]

            record = ctrl._exchange_recorder.record
            assert record is not None
            await ctrl.rename(record.id, "Renamed")
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
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()

        seen, eff = watch_title(session, chat.history.title)
        try:
            await reactive.flush()
            assert seen == ["Hi"]

            record = ctrl._exchange_recorder.record
            assert record is not None
            await ctrl.rename(record.id, "Hi")
            await ctrl.save()
            await reactive.flush()

            assert seen == ["Hi"]
        finally:
            eff.destroy()

    run_async(main)


def test_active_rename_updates_title_inactive_rename_does_not():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "one")
        assert status == "success"
        mock.set_turns(make_turns("one", "Reply"))
        await ctrl.on_response()
        id1 = public_conversation_id(chat)
        assert id1 is not None

        await ctrl.new_chat()
        status = await submit_and_wait(chat, session, "two")
        assert status == "success"
        mock.set_turns(make_turns("two", "Reply"))
        await ctrl.on_response()
        assert public_title(chat) == "two"

        await ctrl.rename(id1, "Inactive rename")
        assert public_title(chat) == "two"

        record = ctrl._exchange_recorder.record
        assert record is not None
        await ctrl.rename(record.id, "  Active   rename ")
        assert public_title(chat) == "Active rename"

    run_async(main)


def test_failed_rename_leaves_the_previous_title_in_place():
    async def main() -> None:
        store = FlakyStore()
        chat, mock, session = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()
        assert public_title(chat) == "Hi"

        record = ctrl._exchange_recorder.record
        assert record is not None
        store.fail_puts = True
        with pytest.raises(RuntimeError, match="unavailable"):
            await ctrl.rename(record.id, "Nope")
        assert public_title(chat) == "Hi"

    run_async(main)


def test_restore_switch_new_chat_and_delete_update_the_title():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "one")
        assert status == "success"
        mock.set_turns(make_turns("one", "Reply"))
        await ctrl.on_response()
        id1 = public_conversation_id(chat)
        assert id1 is not None
        assert public_title(chat) == "one"

        await ctrl.new_chat()
        assert public_title(chat) is None

        status = await submit_and_wait(chat, session, "two")
        assert status == "success"
        mock.set_turns(make_turns("two", "Reply"))
        await ctrl.on_response()
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
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()
        record = ctrl._exchange_recorder.record
        assert record is not None
        await ctrl.rename(record.id, "Persisted")
        conv_id = record.id

        # A fresh chat restoring the saved conversation adopts its
        # persisted title.
        chat2, mock2, session2 = make_chat(
            history=HistoryOptions(store=store, title=None)
        )
        session2.input["chat_history_current_id"].set(conv_id)
        session2.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        assert public_conversation_id(chat2) == conv_id
        assert public_title(chat2) == "Persisted"

    run_async(main)


def test_clear_failed_restore_clears_the_title():
    async def main() -> None:
        ctrl = make_controller()
        ctrl._set_title("Stale")
        assert ctrl_title(ctrl) == "Stale"

        await ctrl._clear_failed_restore()
        assert ctrl_title(ctrl) is None

    run_async(main)


def test_title_disabled_still_exposes_fallback_and_never_retitles():
    async def main() -> None:
        # make_chat's default HistoryOptions(title=None) disables titling.
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None
        assert ctrl.title_enabled is False

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()
        assert public_title(chat) == "Hi"

        status = await submit_and_wait(chat, session, "More")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello") + make_turns("More", "Sure"))
        await ctrl.on_response()
        await asyncio.sleep(0.05)
        await reactive.flush()

        # The second response would trigger titling when enabled; with
        # titling disabled the fallback stays.
        assert public_title(chat) == "Hi"

    run_async(main)


def test_automatic_retitle_updates_title_once_it_is_persisted():
    async def main() -> None:
        async def title(turns: list[dict[str, Any]]) -> str:
            return "Generated"

        chat, mock, session = make_chat(
            history=HistoryOptions(store="memory", title=title)
        )
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()
        assert public_title(chat) == "Hi"

        status = await submit_and_wait(chat, session, "More")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello") + make_turns("More", "Sure"))
        await ctrl.on_response()

        task = ctrl._title_task
        assert task is not None
        await task

        recorder = ctrl._exchange_recorder
        assert recorder.record is not None
        assert public_title(chat) == "Generated"
        assert recorder.record.title == "Generated"

    run_async(main)


def test_user_rename_wins_over_an_inflight_retitle():
    async def main() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def title(turns: list[dict[str, Any]]) -> str:
            entered.set()
            await release.wait()
            return "Generated"

        chat, mock, session = make_chat(
            history=HistoryOptions(store="memory", title=title)
        )
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()

        status = await submit_and_wait(chat, session, "More")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello") + make_turns("More", "Sure"))
        await ctrl.on_response()

        await asyncio.wait_for(entered.wait(), 1)
        record = ctrl._exchange_recorder.record
        assert record is not None
        await ctrl.rename(record.id, "Mine")

        release.set()
        task = ctrl._title_task
        assert task is not None
        await task

        assert public_title(chat) == "Mine"
        assert record.title == "Mine"

    run_async(main)


def test_failed_retitle_persistence_leaves_title_unchanged():
    async def main() -> None:
        store = FlakyStore()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def title(turns: list[dict[str, Any]]) -> str:
            entered.set()
            await release.wait()
            return "Generated"

        chat, mock, session = make_chat(
            history=HistoryOptions(store=store, title=title)
        )
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        ctrl = chat.history._controller
        assert ctrl is not None

        status = await submit_and_wait(chat, session, "Hi")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello"))
        await ctrl.on_response()
        assert public_title(chat) == "Hi"

        status = await submit_and_wait(chat, session, "More")
        assert status == "success"
        mock.set_turns(make_turns("Hi", "Hello") + make_turns("More", "Sure"))
        await ctrl.on_response()

        await asyncio.wait_for(entered.wait(), 1)
        store.fail_puts = True
        release.set()
        task = ctrl._title_task
        assert task is not None
        while not task.done():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0)  # let the done callback surface the failure

        assert public_title(chat) == "Hi"

    run_async(main)


def test_history_title_follows_the_submission_and_response_lifecycle():
    async def main() -> None:
        chat, mock, session = make_chat()

        titles_seen: list[str | None] = []

        def on_stream() -> None:
            # Mid-call the conversation is an identified, unsaved draft.
            titles_seen.append(public_title(chat))

        mock.on_stream = on_stream

        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        assert public_title(chat) is None

        status = await submit_and_wait(chat, session, "hi there")
        assert status == "success"

        assert len(titles_seen) == 1
        # Unlike R, the record is already persisted when the model call
        # starts (input admission persists it), so the fallback title is
        # public mid-call.
        assert titles_seen[0] == "hi there"

        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("hi there", "response"))
        await ctrl.on_response()

        recorder = ctrl._exchange_recorder
        assert recorder.record is not None
        assert public_title(chat) == recorder.record.title

        await ctrl.rename(recorder.record.id, "Renamed")
        assert public_title(chat) == "Renamed"

        await ctrl.new_chat()
        assert public_title(chat) is None

    run_async(main)


def test_history_disabled_title_stays_none():
    async def main() -> None:
        chat, mock, session = make_chat(history=False)
        assert chat.history._controller is None

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"
        assert public_title(chat) is None

    run_async(main)


def test_client_set_preserves_the_title():
    async def main() -> None:
        chat, mock, session = make_chat()
        session.input["chat_history_browser_token"] = reactive.Value("tok")
        await reactive.flush()

        status = await submit_and_wait(chat, session, "hi")
        assert status == "success"
        ctrl = chat.history._controller
        assert ctrl is not None
        mock.set_turns(make_turns("hi", "response"))
        await ctrl.on_response()
        record = ctrl._exchange_recorder.record
        assert record is not None
        await ctrl.rename(record.id, "Kept title")

        # Unlike R, a client swap doesn't re-register history in Python (the
        # controller — and its published title — simply survives).
        assert chat.client is not None
        with reactive.isolate():
            chat.client.set(cast(Any, StreamClient()))
        await reactive.flush()

        assert public_title(chat) == "Kept title"

    run_async(main)
