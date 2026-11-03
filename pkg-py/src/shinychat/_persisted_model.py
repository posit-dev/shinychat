from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PersistedModel(BaseModel):
    """Keep fields written by newer schema writers.

    Parse client input with ``model_validate(..., extra="ignore")`` so
    client-chosen keys never enter saved records.
    """

    model_config = ConfigDict(extra="allow")
