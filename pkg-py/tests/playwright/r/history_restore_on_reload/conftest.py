from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(
    process: subprocess.Popen[str], url: str, timeout: float
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"R Shiny app exited during startup:\n{output}")
        try:
            with urllib.request.urlopen(url, timeout=0.25):
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)

    raise TimeoutError(f"R Shiny app did not become ready at {url}")


@pytest.fixture
def r_app_url(tmp_path: Path) -> Iterator[str]:
    root = Path(__file__).resolve().parents[5]
    app = Path(__file__).with_name("app.R")
    port = available_port()
    url = f"http://127.0.0.1:{port}/"
    env = os.environ.copy()
    env["SHINYCHAT_HISTORY_TEST_DIR"] = str(tmp_path / "history")
    expression = (
        f'pkgload::load_all("{root / "pkg-r"}", quiet = TRUE); '
        f'shiny::runApp("{app}", host = "127.0.0.1", port = {port}, '
        "launch.browser = FALSE)"
    )
    process = subprocess.Popen(
        ["Rscript", "-e", expression],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_until_ready(process, url, timeout=30)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
