from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
)


class PersistedModel(BaseModel):
    """Keep fields written by newer schema writers, including explicit nulls."""

    model_config = ConfigDict(extra="allow")

    def _preserve_extra_nulls(
        self, serialized: dict[str, Any], info: SerializationInfo
    ) -> dict[str, Any]:
        if info.exclude_none:
            for key, value in (self.__pydantic_extra__ or {}).items():
                if (
                    value is None
                    and key not in (info.exclude or {})
                    and (info.include is None or key in info.include)
                ):
                    serialized[key] = None
        return serialized

    @model_serializer(mode="wrap")
    def _serialize(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        return self._preserve_extra_nulls(handler(self), info)
