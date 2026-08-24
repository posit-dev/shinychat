"""
OpenTelemetry instrumentation for managed chat responses.

One ``shinychat.response`` span per managed response, carrying
``gen_ai.conversation.id``, so downstream consumers (e.g. Posit Commons) can
attribute model work to a conversation. The span is active for the full
consumption of the response stream, so chatlas (or other client) spans nest
beneath it.

Tracing is strictly observational: with no SDK provider configured the spans
are non-recording no-ops, and any tracer/span failure falls back to a plain
nullcontext so telemetry can never break the model call.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, AsyncIterable, AsyncIterator

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


def response_span(conversation_id: str | None) -> "AbstractContextManager[Any]":
    """
    Context manager for a managed response's ``shinychat.response`` span.

    Returns a no-op context when there is no conversation ID (history
    disabled or empty draft) or when OpenTelemetry is unavailable/fails.
    """
    if conversation_id is None:
        return nullcontext()
    try:
        from opentelemetry import trace
    except ImportError:
        return nullcontext()
    try:
        # Resolved fresh per response: a tracer cached at import time would
        # still delegate dynamically (the OTel API returns a proxy tracer),
        # but resolving here keeps failure isolation trivial.
        tracer = trace.get_tracer("shinychat")
        return tracer.start_as_current_span(
            "shinychat.response",
            attributes={"gen_ai.conversation.id": conversation_id},
        )
    except Exception:
        return nullcontext()


async def trace_response_stream(
    stream: AsyncIterable[Any],
    conversation_id: str | None,
) -> AsyncIterator[Any]:
    """
    Wrap a managed response stream so its ``shinychat.response`` span stays
    active for the full consumption.

    ``Chat.append_message_stream()`` consumes streams in a background task,
    so a ``with response_span(...)`` block around the call site would close
    the span long before the stream finishes. Wrapping the generator instead
    opens the span when consumption begins (still before any model work —
    chatlas's ``stream_async()`` is lazy and does all provider I/O inside
    the generator) and closes it once the stream is exhausted or fails.

    ``conversation_id`` is captured as a scalar at submission time, so
    in-flight work is never relabeled by later history switches, new-chat
    actions, or client swaps.
    """
    if conversation_id is None:
        async for chunk in stream:
            yield chunk
        return
    with response_span(conversation_id):
        async for chunk in stream:
            yield chunk
