from pathlib import Path

import pytest
from shiny.run import run_shiny_app


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    return tmp_path / "history"


@pytest.fixture
def local_app(store_dir: Path):
    # The supported process API merges these path-only settings into the child.
    with run_shiny_app(
        Path(__file__).with_name("app.py"),
        wait_for_start=True,
        env={"SHINYCHAT_TEST_STORE_DIR": str(store_dir)},
    ) as app:
        yield app
