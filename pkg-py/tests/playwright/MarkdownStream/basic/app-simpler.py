import asyncio
from pathlib import Path

from shiny import reactive
from shiny.express import ui
from shinychat.express import MarkdownStream

# Read in the py-shiny README.md file
readme = Path(__file__).parent / "README.md"
with open(readme, "r") as f:
    readme_chunks = f.read()

# Remove everything up to "## Getting started"
# readme_chunks = readme_chunks.split("## Getting started", 1)[-1]
# readme_chunks = "## Getting started" + readme_chunks
readme_chunks = readme_chunks.replace("\n", " \n ").split(" ")


stream = MarkdownStream("shiny_readme")
stream_err = MarkdownStream("shiny_readme_err")


async def readme_generator():
    for chunk in readme_chunks:
        await asyncio.sleep(0.005)
        yield chunk + " "


def readme_generator_err():
    for chunk in readme_chunks:
        yield chunk + " "
        if chunk == "Shiny":
            raise RuntimeError("boom!")


@reactive.effect
async def _():
    await stream.stream(readme_generator())


with ui.card(
    height="600px",
    class_="mt-3",
):
    ui.card_header("Shiny README.md")
    stream.ui(
        code_theme_light="gradient-light",
        code_theme_dark="gradient-dark",
        # code_theme_light="github-light",
        # code_theme_dark="github-dark",
    )

ui.input_dark_mode()

# with ui.card(class_="mt-3"):
#     ui.card_header("Shiny README.md with error")
#     stream_err.ui()


# basic_stream = MarkdownStream("basic_stream_result")
# basic_stream.ui()


# def basic_generator():
#     yield "Basic "
#     yield "stream"


# @reactive.calc
# async def stream_task():
#     return await basic_stream.stream(basic_generator())


# @reactive.effect
# async def _():
#     await stream_task()


# @render.text
# async def stream_result():
#     task = await stream_task()
#     return f"Stream result: {task.result()}"
