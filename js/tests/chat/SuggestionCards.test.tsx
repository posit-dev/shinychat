/**
 * Integration tests for suggestion card rendering, interaction, and roving tabindex.
 *
 * These tests mount ChatApp (the full component tree used in production) with
 * an assistant message containing a qualifying suggestion list, then assert
 * click, data-last-clicked, focus, and keyboard navigation behaviors that are
 * implemented in ChatContainer.
 */
import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

const SUGGESTION_HTML =
  "<ul>" +
  '<li><span class="suggestion" title="Foo">do thing</span></li>' +
  '<li><span class="suggestion" title="Bar">other thing</span></li>' +
  "</ul>"

/** Render ChatApp and push an assistant message containing the suggestion list. */
async function renderWithSuggestions(placeholder = "Type...") {
  const transport = createMockTransport()
  const shinyLifecycle = createMockShinyLifecycle()

  const result = render(
    <ChatApp
      transport={transport}
      shinyLifecycle={shinyLifecycle}
      elementId="test-chat"
      inputId="test-input"
      placeholder={placeholder}
    />,
  )

  await act(async () => {
    transport.fire("test-chat", {
      type: "message",
      message: {
        role: "assistant",
        segments: [{ content: SUGGESTION_HTML, content_type: "html" }],
      },
    })
  })

  return { ...result, transport }
}

beforeEach(() => {
  installShinyWindowStub()
})

describe("SuggestionCards: rendering", () => {
  it("renders the suggestion list container and two cards from HTML content", async () => {
    await renderWithSuggestions()

    expect(document.querySelector(".shiny-chat-suggestion-list")).not.toBeNull()

    const cards = document.querySelectorAll(".shiny-chat-suggestion-list-item")
    expect(cards.length).toBe(2)
  })

  it("plugin sets data-suggestion to body text (not title) for title-bearing spans", async () => {
    await renderWithSuggestions()

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )
    expect(cards[0]!.dataset.suggestion).toBe("do thing")
    expect(cards[1]!.dataset.suggestion).toBe("other thing")
  })
})

describe("SuggestionCards: click behavior", () => {
  it("clicking a card sets the textarea value to the body text, not title-prefixed text", async () => {
    await renderWithSuggestions("Type...")

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement
    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    await act(async () => {
      fireEvent.click(cards[1]!)
    })

    expect(textarea.value).toBe("other thing")
  })

  it("clicking the first card sets textarea to the first card's body text", async () => {
    await renderWithSuggestions("Type...")

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement
    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    await act(async () => {
      fireEvent.click(cards[0]!)
    })

    expect(textarea.value).toBe("do thing")
  })

  it("data-last-clicked moves from first card to second after clicking second", async () => {
    await renderWithSuggestions()

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    await act(async () => {
      fireEvent.click(cards[0]!)
    })

    expect(cards[0]!.hasAttribute("data-last-clicked")).toBe(true)
    expect(cards[1]!.hasAttribute("data-last-clicked")).toBe(false)

    await act(async () => {
      fireEvent.click(cards[1]!)
    })

    expect(cards[0]!.hasAttribute("data-last-clicked")).toBe(false)
    expect(cards[1]!.hasAttribute("data-last-clicked")).toBe(true)
  })
})

describe("SuggestionCards: aria-label matches visible text (#5 / test-d)", () => {
  it("ul titled cards have aria-label containing title and body", async () => {
    await renderWithSuggestions()

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    // SUGGESTION_HTML uses title="Foo" body="do thing" and title="Bar" body="other thing"
    expect(cards[0]!.getAttribute("aria-label")).toBe(
      "Use chat suggestion: Foo — do thing",
    )
    expect(cards[1]!.getAttribute("aria-label")).toBe(
      "Use chat suggestion: Bar — other thing",
    )
  })

  it("ol titled cards have aria-label with index prefix, title, and body", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    const OL_HTML =
      "<ol>" +
      '<li><span class="suggestion" title="Step One">do first</span></li>' +
      '<li><span class="suggestion" title="Step Two">do second</span></li>' +
      "</ol>"

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat-ol"
        inputId="test-input-ol"
        placeholder="Type..."
      />,
    )

    await act(async () => {
      transport.fire("test-chat-ol", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: OL_HTML, content_type: "html" }],
        },
      })
    })

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list--ordered .shiny-chat-suggestion-list-item",
    )

    expect(cards[0]!.getAttribute("aria-label")).toBe(
      "Use chat suggestion #1: Step One — do first",
    )
    expect(cards[1]!.getAttribute("aria-label")).toBe(
      "Use chat suggestion #2: Step Two — do second",
    )
  })
})

describe("SuggestionCards: roving tabindex", () => {
  it("focusing the first card gives it tabIndex=0 and sets siblings to tabIndex=-1", async () => {
    await renderWithSuggestions()

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    await act(async () => {
      fireEvent.focus(cards[0]!)
    })

    expect(cards[0]!.tabIndex).toBe(0)
    expect(cards[1]!.tabIndex).toBe(-1)
  })

  it("ArrowDown on the focused first card moves focus to the second card", async () => {
    await renderWithSuggestions()

    const cards = document.querySelectorAll<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )

    // Trigger roving setup by focusing the first card
    await act(async () => {
      fireEvent.focus(cards[0]!)
    })

    await act(async () => {
      fireEvent.keyDown(cards[0]!, { key: "ArrowDown" })
    })

    expect(cards[1]!.tabIndex).toBe(0)
    expect(cards[0]!.tabIndex).toBe(-1)
  })
})
