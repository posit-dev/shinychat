import os
from pathlib import Path

from dotenv import load_dotenv
from faicons import icon_svg
from pydantic_ai import Agent
from shiny import App, Inputs, reactive, ui

welcome = """
Welcome to a choose-your-own learning adventure in data science!
Please pick your role, the size of the company you work for, and the industry you're in.
Then click the "Start adventure" button to begin.
"""

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize(
            "company_role",
            "You are a...",
            choices=[
                "Machine Learning Engineer",
                "Data Analyst",
                "Research Scientist",
                "MLOps Engineer",
                "Data Science Generalist",
            ],
            selected="Data Analyst",
        ),
        ui.input_selectize(
            "company_size",
            "who works for...",
            choices=[
                "yourself",
                "a startup",
                "a university",
                "a small business",
                "a medium-sized business",
                "a large business",
                "an enterprise corporation",
            ],
            selected="a medium-sized business",
        ),
        ui.input_selectize(
            "company_industry",
            "in the ... industry",
            choices=[
                "Healthcare and Pharmaceuticals",
                "Banking, Financial Services, and Insurance",
                "Technology and Software",
                "Retail and E-commerce",
                "Media and Entertainment",
                "Telecommunications",
                "Automotive and Manufacturing",
                "Energy and Oil & Gas",
                "Agriculture and Food Production",
                "Cybersecurity and Defense",
            ],
            selected="Healthcare and Pharmaceuticals",
        ),
        ui.input_action_button(
            "go",
            "Start adventure",
            icon=icon_svg("play"),
            class_="btn btn-primary",
        ),
        id="sidebar",
    ),
    ui.chat_ui("chat"),
    title="Choose your own data science adventure",
    fillable=True,
    fillable_mobile=True,
)


def server(input: Inputs):
    _ = load_dotenv()

    try:
        app_dir = Path(__file__).parent
        with open(app_dir / "prompt.md") as f:
            system_prompt_content = f.read()
    except FileNotFoundError:
        print("Error: prompt.md not found. Please create it in the app directory.")
        print("Using a default system prompt for now.")
        system_prompt_content = (
            "You are a storyteller creating an interactive adventure."
        )
    except Exception as e:
        print(f"Error loading prompt.md: {e}")
        system_prompt_content = (
            "You are a storyteller creating an interactive adventure."
        )

    chat_client = Agent(
        "openai:o4-mini",
        api_key=os.environ.get("OPENAI_API_KEY"),
        system_prompt=system_prompt_content,
    )

    chat = ui.Chat(id="chat")

    @reactive.calc
    def starting_prompt():
        return (
            f"I want a story that features a {input.company_role()} "
            f"who works for {input.company_size()} in the {input.company_industry()} industry."
        )

    has_started: reactive.value[bool] = reactive.value(False)

    @reactive.effect
    @reactive.event(input.go)
    async def _():
        if has_started():
            await chat.clear_messages()
            await chat.append_message(welcome)
        chat.update_user_input(value=starting_prompt(), submit=True)
        chat.update_user_input(value="", focus=True)
        has_started.set(True)

    @reactive.effect
    async def _():
        if has_started():
            ui.update_action_button(
                "go", label="Restart adventure", icon=icon_svg("repeat")
            )
            ui.update_sidebar("sidebar", show=False)
        else:
            if not chat.messages():
                await chat.append_message(welcome)
            chat.update_user_input(value=starting_prompt())

    async def pydantic_adventure_stream_generator(current_user_input: str):
        async with chat_client.run_stream(current_user_input) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk

    @chat.on_user_submit
    async def handle_user_submission(user_input: str):
        n_msgs = len(chat.messages())
        current_input_for_llm = user_input

        if n_msgs == 1:
            current_input_for_llm += " Please jump right into the story without any greetings or introductions."
        elif n_msgs == 4:
            current_input_for_llm += ". Time to nudge this story toward its conclusion. Give one more scenario (like creating a report, dashboard, or presentation) that will let me wrap this up successfully."
        elif n_msgs == 5:
            current_input_for_llm += ". Time to wrap this up. Conclude the story in the next step and offer to summarize the chat or create example scripts in R or Python. Consult your instructions for the correct format. If the user asks for code, remember that you'll need to create simulated data that matches the story."

        stream_generator = pydantic_adventure_stream_generator(current_input_for_llm)
        await chat.append_message_stream(stream_generator)


app = App(app_ui, server)
