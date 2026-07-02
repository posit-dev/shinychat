# Cross-language behavior matrix for HistoryController.
#
# Scenarios are defined once in tests/shared/history-behavior-matrix.json and
# consumed by both this file and pkg-r/tests/testthat/test-chat_history_matrix.R
# (via the vendored copy at pkg-r/tests/testthat/fixtures/, kept in sync by
# `make history-matrix-sync`; CI fails the build if that copy drifts — see
# .github/workflows/verify-js-built.yaml).
#
# Only scenarios whose operation has a matching signature in both languages
# belong here (e.g. rename(conv_id, title), delete(conv_id)). Operations that
# take language-specific input shapes (e.g. on_response's turn data) aren't a
# good fit for this generic harness — see
# docs/plans/2026-07-01-chat-history-principal-review.md for scope notes.
#
# Each scenario gets its own "expect" block of plain field-equality checks
# against `controller.record`, plus an optional hand-written custom check
# (below) for anything that isn't a plain equality — e.g. comparing against a
# pre-operation snapshot. Custom checks are ordinary code, not a data-driven
# DSL, specifically so failures are easy to trace back to a real assertion.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest
from shinychat._history import HistoryController
from shinychat._history_store import (
    ConversationPartition,
    InMemoryConversationStore,
)
from test_history_controller import _NavFakeAdapter, _NavFakeChat

MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "shared"
    / "history-behavior-matrix.json"
)
MATRIX: list[dict[str, Any]] = json.loads(MATRIX_PATH.read_text())


def _make_matrix_controller() -> tuple[
    HistoryController, InMemoryConversationStore
]:
    store = InMemoryConversationStore()
    controller = HistoryController(
        chat=_NavFakeChat(),  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.partition = ConversationPartition(
        chat_id="matrix-test", scope="matrix-scope"
    )
    return controller, store


async def _seed(controller: HistoryController, setup: dict[str, Any]) -> dict[str, str]:
    n = setup.get("conversations", 1) if setup.get("turns", 0) > 0 else 0
    ids: list[str] = []
    for i in range(n):
        await controller.on_response()
        assert controller.record is not None, "setup must produce an active record"
        ids.append(controller.record.id)
        if i < n - 1:
            await controller.new_chat()
    assert controller.record is not None, "setup must produce an active record"
    result = {"active_id": controller.record.id}
    if len(ids) >= 2:
        result["first_id"] = ids[0]
    return result


def _resolve_args(args: list[Any], ids: dict[str, str]) -> list[Any]:
    subs = {f"${k}": v for k, v in ids.items()}
    return [subs.get(a, a) for a in args]


async def _check_rename(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record.updated_at == ctx["before_updated_at"], (
        "rename() must not change updated_at"
    )
    partition = ctx["controller"].partition
    assert partition is not None
    stored = await ctx["store"].get(partition, ctx["active_id"])
    assert stored is not None and stored.title == "New Title"


async def _check_delete(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record is None
    partition = ctx["controller"].partition
    assert partition is not None
    remaining = await ctx["store"].list(partition)
    assert ctx["active_id"] not in {m.id for m in remaining}


async def _check_rename_empty_title_is_noop(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record.title == ctx["before_title"]


async def _check_rename_nonexistent_conversation_id_is_noop(
    ctx: dict[str, Any],
) -> None:
    assert ctx["controller"].record.title == ctx["before_title"]


async def _check_switch_to_same_active_id_is_noop(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record.updated_at == ctx["before_updated_at"]


async def _check_new_chat_clears_active_record(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record is None
    partition = ctx["controller"].partition
    assert partition is not None
    stored = await ctx["store"].get(partition, ctx["active_id"])
    assert stored is not None


async def _check_switch_to_inactive_conversation_loads_target_record(
    ctx: dict[str, Any],
) -> None:
    assert ctx["controller"].record.id == ctx["first_id"]
    assert ctx["controller"].record.id != ctx["active_id"]


async def _check_rename_inactive_conversation_updates_store_leaves_active_record(
    ctx: dict[str, Any],
) -> None:
    assert ctx["controller"].record.id == ctx["active_id"]
    partition = ctx["controller"].partition
    assert partition is not None
    stored = await ctx["store"].get(partition, ctx["first_id"])
    assert stored is not None
    assert stored.title == "Renamed Inactive"
    assert stored.title_source == "user"


async def _check_delete_inactive_conversation_leaves_active_record_and_removes_from_store(
    ctx: dict[str, Any],
) -> None:
    assert ctx["controller"].record.id == ctx["active_id"]
    partition = ctx["controller"].partition
    assert partition is not None
    remaining = await ctx["store"].list(partition)
    assert ctx["first_id"] not in {m.id for m in remaining}


CUSTOM_CHECKS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "rename_updates_title_and_marks_user_source": _check_rename,
    "delete_active_conversation_clears_controller_record": _check_delete,
    "rename_empty_title_is_noop": _check_rename_empty_title_is_noop,
    "rename_nonexistent_conversation_id_is_noop": (
        _check_rename_nonexistent_conversation_id_is_noop
    ),
    "switch_to_same_active_id_is_noop": _check_switch_to_same_active_id_is_noop,
    "new_chat_clears_active_record": _check_new_chat_clears_active_record,
    "switch_to_inactive_conversation_loads_target_record": (
        _check_switch_to_inactive_conversation_loads_target_record
    ),
    "rename_inactive_conversation_updates_store_leaves_active_record": (
        _check_rename_inactive_conversation_updates_store_leaves_active_record
    ),
    "delete_inactive_conversation_leaves_active_record_and_removes_from_store": (
        _check_delete_inactive_conversation_leaves_active_record_and_removes_from_store
    ),
}


@pytest.mark.anyio
@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c["name"])
async def test_matrix(case: dict[str, Any]) -> None:
    controller, store = _make_matrix_controller()
    ids = await _seed(controller, case["setup"])
    active_id = ids["active_id"]
    before_updated_at = controller.record.updated_at  # type: ignore[union-attr]
    before_title = controller.record.title  # type: ignore[union-attr]

    method = case["operation"]["method"]
    args = _resolve_args(case["operation"].get("args", []), ids)
    await getattr(controller, method)(*args)

    for field, expected in case.get("expect", {}).items():
        actual = getattr(controller.record, field)
        assert actual == expected, (
            f"{case['name']}: {field} = {actual!r}, expected {expected!r}"
        )

    check = CUSTOM_CHECKS.get(case["name"])
    if check is not None:
        ctx = {
            "controller": controller,
            "store": store,
            "active_id": active_id,
            "first_id": ids.get("first_id"),
            "before_updated_at": before_updated_at,
            "before_title": before_title,
        }
        await check(ctx)
