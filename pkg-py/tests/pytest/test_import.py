import subprocess
import sys


def test_no_circular_import():
    result = subprocess.run(
        [sys.executable, "-c", "import shinychat"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
