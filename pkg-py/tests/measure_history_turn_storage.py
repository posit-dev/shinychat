"""Reproducible storage measurement for model-checkpoint turn entries.

Measures what the production exchange-tree capture path stores for
representative conversations, comparing the *actual* production record
against an all-snapshot baseline derived from that same record:

- **Production capture** drives the real `HistoryController` +
  `_ExchangeRecorder` + `FileConversationStore` sequence (accepted input,
  stream start/update/finish, response settlement) with a deterministic,
  offline chatlas-shaped turn client. No provider or network is involved;
  the capture, folding, persistence, and restore logic is all production
  code.
- **All-snapshot baseline** deep-copies the actual production record and
  replaces every `shinychat:turns` state entry along the root-to-leaf path
  with a full snapshot of that node's effective turns (materialized with
  the production `materialize_restore_turns`). It is a representation
  change of the same record, not a second capture run with alternate
  semantics; the baseline record is verified to restore to exactly the
  same per-node contexts.

Scenarios: plain-text and tool-heavy conversations at 40 and 100
exchanges. Reported separately, per scenario:

- **turn-payload bytes**: the summed serialized size of the turn lists
  in every `shinychat:turns` entry, excluding state-entry envelopes;
- **whole-record bytes**: the complete serialized `ConversationRecordV2`
  (`model_dump_json(exclude_none=True)`, byte-identical to what the file
  store writes to ``record.json``).

Every run also verifies exact restore round-trips: each captured node's
materialized turns must equal the live client turns at its capture
boundary (canonical JSON equality), and a fresh controller restoring the
saved conversation must end with exactly the final client context. Any
mismatch raises.

Run from the repository root::

    uv run python pkg-py/tests/measure_history_turn_storage.py
    uv run python pkg-py/tests/measure_history_turn_storage.py --json out.json
    uv run python pkg-py/tests/measure_history_turn_storage.py --exchanges 40 --scenarios plain

The measurement is deterministic: conversation content is templated, not
random, so byte counts are stable for a given implementation. Run the
same command before and after a turn-storage policy change to compare.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from shinychat._chat_bookmark import serialize_chatlas_turn
from shinychat._chat_transcript import ChatTranscript, TranscriptEntry
from shinychat._chat_types import StoredMessage, StoredSegment
from shinychat._history_controller import HistoryController
from shinychat._history_plan import (
    StatePathContext,
    materialize_restore_turns,
)
from shinychat._history_store import (
    ConversationPartition,
    FileConversationStore,
)
from shinychat._history_types import (
    TURNS_STATE_KEY,
    ConversationRecordV2,
    StateEntry,
)

MEASURE_PARTITION = ConversationPartition(
    chat_id="measure", scope="measure-scope"
)


# ---------------------------------------------------------------------------
# Deterministic conversation content
# ---------------------------------------------------------------------------

_TOPICS = [
    (
        "deployment",
        "how to deploy a Shiny app to Posit Connect",
        "shinyapps.io",
        "Posit Connect",
        "Kubernetes",
    ),
    (
        "theming",
        "how to theme a chat with brand.yml",
        "colors",
        "typography",
        "CSS custom properties",
    ),
    (
        "performance",
        "how to speed up a slow reactive graph",
        "debouncing",
        "isolation",
        "async handlers",
    ),
    (
        "inputs",
        "how to add a file upload to the chat composer",
        "attachments",
        "drag and drop",
        "validation",
    ),
    (
        "history",
        "how conversation history restores older branches",
        "checkpoints",
        "sparse values",
        "exchange tree",
    ),
]


def _question(index: int) -> str:
    topic, prompt, *extras = _TOPICS[index % len(_TOPICS)]
    return (
        f"Question {index + 1}: {prompt}? "
        f"Please be specific about {extras[0]} and mention {extras[1]} "
        f"so I can compare with our current setup around {extras[2]}."
    )


_ANSWER_PARAGRAPHS = [
    (
        "Start from the smallest working setup and add one variable at a "
        "time. That keeps the failure surface small enough to reason about, "
        "and when something breaks you will know exactly which change broke "
        "it. Prefer boring, documented mechanisms over clever shortcuts; "
        "the next maintainer will thank you."
    ),
    (
        "Measure before and after each change, and keep the numbers in the "
        "pull request description. A change that looks obviously faster can "
        "turn out to be neutral or harmful in a realistic deployment, and "
        "reviewers cannot check a claim they cannot see. Include the "
        "measurement command so anyone can reproduce the result later."
    ),
    (
        "Finally, write down what you decided not to do. Most designs fail "
        "not because the chosen path was wrong, but because nobody recorded "
        "the alternatives that were rejected, so the team re-litigates the "
        "same tradeoff every few months with less context than the original "
        "discussion had."
    ),
]


def _answer(index: int) -> str:
    start = index % len(_ANSWER_PARAGRAPHS)
    paragraphs = [
        _ANSWER_PARAGRAPHS[(start + i) % len(_ANSWER_PARAGRAPHS)]
        for i in range(len(_ANSWER_PARAGRAPHS))
    ]
    return f"Answer {index + 1}.\n\n" + "\n\n".join(paragraphs)


def _tool_preamble(index: int) -> str:
    return f"Let me look that up for question {index + 1}."


def _tool_answer(index: int) -> str:
    return (
        f"Based on the records for question {index + 1}, the practical "
        "guidance is: " + _ANSWER_PARAGRAPHS[index % len(_ANSWER_PARAGRAPHS)]
    )


def _weather_arguments(index: int) -> dict[str, Any]:
    return {
        "city": f"city-{index % 37}",
        "units": "metric",
        "window": {"days": 7, "include_historical": True},
    }


def _tool_value(index: int) -> dict[str, Any]:
    return {
        "location": f"city-{index % 37}",
        "summary": f"Partly cloudy with steady wind ({index % 11} knots)",
        "readings": [
            {
                "day": d,
                "high": 12 + ((index + d) % 14),
                "low": 3 + ((index + d) % 9),
                "precipitation": (index + d) % 5,
            }
            for d in range(7)
        ],
        "cached": index % 2 == 0,
        "source_count": 3,
    }


def _turn(role: str, contents: list[Any]) -> dict[str, Any]:
    from chatlas import Turn

    return serialize_chatlas_turn(Turn(role=role, contents=contents))


def _text_content(text: str) -> Any:
    from chatlas.types import ContentText

    return ContentText(text=text)


def _tool_request_content(index: int) -> Any:
    from chatlas.types import ContentToolRequest

    return ContentToolRequest(
        id=f"req_{index:04d}",
        name="get_weather",
        arguments=_weather_arguments(index),
    )


def _tool_result_content(index: int) -> Any:
    from chatlas.types import ContentToolResult

    return ContentToolResult(
        request=_tool_request_content(index),
        value=_tool_value(index),
    )


# ---------------------------------------------------------------------------
# Offline chatlas-shaped client and fake Chat (production capture host)
# ---------------------------------------------------------------------------


class _MeasureTurnsClient:
    """A deterministic client satisfying the `ClientWithTurns` protocol."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.system_prompt: str | None = None

    def get_turns(self) -> list[dict[str, Any]]:
        return list(self.turns)

    def set_turns(self, turns: list[dict[str, Any]]) -> None:
        self.turns = [copy.deepcopy(t) for t in turns]


class _MeasureAdapter:
    """TurnsAdapter duck-type over the measure client.

    ``chatlas=True`` gives the recorded turn entries the production chatlas
    kind, so restore validates entries through `chatlas.Turn` exactly as a
    real chatlas client's records do.
    """

    def __init__(self, client: _MeasureTurnsClient) -> None:
        self._client = client

    def get_turns_json(
        self, *, include_system_prompt: bool = False
    ) -> list[dict[str, Any]]:
        turns = self._client.get_turns()
        if include_system_prompt and self._client.system_prompt is not None:
            return [
                {"role": "system", "content": self._client.system_prompt},
                *turns,
            ]
        return turns

    def is_chatlas(self) -> bool:
        return True

    def has_system_prompt(self) -> bool:
        return True

    def get_system_prompt(self) -> str | None:
        return self._client.system_prompt

    def set_system_prompt(self, prompt: str | None) -> None:
        self._client.system_prompt = prompt

    def get_turns_grouped(self) -> list[list[dict[str, Any]]]:
        return [[t] for t in self.get_turns_json()]

    def set_turns_json(self, turns: list[dict[str, Any]]) -> None:
        self._client.set_turns(cast("list[dict[str, Any]]", turns))

    def client_info(self) -> dict[str, str]:
        return {"provider": "measure", "model": "measure-1"}


class _InactiveMessageStream:
    def status(self) -> str:
        return "success"


class _FakeChat:
    """The offline Chat stand-in production tests use."""

    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.set_greeting_calls: list[Any] = []
        self.restored_messages: list[dict[str, Any]] = []
        self.restored_icons: list[str | None] = []
        self.messages: list[Any] = []
        self.published_inputs: list[StoredMessage] = []
        self._transcript = ChatTranscript()
        self.latest_message_stream = _InactiveMessageStream()
        self._session = None

    async def _send_action(self, action: Any) -> None:
        self.actions.append(cast("dict[str, Any]", action))

    def _messages_for_bookmark(self) -> list[Any]:
        return self.messages

    async def _clear_messages_screen_only(
        self, *, greeting: bool = False
    ) -> None:
        self.messages.clear()
        self.restored_messages.clear()
        self.restored_icons.clear()
        self._transcript.replace([])

    @asynccontextmanager
    async def _destructive_history_mutation(self, *, block_input: bool = False):
        del block_input
        yield

    def _publish_accepted_user_input(self, message: StoredMessage) -> None:
        self.published_inputs.append(message)

    async def set_greeting(self, greeting: Any) -> None:
        self.set_greeting_calls.append(greeting)

    async def _restore_bookmark_message(
        self, message_dict: Any, *, icon: str | None = None
    ) -> None:
        self.restored_messages.append(cast("dict[str, Any]", message_dict))
        self.restored_icons.append(icon)


async def _sent() -> bool:
    return True


def _stored_message(role: str, content: str) -> StoredMessage:
    return StoredMessage(
        role=cast(Any, role),
        segments=[StoredSegment(content=content, content_type="markdown")],
    )


def _tool_stored_message(
    preamble: str, request_id: str, answer: str
) -> StoredMessage:
    return StoredMessage(
        role="assistant",
        segments=[
            StoredSegment(content=preamble, content_type="markdown"),
            cast(
                Any,
                {
                    "type": "tool_request",
                    "version": 1,
                    "request_id": request_id,
                    "tool_name": "get_weather",
                },
            ),
            cast(
                Any,
                {
                    "type": "tool_result",
                    "version": 1,
                    "request_id": request_id,
                    "tool_name": "get_weather",
                    "status": "success",
                },
            ),
            StoredSegment(content=answer, content_type="markdown"),
        ],
    )


# ---------------------------------------------------------------------------
# Byte accounting
# ---------------------------------------------------------------------------


def record_bytes(record: ConversationRecordV2) -> int:
    """Complete record serialization, as the file store writes it."""
    return len(record.model_dump_json(exclude_none=True).encode("utf-8"))


def turn_entry_bytes(entry: StateEntry) -> int:
    return len(
        json.dumps(
            entry.data,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def turn_payload_bytes(record: ConversationRecordV2) -> int:
    """Summed serialized turn lists, excluding state-entry envelopes."""
    return sum(
        turn_entry_bytes(node.state[TURNS_STATE_KEY])
        for node in record.nodes.values()
        if TURNS_STATE_KEY in node.state
    )


def entry_modes(record: ConversationRecordV2) -> dict[str, int]:
    modes: dict[str, int] = {}
    for node in record.nodes.values():
        entry = node.state.get(TURNS_STATE_KEY)
        if entry is not None:
            modes[entry.mode] = modes.get(entry.mode, 0) + 1
    return modes


def _path_context(
    record: ConversationRecordV2, node_id: str
) -> StatePathContext:
    path: list[str] = []
    cursor: str | None = node_id
    while cursor is not None:
        path.append(cursor)
        cursor = record.nodes[cursor].parent_id
    path.reverse()
    return StatePathContext(
        conversation_id=record.id,
        active_leaf=node_id,
        node_ids=tuple(path),
        entries=tuple(
            (nid, record.nodes[nid].state[TURNS_STATE_KEY])
            for nid in path
            if TURNS_STATE_KEY in record.nodes[nid].state
        ),
    )


def canonical_turn_json(turns: list[dict[str, Any]]) -> list[str]:
    return [
        json.dumps(t, allow_nan=False, sort_keys=True, separators=(",", ":"))
        for t in turns
    ]


# ---------------------------------------------------------------------------
# Conversation runner
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    name: str
    exchanges: int
    tool_heavy: bool
    modes: dict[str, int]
    production_turn_bytes: int
    production_record_bytes: int
    baseline_turn_bytes: int
    baseline_record_bytes: int
    # Cumulative production turn-payload bytes after each settled exchange,
    # demonstrating append-only growth shape (quadratic vs linear).
    growth_series: list[int] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def turn_saving(self) -> float:
        if self.baseline_turn_bytes == 0:
            return 0.0
        return 1 - self.production_turn_bytes / self.baseline_turn_bytes

    @property
    def record_saving(self) -> float:
        if self.baseline_record_bytes == 0:
            return 0.0
        return 1 - self.production_record_bytes / self.baseline_record_bytes


def _wire(controller: HistoryController) -> ChatTranscript:
    recorder = controller._exchange_recorder
    assert recorder is not None
    return ChatTranscript(
        on_accepted_input=recorder.accepted_input,
        on_stream_started=recorder.stream_started,
        on_stream_updated=recorder.stream_updated,
        on_stream_finished=recorder.stream_finished,
    )


async def run_conversation(
    *, exchanges: int, tool_heavy: bool, store_dir: Path
) -> ScenarioResult:
    client = _MeasureTurnsClient()
    adapter = _MeasureAdapter(client)
    store = FileConversationStore(store_dir)
    reader = FileConversationStore(store_dir)
    controller = HistoryController(
        chat=cast(Any, _FakeChat()),
        adapter=cast(Any, adapter),
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = MEASURE_PARTITION
    transcript = _wire(controller)

    # node id -> live client turns at that node's last model capture.
    expected: dict[str, list[dict[str, Any]]] = {}
    growth_series: list[int] = []

    async def settle() -> None:
        await controller.on_response()
        live = controller._exchange_recorder.record
        assert live is not None
        growth_series.append(turn_payload_bytes(live))

    for index in range(exchanges):
        context = list(client.turns)
        record_before = controller._exchange_recorder.record
        if record_before is not None:
            active = record_before.active_leaf
            assert active is not None
            expected[active] = copy.deepcopy(context)
        else:
            # The first accepted input captures the fresh record's starting
            # root ("n_0000" by construction) before provider work.
            expected["n_0000"] = copy.deepcopy(context)

        exchange_id = await transcript.record_accepted_input_and_notify(
            _stored_message("user", _question(index))
        )
        client.turns = [
            *context,
            _turn("user", [_text_content(_question(index))]),
        ]
        await transcript.start_stream(
            stream_id="stream",
            entry=TranscriptEntry(message=_stored_message("assistant", "")),
            owner_task=None,
            exchange_id=exchange_id,
            send=_sent,
        )
        if tool_heavy:
            client.turns = [
                *client.turns,
                _turn("assistant", [_tool_request_content(index)]),
                _turn("user", [_tool_result_content(index)]),
            ]
            message = _tool_stored_message(
                _tool_preamble(index), f"req_{index:04d}", _tool_answer(index)
            )
        else:
            message = _stored_message("assistant", _answer(index))
        client.turns = [
            *client.turns,
            _turn("assistant", [_text_content(_answer(index))]),
        ]
        await transcript.transition_stream(
            stream_id="stream",
            source_segments=[],
            message=message,
            operation="append",
            send=_sent,
        )
        expected[exchange_id] = copy.deepcopy(client.turns)
        await transcript.end_stream(
            stream_id="stream", status=None, error=None, send=_sent
        )
        await settle()

    recorder = controller._exchange_recorder
    record = recorder.record
    assert record is not None
    conv_id = record.id

    # The complete record as it reached disk, read through a fresh store
    # instance (no in-memory aliasing).
    saved = await reader.get(MEASURE_PARTITION, conv_id)
    assert isinstance(saved, ConversationRecordV2)

    checks: list[str] = []

    # 1. Exact per-node restore round-trip from the production record.
    for node_id in saved.path_node_ids():
        if TURNS_STATE_KEY not in saved.nodes[node_id].state:
            continue
        turns, unavailable = materialize_restore_turns(
            _path_context(saved, node_id), adapter=cast(Any, adapter)
        )
        assert unavailable is None, (node_id, unavailable)
        assert node_id in expected, node_id
        assert canonical_turn_json(turns) == canonical_turn_json(
            expected[node_id]
        ), f"restore mismatch at {node_id}"
    checks.append(f"per-node exact restore over {len(expected)} captures")

    # 2. All-snapshot baseline: same record, every turns entry replaced by a
    # full snapshot of that node's effective turns. This is the
    # representation the pre-delta policy stored; it must restore to
    # exactly the same contexts.
    effective: dict[str, list[dict[str, Any]]] = {}
    for node_id in saved.path_node_ids():
        if TURNS_STATE_KEY not in saved.nodes[node_id].state:
            continue
        turns, unavailable = materialize_restore_turns(
            _path_context(saved, node_id), adapter=cast(Any, adapter)
        )
        assert unavailable is None, (node_id, unavailable)
        effective[node_id] = turns
    baseline = saved.model_copy(deep=True)
    for node_id, turns in effective.items():
        original = saved.nodes[node_id].state[TURNS_STATE_KEY]
        baseline.nodes[node_id].state[TURNS_STATE_KEY] = StateEntry(
            kind=original.kind,
            version=original.version,
            mode="snapshot",
            data=cast(Any, copy.deepcopy(turns)),
        )
    for node_id, turns in effective.items():
        materialized, unavailable = materialize_restore_turns(
            _path_context(baseline, node_id), adapter=cast(Any, adapter)
        )
        assert unavailable is None, (node_id, unavailable)
        assert canonical_turn_json(materialized) == canonical_turn_json(
            expected[node_id]
        ), f"baseline restore mismatch at {node_id}"
    checks.append("all-snapshot baseline restores to identical contexts")

    # 3. Full conversation restore through a second controller: the saved
    # selection must rebuild exactly the final live client context.
    viewer_client = _MeasureTurnsClient()
    viewer_client.turns = [_turn("user", [_text_content("stale context")])]
    viewer = HistoryController(
        chat=cast(Any, _FakeChat()),
        adapter=cast(Any, _MeasureAdapter(viewer_client)),
        store=reader,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    viewer.partition = MEASURE_PARTITION
    await viewer.switch_to(conv_id)
    assert saved.active_leaf is not None
    final_expected = expected[saved.active_leaf]
    assert canonical_turn_json(viewer_client.turns) == canonical_turn_json(
        final_expected
    ), "fresh full-restore context mismatch"
    checks.append("fresh-controller full restore equals final context")

    return ScenarioResult(
        name=("tools" if tool_heavy else "plain") + f"-{exchanges}",
        exchanges=exchanges,
        tool_heavy=tool_heavy,
        modes=entry_modes(saved),
        production_turn_bytes=turn_payload_bytes(saved),
        production_record_bytes=record_bytes(saved),
        baseline_turn_bytes=turn_payload_bytes(baseline),
        baseline_record_bytes=record_bytes(baseline),
        growth_series=growth_series,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _growth_report(result: ScenarioResult) -> str:
    series = result.growth_series
    if len(series) < 4:
        return "n/a"
    quarter = max(1, len(series) // 4)
    early = (series[quarter] - series[0]) / quarter
    late = (series[-1] - series[-quarter - 1]) / quarter
    return (
        f"per-exchange turn-payload growth: "
        f"first quarter ~{_fmt_bytes(round(early))}/exchange, "
        f"last quarter ~{_fmt_bytes(round(late))}/exchange "
        f"(flat=linear, rising=quadratic)"
    )


def print_report(results: list[ScenarioResult]) -> None:
    print("Model checkpoint turn-storage measurement")
    print("=" * 72)
    for result in results:
        mode_summary = ", ".join(
            f"{count} {mode}" for mode, count in sorted(result.modes.items())
        )
        print()
        print(f"{result.name}: {result.exchanges} exchanges")
        print(f"  production turn entries : {mode_summary or 'none'}")
        print(
            f"  turn-payload bytes      : production "
            f"{_fmt_bytes(result.production_turn_bytes)} vs all-snapshot "
            f"{_fmt_bytes(result.baseline_turn_bytes)} "
            f"({result.turn_saving:.1%} saved by production policy)"
        )
        print(
            f"  whole-record bytes      : production "
            f"{_fmt_bytes(result.production_record_bytes)} vs all-snapshot "
            f"{_fmt_bytes(result.baseline_record_bytes)} "
            f"({result.record_saving:.1%} smaller)"
        )
        print(f"  growth                  : {_growth_report(result)}")
        for check in result.checks:
            print(f"  verified                : {check}")
    print()
    print(
        "Notes: turn-payload bytes count only `shinychat:turns` data "
        "lists; whole-record bytes are the complete serialized "
        "ConversationRecordV2 (turns + repeated UI payloads + metadata), so "
        "whole-record savings are bounded by the repeated UI payload, which "
        "this policy does not change."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchanges",
        default="40,100",
        help="comma-separated exchange counts (default: 40,100)",
    )
    parser.add_argument(
        "--scenarios",
        default="plain,tools",
        help="comma-separated scenarios: plain,tools (default: both)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="also write results as JSON to this path",
    )
    parser.add_argument(
        "--keep-dir",
        action="store_true",
        help="keep the measurement store directory instead of a tempdir",
    )
    args = parser.parse_args(argv)

    exchanges = [int(x) for x in str(args.exchanges).split(",")]
    requested = {s.strip() for s in str(args.scenarios).split(",")}
    scenarios = [
        (name, tool_heavy)
        for name, tool_heavy in (("plain", False), ("tools", True))
        if name in requested
    ]

    if args.keep_dir:
        store_root = Path("measure_history_store").absolute()
        store_root.mkdir(exist_ok=True)
        cleanup = None
    else:
        tmp = tempfile.TemporaryDirectory()  # noqa: SIM115 - cleaned below
        cleanup = tmp
        store_root = Path(tmp.name)
    try:
        results = [
            asyncio.run(
                run_conversation(
                    exchanges=count,
                    tool_heavy=tool_heavy,
                    store_dir=store_root / f"{name}-{count}",
                )
            )
            for name, tool_heavy in scenarios
            for count in exchanges
        ]
    finally:
        if cleanup is not None:
            cleanup.cleanup()

    print_report(results)

    if args.json is not None:
        payload = {
            "results": [
                {
                    "name": r.name,
                    "exchanges": r.exchanges,
                    "tool_heavy": r.tool_heavy,
                    "modes": r.modes,
                    "production_turn_payload_bytes": (r.production_turn_bytes),
                    "production_whole_record_bytes": (
                        r.production_record_bytes
                    ),
                    "all_snapshot_turn_payload_bytes": r.baseline_turn_bytes,
                    "all_snapshot_whole_record_bytes": (
                        r.baseline_record_bytes
                    ),
                    "growth_series_turn_payload_bytes": r.growth_series,
                    "checks": r.checks,
                }
                for r in results
            ]
        }
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
