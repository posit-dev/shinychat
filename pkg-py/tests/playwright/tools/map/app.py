import uuid

import ipywidgets
from chatlas import ChatOpenAI, ContentToolResult
from ipyleaflet import CircleMarker, Map
from shiny.express import ui
from shinywidgets import output_widget, register_widget

from shinychat.express import Chat


def tool_show_map(
    lat: float,
    lon: float,
    title: str,
    description: str,
) -> ContentToolResult:
    """Show a map with a marker.

    Use this tool whenever you're talking about a location with the user.
    """

    info = f"<strong>{title}</strong><br>{description}"

    loc = (lat, lon)
    m = Map(center=loc, zoom=10)
    m.add_layer(CircleMarker(location=loc, popup=ipywidgets.HTML(info)))

    id = f"map_{uuid.uuid4().hex}"
    register_widget(id, m)

    return ContentToolResult(
        value="Map shown to the user.",
        extra={
            "display": {
                "html": output_widget(id),
                "show_request": False,
                "open": True,
                "title": f"Map of {title}",
            },
        },
    )


ui.page_opts(fillable=True, title="Map Tool")

client = ChatOpenAI(
    model="gpt-4.1-nano",
    system_prompt="""
You're a helpful guide who can tell users about places and show them maps.

Anytime you mention a location, use the `tool_show_map` tool to show a map with a marker at the location. Don't make the user ask to see the map, just show it automatically when it'd be relevant to have a visual.
""",
)
client.register_tool(tool_show_map)

chat = Chat(id="chat")
chat.ui(
    messages=["Ask me about any location, and I'll show you a map!"],
)


@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await client.stream_async(user_input, content="all")
    await chat.append_message_stream(response)
