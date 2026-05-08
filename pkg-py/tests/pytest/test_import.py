import subprocess
import sys


def test_no_circular_import():
    result = subprocess.run(
        [sys.executable, "-c", "import shinychat"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
