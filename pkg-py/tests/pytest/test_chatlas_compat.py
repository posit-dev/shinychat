"""Reminds us to remove _chatlas_compat.py once chatlas min version > 0.18.0."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import Version

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _min_chatlas_version() -> Version:
    text = PYPROJECT.read_text()
    match = re.search(r'"chatlas\b[^"]*>=([\d.]+)', text)
    assert match, f"Could not find chatlas version constraint in {PYPROJECT}"
    return Version(match.group(1))


def test_chatlas_compat_cleanup_reminder():
    min_ver = _min_chatlas_version()
    assert min_ver <= Version("0.18.0"), (
        f"Minimum chatlas version is now {min_ver} (> 0.18.0). "
        "ContentPDF is available in chatlas.types — remove "
        "_chatlas_compat.py and import ContentPDF from chatlas.types directly."
    )
