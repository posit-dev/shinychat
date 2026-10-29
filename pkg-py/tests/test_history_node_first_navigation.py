"""Position-only restrictions clear; unrelated restore restrictions do not."""

from typing import Any, cast

import pytest
from _history_test_helpers import replay_exchange_record
from shinychat._chat_types import ReadOnlyReason
from shinychat._history_types import TURNS_STATE_KEY, StateEntry
from test_history_controller import _FakeAdapter, _make_controller
from test_history_node_first import _record_with_browsable_failure


@pytest.mark.anyio
async def test_terminal_visit_does_not_lock_healthy_branch() -> None:
    controller, _store = _make_controller()
    record, original, failed = _record_with_browsable_failure()
    record.set_active_leaf(original)
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    adapter = cast(_FakeAdapter, controller.adapter)
    assert not recorder.read_only

    await controller.handle_navigate(0, "next", request_id="visit-failure")
    assert recorder.record is not None
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "terminal_incomplete"
    await controller.handle_navigate(0, "prev", request_id="return-healthy")

    assert recorder.record.active_leaf == original
    assert not recorder.read_only
    assert adapter.turns == [{"role": "user", "content": "B"}]


@pytest.mark.anyio
async def test_failed_healthy_restore_escalates_terminal_restriction() -> None:
    controller, _store = _make_controller()
    record, original, _failed = _record_with_browsable_failure()
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    assert recorder.read_only_reason == "terminal_incomplete"

    def broken_restore(_values: dict[str, Any]) -> None:
        raise ValueError("application still broken")

    controller._restore_callbacks.append(broken_restore)
    with pytest.warns(UserWarning, match="on_restore callback failed"):
        await controller.handle_navigate(0, "prev", request_id="broken-return")

    assert recorder.record is not None
    assert recorder.record.active_leaf == original
    assert recorder.read_only
    assert recorder.read_only_reason == "app_restore_failed"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("reason", "isolated"),
    [
        ("app_restore_failed", False),
        ("model_unavailable", False),
        ("interrupted", True),
    ],
)
async def test_healthy_navigation_keeps_unrelated_restrictions(
    reason: ReadOnlyReason, isolated: bool
) -> None:
    controller, store = _make_controller()
    record, original, _failed = _record_with_browsable_failure()
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    recorder.install_restored_record(
        recorder.record,
        read_only=True,
        read_only_reason=reason,
        source_isolated=isolated,
    )
    writes_before = len(store.put_calls)

    await controller.handle_navigate(0, "prev", request_id="restricted-return")

    assert recorder.record is not None
    assert recorder.record.active_leaf == original
    assert recorder.read_only
    assert recorder.read_only_reason == reason
    assert recorder.source_isolated == isolated
    if isolated:
        assert len(store.put_calls) == writes_before


@pytest.mark.anyio
async def test_unavailable_healthy_context_remains_browsable_without_continuation() -> (
    None
):
    controller, _store = _make_controller()
    record, original, failed = _record_with_browsable_failure()
    record.nodes[original].state[TURNS_STATE_KEY] = StateEntry(
        kind="foreign_turns", version=1, mode="snapshot", data=[]
    )
    await replay_exchange_record(controller, record)
    recorder = controller._exchange_recorder
    assert recorder.record is not None
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "terminal_incomplete"

    await controller.handle_navigate(
        0, "prev", request_id="unavailable-original"
    )

    assert recorder.record.active_leaf == original
    assert recorder.read_only
    assert recorder.read_only_reason == "model_unavailable"
    # Returning to a compatible sibling cannot clear a discovered hard
    # model restriction merely because that sibling is displayable.
    await controller.handle_navigate(0, "next", request_id="return-failed")
    assert recorder.record.active_leaf == failed
    assert recorder.read_only_reason == "model_unavailable"
    assert not controller._can_resubmit_active()
