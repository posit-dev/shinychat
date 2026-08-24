from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, cast

import pytest
from htmltools import HTMLDependency, TagList, tags
from pydantic_core import PydanticSerializationError
from shiny import Inputs, Session
from shiny.module import ResolvedId
from shiny.session import session_context
from shinychat import Chat
from shinychat.types import ChatDrawerController


class _ArtifactSession:
    ns: ResolvedId = ResolvedId("")
    app: object = None
    id: str = "artifact-session"

    def __init__(self) -> None:
        self.input = Inputs({}, ns=ResolvedId)
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def on_ended(self, callback: object) -> None:
        pass

    def on_destroy(self, callback: object) -> None:
        pass

    def _increment_busy_count(self) -> None:
        pass

    def _process_ui(self, ui: object) -> dict[str, object]:
        rendered = TagList(cast(Any, ui)).render()
        return {
            "html": rendered["html"],
            "deps": [
                {"name": dependency.name, "from_session": self.id}
                for dependency in rendered["dependencies"]
            ],
        }

    async def send_custom_message(
        self, type: str, message: dict[str, Any]
    ) -> None:
        self.messages.append((type, message))


def _make_chat() -> tuple[Chat, _ArtifactSession]:
    session = _ArtifactSession()
    with session_context(cast(Session, session)):
        chat = Chat("chat")
    return chat, session


def _run_async(coro: Any) -> None:
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            asyncio.run(coro)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


def test_drawer_controller_is_stable_and_public() -> None:
    chat, _ = _make_chat()

    assert isinstance(chat.drawer, ChatDrawerController)
    assert chat.drawer is chat.drawer


def test_drawer_controller_methods_are_async_with_expected_signatures() -> (
    None
):
    for method in (
        ChatDrawerController.show,
        ChatDrawerController.hide,
        ChatDrawerController.toggle,
        ChatDrawerController.update,
    ):
        assert inspect.iscoroutinefunction(method)

    for method in (
        ChatDrawerController.show,
        ChatDrawerController.update,
    ):
        parameters = inspect.signature(method).parameters
        assert tuple(parameters) == ("self", "content", "title")
        assert parameters["content"].default is None
        assert parameters["title"].default is None

    for method in (
        ChatDrawerController.hide,
        ChatDrawerController.toggle,
    ):
        assert tuple(inspect.signature(method).parameters) == ("self",)


def test_artifact_actions_omit_unsupplied_fields_and_preserve_visibility() -> (
    None
):
    chat, session = _make_chat()

    _run_async(chat.drawer.show())
    _run_async(chat.drawer.update(title="Preview"))
    _run_async(chat.drawer.hide())
    _run_async(chat.drawer.toggle())

    assert session.messages == [
        (
            "shinyChatMessage",
            {"id": "chat", "action": {"type": "drawer_show"}},
        ),
        (
            "shinyChatMessage",
            {
                "id": "chat",
                "action": {"type": "drawer_update", "title": "Preview"},
            },
        ),
        (
            "shinyChatMessage",
            {"id": "chat", "action": {"type": "drawer_hide"}},
        ),
        (
            "shinyChatMessage",
            {"id": "chat", "action": {"type": "drawer_toggle"}},
        ),
    ]


@pytest.mark.parametrize("content", ["", TagList()])
def test_artifact_empty_content_clears_dependencies(content: object) -> None:
    chat, session = _make_chat()

    _run_async(chat.drawer.update(cast(Any, content), title=""))

    assert session.messages == [
        (
            "shinyChatMessage",
            {
                "id": "chat",
                "action": {
                    "type": "drawer_update",
                    "content": "",
                    "title": "",
                },
                "html_deps": [],
            },
        )
    ]


def test_artifact_content_uses_chat_session_dependency_serialization() -> None:
    chat, session = _make_chat()
    dependency = HTMLDependency(
        "artifact-widget",
        "1.0.0",
        source={"subdir": "."},
        stylesheet={"href": "widget.css"},
    )

    _run_async(
        chat.drawer.show(
            tags.div(dependency, "Artifact content"), title="Preview"
        )
    )

    assert session.messages == [
        (
            "shinyChatMessage",
            {
                "id": "chat",
                "action": {
                    "type": "drawer_show",
                    "content": "<div>Artifact content</div>",
                    "title": "Preview",
                },
                "html_deps": [
                    {
                        "name": "artifact-widget",
                        "from_session": "artifact-session",
                    }
                ],
            },
        )
    ]


def test_artifact_tagifiable_content_includes_tagified_dependencies() -> None:
    class ArtifactContent:
        def tagify(self):
            dependency = HTMLDependency(
                "tagified-artifact",
                "1.0.0",
                source={"subdir": "."},
            )
            return TagList(
                dependency,
                tags.div("Tagified artifact content"),
            ).tagify()

    chat, session = _make_chat()

    _run_async(chat.drawer.show(cast(Any, ArtifactContent())))

    assert session.messages == [
        (
            "shinyChatMessage",
            {
                "id": "chat",
                "action": {
                    "type": "drawer_show",
                    "content": "<div>Tagified artifact content</div>",
                },
                "html_deps": [
                    {
                        "name": "tagified-artifact",
                        "from_session": "artifact-session",
                    }
                ],
            },
        )
    ]


def test_artifact_uses_resolved_chat_id_and_envelope() -> None:
    session = _ArtifactSession()
    session.ns = ResolvedId("module")
    with session_context(cast(Session, session)):
        chat = Chat("chat")

    _run_async(chat.drawer.show(tags.span("Artifact")))

    assert session.messages == [
        (
            "shinyChatMessage",
            {
                "id": "module-chat",
                "action": {
                    "type": "drawer_show",
                    "content": "<span>Artifact</span>",
                },
                "html_deps": [],
            },
        )
    ]


def test_artifact_validates_title_and_content() -> None:
    chat, _ = _make_chat()

    with pytest.raises(TypeError, match="`title` must be a string or None"):
        _run_async(chat.drawer.show(title=cast(Any, 1)))
    with pytest.raises(PydanticSerializationError, match="Unable to serialize"):
        _run_async(chat.drawer.show(cast(Any, object())))
