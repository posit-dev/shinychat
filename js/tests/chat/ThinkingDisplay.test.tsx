import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ThinkingDisplay } from "../../src/chat/ThinkingDisplay"
import type { ThinkingBlock } from "../../src/chat/state"

function thinking(partial: Partial<ThinkingBlock> = {}): ThinkingBlock {
  return {
    type: "thinking",
    content: "Weighing the options",
    streaming: false,
    durationMs: 1200,
    ...partial,
  }
}

describe("ThinkingDisplay", () => {
  beforeEach(() => {
    // The label's fade animation reads prefers-reduced-motion.
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
  })

  it("reads as the same activity row as a tool call: leading glyph, trailing disclosure", () => {
    // A collapsed thinking header used to stand out sharply against the tool
    // rows around it — bigger, bolder, undimmed, and structurally mirrored (its
    // only chevron led the row). It now takes the tool-row shape: a static
    // identity glyph in the leading slot, the rotating chevron trailing.
    const { container } = render(
      <ThinkingDisplay thinking={thinking()} messageId="m1" />,
    )
    const header = container.querySelector(".shiny-chat-thinking-header")!
    const children = Array.from(header.children).map((el) =>
      el.getAttribute("class"),
    )
    expect(children[0]).toBe("shiny-chat-thinking-glyph")
    expect(children[children.length - 1]).toBe("shiny-chat-thinking-disclosure")
  })

  it("keeps the leading glyph static and rotates only the trailing chevron", () => {
    // The leading glyph is identity, not an affordance, so it carries no
    // expanded state to rotate on. Disclosure rotation is driven off the
    // header's aria-expanded, exactly as a tool row's is.
    const { container } = render(
      <ThinkingDisplay thinking={thinking()} messageId="m1" />,
    )
    const header = container.querySelector(".shiny-chat-thinking-header")!
    const glyph = container.querySelector(".shiny-chat-thinking-glyph")!
    expect(header.getAttribute("aria-expanded")).toBe("false")
    expect(glyph.hasAttribute("data-expanded")).toBe(false)

    fireEvent.click(header)
    expect(header.getAttribute("aria-expanded")).toBe("true")
    expect(glyph.hasAttribute("data-expanded")).toBe(false)
  })

  it("reports sub-second thinking as finished, not as still thinking", () => {
    // A short reasoning burst between two tool calls finalizes in well under a
    // second. It used to fall through to the in-progress "Thinking" label, so a
    // finished block was indistinguishable from a running one.
    const { container } = render(
      <ThinkingDisplay
        thinking={thinking({ durationMs: 170 })}
        messageId="m1"
      />,
    )
    expect(
      container.querySelector(".shiny-chat-thinking-label")?.textContent,
    ).toBe("Thought for less than a second")
  })

  it("still reports whole seconds for longer thinking", () => {
    const { container } = render(
      <ThinkingDisplay
        thinking={thinking({ durationMs: 1200 })}
        messageId="m1"
      />,
    )
    expect(
      container.querySelector(".shiny-chat-thinking-label")?.textContent,
    ).toBe("Thought for 1s")
  })

  it("falls back to 'Thinking' when no duration was recorded", () => {
    // `durationMs` is computed client-side and never serialized, so every
    // restored transcript lands here. Keeping the in-progress label is a
    // deliberate tradeoff, not an oversight — pinned so it isn't "fixed" into
    // copy that claims a duration we don't have.
    const { container } = render(
      <ThinkingDisplay
        thinking={thinking({ durationMs: undefined })}
        messageId="m1"
      />,
    )
    expect(
      container.querySelector(".shiny-chat-thinking-label")?.textContent,
    ).toBe("Thinking")
  })

  it("keeps the streaming dot beside the label, ahead of the disclosure", () => {
    const { container } = render(
      <ThinkingDisplay
        thinking={thinking({ streaming: true, durationMs: undefined })}
        messageId="m1"
      />,
    )
    const header = container.querySelector(".shiny-chat-thinking-header")!
    expect(
      Array.from(header.children).map((el) => el.getAttribute("class")),
    ).toEqual([
      "shiny-chat-thinking-glyph",
      "shiny-chat-thinking-label",
      "shiny-chat-thinking-dot",
      "shiny-chat-thinking-disclosure",
    ])
  })
})
