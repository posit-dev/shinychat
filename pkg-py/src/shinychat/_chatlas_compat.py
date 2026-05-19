"""Compatibility shim for chatlas types not yet public in chatlas.types.

ContentPDF was added to chatlas.types in chatlas 0.19.0. Until our minimum
chatlas version exceeds 0.18.0, we fall back to the private import path.

When pyproject.toml requires chatlas > 0.18.0, delete this file and import
ContentPDF directly from chatlas.types everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatlas._content import ContentPDF as ContentPDF
else:
    try:
        from chatlas.types import ContentPDF as ContentPDF
    except (ImportError, AttributeError):
        from chatlas._content import ContentPDF as ContentPDF
