"""Keep the reproducible complete-record measurement on the CI path."""

import pytest
from measure_history_turn_storage import run_conversation


@pytest.mark.anyio
@pytest.mark.parametrize("tool_heavy", [False, True], ids=["plain", "tools"])
async def test_storage_measurement_round_trips_complete_records(tmp_path, tool_heavy):
    result = await run_conversation(
        exchanges=2, tool_heavy=tool_heavy, store_dir=tmp_path
    )
    assert result.modes == {"snapshot": 1, "delta": 2}
    assert result.production_turn_bytes < result.baseline_turn_bytes
    assert result.production_record_bytes < result.baseline_record_bytes
    assert len(result.growth_series) == 2
    assert result.checks == [
        "per-node exact restore over 3 captures",
        "all-snapshot baseline restores to identical contexts",
        "fresh-controller full restore equals final context",
    ]
