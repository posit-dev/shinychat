from __future__ import annotations

import re
import time
from typing import Optional


class ThinkingAccumulator:
    """Extracts <topic>...</topic> tags from thinking content, handling chunk boundaries."""

    def __init__(self):
        self.buffer: str = ""
        self.current_topic: Optional[str] = None

    def process(self, text: str) -> tuple[str, Optional[str]]:
        """Process text, stripping topic tags. Returns (cleaned_text, new_topic_or_None)."""
        text = self.buffer + text
        self.buffer = ""

        topic: Optional[str] = None

        # Strip complete <topic>...</topic> tags
        while True:
            m = re.search(r"<topic>(.*?)</topic>", text)
            if not m:
                break
            topic = m.group(1)
            text = text[: m.start()] + text[m.end() :]

        # Buffer partial opening tags at end of text
        partial = re.search(r"<t(?:o(?:p(?:i(?:c(?:>[^<]*)?)?)?)?)?\s*$", text)
        if partial and partial.group():
            self.buffer = partial.group()
            text = text[: partial.start()]

        if topic is not None:
            self.current_topic = topic

        return text, topic


class ThinkingState:
    """Tracks thinking state during a stream."""

    def __init__(self):
        self.active: bool = False
        self.start_time: Optional[float] = None
        self.accumulator: ThinkingAccumulator = ThinkingAccumulator()

    def start(self) -> None:
        self.active = True
        self.start_time = time.monotonic()

    def end(self) -> int:
        """End thinking and return duration_ms."""
        if self.start_time is not None:
            duration_ms = round((time.monotonic() - self.start_time) * 1000)
        else:
            duration_ms = 0
        self.active = False
        self.start_time = None
        self.accumulator = ThinkingAccumulator()
        return duration_ms
