import os
from dotenv import load_dotenv
from pydantic_ai import Agent
from faicons import icon_svg
from shiny import reactive
from shiny.express import input, render, ui

_ = load_dotenv()

# Create a Pydantic AI agent
chat_client = Agent(
    "openai:o4-mini",
    api_key=os.environ.get("OPENAI_API_KEY"),
    system_prompt="""
    You are a helpful AI fitness coach.
    Give detailed workout plans to users based on their fitness goals and experience level.
    Before getting into details, give a brief introduction to the workout plan.
    Keep the overall tone encouraging and professional yet friendly.
    Generate the response in Markdown format and avoid using h1, h2, or h3.
    """,
)

# Shiny page options 
ui.page_opts(title="Personalized Workout Plan Generator")

# Sidebar UI for user inputs
with ui.sidebar(open={"mobile": "always-above"}):
    ui.input_select(
        "goal",
        "Fitness Goal",
        ["Strength", "Cardio", "Flexibility", "General Fitness"],
    )
    ui.input_selectize(
        "equipment",
        "Available Equipment",
        ["Dumbbells", "Barbell", "Resistance Bands", "Bodyweight"],
        multiple=True,
        selected=["Bodyweight", "Barbell"],
    )
    ui.input_slider("experience", "Experience Level", min=1, max=10, value=5)
    ui.input_slider("duration", "Duration (mins)", min=15, max=90, step=5, value=45)
    ui.input_select(
        "daysPerWeek",
        "Days per Week",
        [str(i) for i in range(1, 8)],
        selected="3",
    )
    ui.input_task_button("generate", "Get Workout", icon=icon_svg("person-running"))

    # Download button UI
    @render.express
    def download_ui():
        plan = workout_stream.latest_stream.result()

        @render.download(filename="workout_plan.md", label="Download Workout")
        def download():
            yield plan


# Create a Markdown stream
workout_stream = ui.MarkdownStream("workout_stream")

# Display the Markdown stream in the main content area
workout_stream.ui(
    content=(
        "Hi there! 👋 I'm your AI fitness coach. 💪"
        "\n\n"
        "Fill out the form in the sidebar to get started. 📝 🏋️‍♂ ️"
    )
)


# Async generator function to stream the response from the Pydantic AI agent
async def pydantic_workout_stream_generator(user_prompt: str):
    """
    An async generator that streams text chunks from the Pydantic AI agent.
    """
    # chat_client is defined globally
    async with chat_client.run_stream(user_prompt) as result:
        async for chunk in result.stream_text(delta=True):
            yield chunk


# Reactive effect to generate workout plan when the button is clicked
@reactive.effect
@reactive.event(input.generate)
async def _():
    # Construct the prompt based on user inputs
    prompt = f"""
    Generate a brief {input.duration()}-minute workout plan for a {input.goal()} fitness goal.
    On a scale of 1-10, I have a level  {input.experience()} experience,
    works out {input.daysPerWeek()} days per week, and have access to:
    {", ".join(input.equipment()) if input.equipment() else "no equipment"}.
    Format the response in Markdown.
    """

    # Generate the stream using the pydantic_workout_stream_generator
    stream_generator = pydantic_workout_stream_generator(prompt)
    
    # Pass the async generator to the MarkdownStream
    await workout_stream.stream(stream_generator)
