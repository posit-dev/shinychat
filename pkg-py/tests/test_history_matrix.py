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
from test_history_controller import _NavFakeAdapter, _NavFakeChat

from shinychat._history import HistoryController
from shinychat._history_store import InMemoryConversationStore

MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "shared"
    / "history-behavior-matrix.json"
)
MATRIX: list[dict[str, Any]] = json.loads(MATRIX_PATH.read_text())


def _make_matrix_controller() -> tuple[HistoryController, InMemoryConversationStore]:
    store = InMemoryConversationStore()
    controller = HistoryController(
        chat=_NavFakeChat(),  # type: ignore[arg-type]
        adapter=_NavFakeAdapter(),  # type: ignore[arg-type]
        store=store,
        title_fn=None,
        title_enabled=False,
        client=None,
    )
    controller.scope = "matrix-scope"
    return controller, store


async def _seed(controller: HistoryController, setup: dict[str, Any]) -> str:
    if setup.get("turns", 0) > 0:
        await controller.on_response()
    assert controller.record is not None, "setup must produce an active record"
    return controller.record.id


def _resolve_args(args: list[Any], active_id: str) -> list[Any]:
    return [active_id if a == "$active_id" else a for a in args]


async def _check_rename(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record.updated_at == ctx["before_updated_at"], (
        "rename() must not change updated_at"
    )


async def _check_delete(ctx: dict[str, Any]) -> None:
    assert ctx["controller"].record is None
    remaining = await ctx["store"].list(ctx["controller"].scope)
    assert ctx["active_id"] not in {m.id for m in remaining}


CUSTOM_CHECKS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "rename_updates_title_and_marks_user_source": _check_rename,
    "delete_active_conversation_clears_controller_record": _check_delete,
}


@pytest.mark.anyio
@pytest.mark.parametrize("case", MATRIX, ids=lambda c: c["name"])
async def test_matrix(case: dict[str, Any]) -> None:
    controller, store = _make_matrix_controller()
    active_id = await _seed(controller, case["setup"])
    before_updated_at = controller.record.updated_at  # type: ignore[union-attr]

    method = case["operation"]["method"]
    args = _resolve_args(case["operation"].get("args", []), active_id)
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
            "before_updated_at": before_updated_at,
        }
        await check(ctx)
