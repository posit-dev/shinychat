from pathlib import Path

import pytest
from shiny.run import run_shiny_app


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    return tmp_path / "history"


@pytest.fixture
def local_app(store_dir: Path):
    # Function-scoped: every test gets a fresh app process and a fresh store,
    # so record.json parsing is per-test and counters never leak across
    # tests. The app reads SHINYCHAT_TEST_STORE_DIR and also exposes the
    # directory as its #store_dir output for inspection.
    with run_shiny_app(
        Path(__file__).with_name("app.py"),
        wait_for_start=True,
        env={
            "SHINY_TESTMODE": "1",
            "SHINYCHAT_TEST_STORE_DIR": str(store_dir),
        },
    ) as app:
        yield app
