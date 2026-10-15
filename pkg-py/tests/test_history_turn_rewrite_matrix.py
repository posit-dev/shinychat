# Cross-language turn-rewrite matrix for the v2 exchange-tree history
# engine (#421).
#
# The scenario is defined once in tests/shared/history-turn-rewrite-matrix.json
# and consumed here plus the Phase 6 R port (via the vendored copy at
# pkg-r/tests/testthat/fixtures/, kept in sync by `make r-sync-fixtures`).
#
# #421: when the client rewrites its own turn list between exchanges
# (`set_turns()` shortening the conversation, e.g. context compaction), v1
# history kept appending to one mutable turn log, so a later conversation
# switch restored the stale pre-rewrite turns and skipped the post-rewrite
# response. The v2 engine re-captures turns per exchange: a non-prefix
# rewrite forces a fresh snapshot at the next capture, so switching away
# and back restores the rewritten turns plus the post-rewrite response.
#
# Each case is a multi-step script of plain operations (the #421 flow is
# inherently ordered, which is why it gets its own matrix instead of living
# in the single-operation history-behavior-matrix.json). Ops:
#
# - `input`: the user submits `content`; `turns` is the client's full turn
#   list at that moment (the client appended the user turn on submit).
# - `response`: the assistant streams `content` and the stream settles;
#   `turns` is the client's full turn list afterwards.
# - `client_set_turns`: the client rewrites its own turn list in place
#   (compaction) without any exchange in flight.
# - `new_chat`: switch away to a fresh conversation.
# - `switch_to`: switch back to `$conversation`, the id opened by the
#   first `input`.
#
# `expect.turns` is the turn list the attached client must hold after the
# final step (the restored conversation's folded turns — v1 restored the
# stale pre-rewrite log instead), `expect.display` is the restored
# conversation's rendered messages (v1 skipped the post-rewrite response),
# and `expect.response_count` pins the settled-response count.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._history_store import FileConversationStore
from shinychat._history_types import ConversationRecordV2
from test_history_controller import (
    _FakeAdapter,
    _FakeChat,
    _make_controller,
    _sent,
    _stored_message,
)

MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "shared"
    / "history-turn-rewrite-matrix.json"
)
MATRIX: list[dict[str, Any]] = json.loads(
    MATRIX_PATH.read_text(encoding="utf-8")
)

_KNOWN_OPS = ("input", "response", "client_set_turns", "new_chat", "switch_to")
_REQUIRED_EXPECT = ("turns", "display", "response_count")


def test_matrix_covers_the_421_scenario() -> None:
    """The matrix holds exactly the #421 case, fully described."""
    assert {case["name"] for case in MATRIX} == {
        "set_turns_compaction_survives_switch_round_trip"
    }
    for case in MATRIX:
        assert case["steps"], f"{case['name']}: scenario has no steps"
        for index, step in enumerate(case["steps"]):
            assert step["op"] in _KNOWN_OPS, (
                f"{case['name']}/step {index}: unknown op {step.get('op')!r}"
            )
            if step["op"] in ("input", "response"):
                assert "content" in step, (
                    f"{case['name']}/step {index}: {step['op']} needs content"
                )
            if step["op"] in ("input", "response", "client_set_turns"):
                assert step.get("turns"), (
                    f"{case['name']}/step {index}: {step['op']} needs turns"
                )
        assert set(case["expect"]) == set(_REQUIRED_EXPECT), (
            f"{case['name']}: expected exactly {sorted(_REQUIRED_EXPECT)}"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("case", MATRIX, ids=lambda case: cast(str, case["name"]))
async def test_turn_rewrite_scenario(
    case: dict[str, Any], tmp_path: Path
) -> None:
    """Run one matrix case through the production v2 code paths.

    The controller runs with the real exchange recorder and the real
    FileConversationStore (record puts/gets go through on-disk files), and
    the client is driven only through the adapter seam and the transcript's
    production capture callbacks -- no test-side bypasses of capture or
    restore.
    """
    adapter = _FakeAdapter()
    adapter.turns = []  # fresh client context, like a real first exchange
    store = FileConversationStore(tmp_path)
    controller, _ = _make_controller(store=store, adapter=adapter)
    recorder = controller._exchange_recorder
    transcript = ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_finished=recorder.stream_finished,
    )

    conversation_id: str | None = None
    open_exchange_id: str | None = None

    for index, step in enumerate(case["steps"]):
        op = step["op"]
        assert op in _KNOWN_OPS, (
            f"{case['name']}/step {index}: unknown op {op!r}"
        )
        if op == "input":
            # The client owns its turn list: it holds the user turn once
            # the input is submitted, before the server accepts it.
            adapter.set_turns_json(step["turns"])
            open_exchange_id = await transcript.record_accepted_input_and_notify(
                _stored_message("user", step["content"])
            )
            if conversation_id is None:
                record = recorder.record
                assert record is not None, (
                    f"{case['name']}/step {index}: the first input must "
                    "open a conversation"
                )
                conversation_id = record.id
        elif op == "response":
            adapter.set_turns_json(step["turns"])
            assert open_exchange_id is not None, (
                f"{case['name']}/step {index}: response without an open "
                "input exchange"
            )
            stream_id = f"turn-rewrite-stream-{index}"
            await transcript.start_stream(
                stream_id=stream_id,
                entry=TranscriptEntry(
                    message=_stored_message("assistant", step["content"])
                ),
                owner_task=None,
                exchange_id=open_exchange_id,
                send=_sent,
            )
            await transcript.end_stream(
                stream_id=stream_id, status=None, error=None, send=_sent
            )
            # Production settles history through this callback once a
            # response finishes; drive the same entry point.
            await controller.on_response()
        elif op == "client_set_turns":
            adapter.set_turns_json(step["turns"])
        elif op == "new_chat":
            await controller.new_chat()
        elif op == "switch_to":
            assert step["id"] == "$conversation", (
                f"{case['name']}/step {index}: unknown id placeholder "
                f"{step.get('id')!r}"
            )
            assert conversation_id is not None, (
                f"{case['name']}/step {index}: no conversation to switch to"
            )
            await controller.switch_to(conversation_id)

    expected = case["expect"]

    restored = recorder.record
    assert isinstance(restored, ConversationRecordV2), (
        f"{case['name']}: switching back must leave the restored record "
        "installed as the active v2 conversation"
    )
    assert restored.id == conversation_id
    assert restored.response_count == expected["response_count"], (
        f"{case['name']}: response_count"
    )

    # #421, first half: the restored conversation reflects the rewritten
    # (compacted) turns, plus the post-rewrite exchange -- never the stale
    # pre-rewrite turn log v1 persisted.
    assert adapter.get_turns_json() == expected["turns"], (
        f"{case['name']}: client turns after the switch round trip"
    )

    # #421, second half: the restored display includes the post-rewrite
    # response; v1 skipped it.
    fake_chat = cast(_FakeChat, controller.chat)
    display = [
        {"role": message["role"], "content": message["segments"][0]["content"]}
        for message in fake_chat.restored_messages
    ]
    assert display == expected["display"], (
        f"{case['name']}: restored conversation display"
    )

    # The round trip went through the on-disk store, not an in-memory
    # hand-off: the persisted record must exist and match the restored one.
    stored = await store.get(controller.partition, conversation_id)  # type: ignore[arg-type]
    assert isinstance(stored, ConversationRecordV2), (
        f"{case['name']}: conversation missing from the file store"
    )
    assert stored == restored, (
        f"{case['name']}: stored record drifted from the restored record"
    )
