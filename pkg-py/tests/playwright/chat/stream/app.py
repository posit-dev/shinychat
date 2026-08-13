from shiny import reactive
from shiny.express import render, ui
from shinychat.express import Chat

ui.page_opts(title="Hello Chat")

# Create and display the chat
chat = Chat(id="chat")
chat.ui()

# Drive the five operations one step at a time, gated by `step`. Under
# single-flight admission, `append_message()`/`append_message_stream()` must
# not be called again for this chat until the previous stream has settled.
#
# `append_message_stream()` only awaits until its background extended task is
# *scheduled*, not until it *settles* -- so a "wait" step reads
# `chat.latest_message_stream.status()` directly (no `reactive.isolate()`) to
# create a real reactive dependency, and only advances `step` once the status
# leaves "running". This mirrors shinychat's own `_on_stream_complete` effect
# in `_chat.py`.
#
# A single busy-poll loop (e.g. isolating the status read and spinning on
# `asyncio.sleep(0)`, as `wait_for_stream()` does in `test_chat.py`) would
# deadlock here: that helper is only safe for test-harness code that drives
# its own `reactive.flush()` between awaits. Inside a real running app, this
# module's startup effects execute during the session's *initial* flush,
# which holds `reactive.lock()` for its entire duration -- and the stream's
# background task needs that same lock to record its result and flush. A
# blocking wait inside one continuous effect would hold the lock forever,
# so the stream could never finish. Splitting the wait into its own effect
# lets the initial flush complete (releasing the lock) while the stream
# finishes in the background; the status effect re-runs once it does.
step = reactive.Value(0)


@reactive.effect
async def _step_0():
    if step() != 0:
        return
    await chat.append_message_stream(("FIRST ", "FIRST ", "FIRST"))
    step.set(1)


@reactive.effect
def _step_1_wait():
    if step() != 1:
        return
    if chat.latest_message_stream.status() == "running":
        return
    step.set(2)


@reactive.effect
async def _step_2():
    if step() != 2:
        return
    await chat.append_message("SECOND SECOND SECOND")
    step.set(3)


@reactive.effect
async def _step_3():
    if step() != 3:
        return
    await chat.append_message_stream(("THIRD ", "THIRD ", "THIRD"))
    step.set(4)


@reactive.effect
def _step_4_wait():
    if step() != 4:
        return
    if chat.latest_message_stream.status() == "running":
        return
    step.set(5)


@reactive.effect
async def _step_5():
    if step() != 5:
        return
    await chat.append_message("FOURTH FOURTH FOURTH")
    step.set(6)


@reactive.effect
async def _step_6():
    if step() != 6:
        return
    await chat.append_message_stream(("FIFTH ", "FIFTH ", "FIFTH"))
    step.set(7)


"Message state:"


@render.code
def message_state():
    return str(chat.messages())
