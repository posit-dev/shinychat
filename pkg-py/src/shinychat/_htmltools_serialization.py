"""Persistence adapters for htmltools values.

New values use htmltools' source-preserving codec. The legacy reader remains
here because shinychat versions before the htmltools 0.8.0 migration persisted
browser-oriented dependency dictionaries.
"""

from __future__ import annotations

from typing import Any, cast

from htmltools import (
    HTML,
    HTMLDependency,
    SerializedHTML,
    TagChild,
    TagList,
    deserialize_html,
    is_tag_child,
    serialize_html,
)
from pydantic_core import PydanticSerializationError


def serialize_htmltools(value: object) -> SerializedHTML:
    """Serialize an htmltools value for durable persistence."""
    if not is_tag_child(value):
        raise PydanticSerializationError(
            f"Unable to serialize unknown type: {type(value)}"
        )
    return serialize_html(value)


def deserialize_htmltools(value: object) -> TagChild:
    if not isinstance(value, dict):
        if is_tag_child(value):
            return value
        raise TypeError(f"Expected an htmltools value, got {type(value)}")

    if "html" not in value or "dependencies" not in value:
        raise ValueError(f"Don't know how to restore HTML from {value}")

    dependencies = value["dependencies"]
    if not isinstance(dependencies, list):
        raise ValueError(f"Don't know how to restore HTML from {value}")

    if all(is_durable_dependency(dependency) for dependency in dependencies):
        return deserialize_html(cast(SerializedHTML, value))

    return deserialize_legacy_html(value)


def is_durable_dependency(value: object) -> bool:
    return (
        isinstance(value, dict) and "source" in value and "all_files" in value
    )


def deserialize_legacy_html(value: dict[str, Any]) -> TagList:
    dependencies: list[HTMLDependency] = []
    for dependency in value["dependencies"]:
        if not isinstance(dependency, dict):
            continue
        name = dependency["name"]
        version = dependency["version"]
        other = {
            key: item
            for key, item in dependency.items()
            if key not in ("name", "version")
        }
        dependencies.append(HTMLDependency(name=name, version=version, **other))

    return TagList(HTML(value["html"]), *dependencies)
