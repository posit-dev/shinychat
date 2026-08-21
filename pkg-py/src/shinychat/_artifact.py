from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from htmltools import TagChild

from ._chat_types import ArtifactShowAction, ArtifactUpdateAction
from ._htmltools_serialization import render_htmltools

if TYPE_CHECKING:
    from ._chat import Chat

__all__ = ("ChatArtifactController",)


class ChatArtifactController:
    """Control the artifact region associated with a :class:`~shinychat.Chat`."""

    def __init__(self, chat: Chat):
        self._chat = chat

    async def show(
        self,
        content: TagChild | None = None,
        title: str | None = None,
    ) -> None:
        """Show the artifact, optionally replacing its content or title."""
        await self._send_mutation("artifact_show", content=content, title=title)

    async def hide(self) -> None:
        """Hide the artifact without changing its content."""
        await self._chat._send_action({"type": "artifact_hide"})

    async def toggle(self) -> None:
        """Toggle the artifact's visibility without changing its content."""
        await self._chat._send_action({"type": "artifact_toggle"})

    async def update(
        self,
        content: TagChild | None = None,
        title: str | None = None,
    ) -> None:
        """Update supplied artifact fields without changing its visibility."""
        await self._send_mutation(
            "artifact_update", content=content, title=title
        )

    async def _send_mutation(
        self,
        action_type: Literal["artifact_show", "artifact_update"],
        *,
        content: TagChild | None,
        title: str | None,
    ) -> None:
        if title is not None and not isinstance(title, str):
            raise TypeError(
                f"`title` must be a string or None, not {type(title).__name__}."
            )

        action: ArtifactShowAction | ArtifactUpdateAction
        if action_type == "artifact_show":
            action = {"type": "artifact_show"}
        else:
            action = {"type": "artifact_update"}
        html_deps = None
        if content is not None:
            rendered = render_htmltools(content)
            action["content"] = rendered["html"]
            # Process dependencies through the chat session so Shiny can register
            # local assets before the browser renders the replacement content.
            html_deps = self._chat._serialize_html_deps(
                rendered["dependencies"]
            )
            if html_deps is None:
                html_deps = []
        if title is not None:
            action["title"] = title

        await self._chat._send_action(action, html_deps)
