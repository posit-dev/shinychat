"""Helpers for user-uploaded chat attachments (images, PDFs, and text files).

This is a private module: module-level functions are intentionally not
underscore-prefixed.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from htmltools import html_escape
from pydantic import BaseModel
from typing_extensions import TypedDict

from ._utils_types import MISSING_TYPE

if TYPE_CHECKING:
    from chatlas.types import Content


class _AttachmentTypesJson(TypedDict):
    image_types: list[str]
    pdf_type: str
    text_extensions: dict[str, str]


def _load_attachment_types() -> _AttachmentTypesJson:
    path = Path(__file__).parent / "www" / "attachment-types.json"
    with open(path) as f:
        res: _AttachmentTypesJson = json.load(f)
        return res


_TYPES = _load_attachment_types()

TEXT_ATTACHMENT_TYPES: tuple[str, ...] = tuple(
    dict.fromkeys(_TYPES["text_extensions"].values())
)

SUPPORTED_ATTACHMENT_TYPES: tuple[str, ...] = (
    *_TYPES["image_types"],
    _TYPES["pdf_type"],
    *TEXT_ATTACHMENT_TYPES,
)


class Attachment(BaseModel):
    """An image, PDF, or text file to attach to a chat message.

    Construct via :meth:`from_path`, :meth:`from_data`, or :meth:`from_url`.
    """

    mime: str
    name: str
    size: int = 0
    data_url: str

    def __str__(self) -> str:
        label = "image" if self.mime.startswith("image/") else "file"
        return f"[{label}: {self.name or 'attachment'}]"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        mime: str | None = None,
        name: str | None = None,
    ) -> "Attachment":
        """Create an attachment from a filesystem path."""
        p = Path(path)
        raw = p.read_bytes()
        resolved_mime = (
            mime
            or mimetypes.guess_type(p.name)[0]
            or "application/octet-stream"
        )
        return cls(
            mime=resolved_mime,
            name=name or p.name,
            size=len(raw),
            data_url=f"data:{resolved_mime};base64,{base64.b64encode(raw).decode()}",
        )

    @classmethod
    def from_data(
        cls,
        data: bytes,
        mime: str,
        *,
        name: str | None = None,
    ) -> "Attachment":
        """Create an attachment from raw bytes."""
        return cls(
            mime=mime,
            name=name or "",
            size=len(data),
            data_url=f"data:{mime};base64,{base64.b64encode(data).decode()}",
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        mime: str | None = None,
        name: str | None = None,
    ) -> "Attachment":
        """Create an attachment from a data URL or remote http(s) URL.

        For ``data:`` URLs, the binary payload is decoded immediately to compute
        ``size``.  Remote ``http(s)`` URLs are stored as-is (no network request
        is made), so ``size`` will be 0.
        """
        if url.startswith("data:"):
            raw = decode_data_url(url)
            semi = url.find(";", 5)
            comma = url.find(",", 5)
            boundary = semi if semi != -1 else comma
            parsed_mime = url[5:boundary] if boundary != -1 else ""
            resolved_mime = mime or parsed_mime or "application/octet-stream"
            return cls(
                mime=resolved_mime,
                name=name or "",
                size=len(raw),
                data_url=url,
            )
        resolved_mime = (
            mime or mimetypes.guess_type(url)[0] or "application/octet-stream"
        )
        return cls(
            mime=resolved_mime,
            name=name or "",
            size=0,
            data_url=url,
        )


#: Default total attachment-size cap (bytes) when the environment variable is
#: not set. Keep in sync with js DEFAULT_MAX_ATTACHMENT_SIZE.
DEFAULT_MAX_ATTACHMENT_SIZE = 30 * 1024 * 1024

#: Environment variable that sets the max combined attachment size (in bytes).
MAX_ATTACHMENT_SIZE_ENV_VAR = "SHINYCHAT_MAX_ATTACHMENT_SIZE"


def resolve_max_attachment_size() -> int:
    """Resolve the max combined attachment size (bytes).

    Reads ``SHINYCHAT_MAX_ATTACHMENT_SIZE`` as a raw byte count; falls back to
    ``DEFAULT_MAX_ATTACHMENT_SIZE`` when unset.
    """
    env = os.environ.get(MAX_ATTACHMENT_SIZE_ENV_VAR)
    if env is not None and env.strip():
        try:
            val = int(env)
        except ValueError:
            raise ValueError(
                f"{MAX_ATTACHMENT_SIZE_ENV_VAR}={env!r} is not a valid integer byte count."
            ) from None
        if val < 0:
            raise ValueError(
                f"{MAX_ATTACHMENT_SIZE_ENV_VAR} must be non-negative, got {val}."
            )
        return val
    return DEFAULT_MAX_ATTACHMENT_SIZE


def resolve_attachment_attrs(
    allow_attachments: "bool | list[str] | MISSING_TYPE",
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the ``allow_attachments`` value into (allow-attachments,
    attachment-accept) attrs.

    Returns a 2-tuple of attribute string values (or ``None`` to omit). A list
    restricts accepted MIME types to a subset of ``SUPPORTED_ATTACHMENT_TYPES``;
    an unsupported MIME raises ``ValueError``.
    """
    if isinstance(allow_attachments, MISSING_TYPE):
        return None, None
    if isinstance(allow_attachments, bool):
        return ("true" if allow_attachments else "false"), None
    if isinstance(allow_attachments, (list, tuple)):
        invalid = [
            m for m in allow_attachments if m not in SUPPORTED_ATTACHMENT_TYPES
        ]
        if invalid:
            raise ValueError(
                f"allow_attachments contains unsupported MIME type(s): {invalid}. "
                f"Supported types: {list(SUPPORTED_ATTACHMENT_TYPES)}"
            )
        if len(allow_attachments) == 0:
            return "false", None
        return "true", ",".join(allow_attachments)
    raise TypeError(
        f"allow_attachments must be bool, list[str], or MISSING, not {type(allow_attachments)}"
    )


def is_text_type(mime: str) -> bool:
    """Whether ``mime`` is one of the text-family attachment types."""
    return mime in TEXT_ATTACHMENT_TYPES


def attachment_to_content(att: Attachment) -> "Content":
    """Convert an attachment into a chatlas content object.

    chatlas is an optional dependency (only needed for the ``client=`` auto
    path), so it is imported lazily here.
    """
    from chatlas import content_image_url
    from chatlas.types import ContentPDF

    if att.mime.startswith("image/"):
        return content_image_url(att.data_url)
    if att.mime == "application/pdf":
        _require_data_url(att)
        data = decode_data_url(att.data_url)
        return ContentPDF(data=data, filename=att.name or "document.pdf")
    if is_text_type(att.mime):
        from chatlas.types import ContentText

        _require_data_url(att)
        text = decode_data_url(att.data_url).decode("utf-8", errors="replace")
        name = att.name or "file"
        return ContentText(
            text=(
                f'<file-attachment name="{html_escape(name, attr=True)}" '
                f'type="{html_escape(att.mime, attr=True)}">\n{text}\n</file-attachment>'
            )
        )
    raise ValueError(f"Unsupported attachment type: {att.mime}")


def _require_data_url(att: Attachment) -> None:
    if not att.data_url.startswith("data:"):
        raise ValueError(
            f"attachment_to_content() requires a base64 data URL for "
            f"{att.mime} attachments, but got a remote URL. "
            f"Use Attachment.from_path() or Attachment.from_data() instead."
        )


def decode_data_url(data_url: str) -> bytes:
    comma = data_url.find(",")
    if comma == -1:
        raise ValueError("Malformed data URL")
    try:
        return base64.b64decode(data_url[comma + 1 :])
    except Exception as e:
        raise ValueError("Malformed base64 payload in data URL") from e
