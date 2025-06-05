import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import {
  ShinyMarkdownStreamOutput,
  handleShinyMarkdownStreamMessage,
} from "../ShinyMarkdownStream"

// Mock the utils
vi.mock("../utils/_utils", () => ({
  renderDependencies: vi.fn().mockResolvedValue(undefined),
  showShinyClientMessage: vi.fn(),
}))

// Mock window.Shiny
const mockShiny = {
  addCustomMessageHandler: vi.fn(),
  setInputValue: vi.fn(),
}

describe("ShinyMarkdownStreamOutput", () => {
  let container: HTMLDivElement
  let element: ShinyMarkdownStreamOutput

  beforeEach(() => {
    // Set up global mocks using vitest's stubGlobal
    vi.stubGlobal("Shiny", mockShiny)

    // Mock customElements
    vi.stubGlobal("customElements", {
      define: vi.fn(),
      get: vi.fn().mockReturnValue(ShinyMarkdownStreamOutput),
    })

    // Create test container
    container = document.createElement("div")
    document.body.appendChild(container)

    // Create element
    element = new ShinyMarkdownStreamOutput()
    element.id = "test-element"
    container.appendChild(element)
  })

  afterEach(() => {
    document.body.removeChild(container)
    vi.clearAllMocks()
    vi.unstubAllGlobals() // Clean up global stubs
  })

  it("should initialize with default values", () => {
    expect(element).toBeInstanceOf(ShinyMarkdownStreamOutput)
  })

  it("should read initial attributes", () => {
    element.setAttribute("content", "Test content")
    element.setAttribute("content-type", "markdown")
    element.setAttribute("streaming", "")
    element.setAttribute("auto-scroll", "")

    // Trigger connectedCallback manually
    element.connectedCallback()

    // Check if attributes are read correctly
    // Note: We can't easily test private properties, but we can test behavior
    expect(element.getAttribute("content")).toBe("Test content")
    expect(element.getAttribute("content-type")).toBe("markdown")
    expect(element.hasAttribute("streaming")).toBe(true)
    expect(element.hasAttribute("auto-scroll")).toBe(true)
  })

  it("should update content correctly", () => {
    element.connectedCallback()

    element.updateContent("New content", "replace")
    expect(element.getAttribute("content")).toBe("New content")

    element.updateContent(" Additional", "append")
    expect(element.getAttribute("content")).toBe("New content Additional")
  })

  it("should set streaming state", () => {
    element.connectedCallback()

    element.setStreaming(true)
    expect(element.hasAttribute("streaming")).toBe(true)

    element.setStreaming(false)
    expect(element.hasAttribute("streaming")).toBe(false)
  })

  it("should set content type", () => {
    element.connectedCallback()

    element.setContentType("html")
    expect(element.getAttribute("content-type")).toBe("html")

    element.setContentType("text")
    expect(element.getAttribute("content-type")).toBe("text")
  })

  it("should set auto scroll", () => {
    element.connectedCallback()

    element.setAutoScroll(true)
    expect(element.hasAttribute("auto-scroll")).toBe(true)

    element.setAutoScroll(false)
    expect(element.hasAttribute("auto-scroll")).toBe(false)
  })

  it("should dispatch custom events", () => {
    element.connectedCallback()

    const contentChangeSpy = vi.fn()
    const streamEndSpy = vi.fn()

    element.addEventListener("contentchange", contentChangeSpy)
    element.addEventListener("streamend", streamEndSpy)

    // Trigger the callbacks (they're called by the React component)
    element.handleContentChange()
    element.handleStreamEnd()

    expect(contentChangeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "contentchange",
        detail: { content: expect.any(String) },
      }),
    )
    expect(streamEndSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "streamend",
      }),
    )
  })
})

describe("handleShinyMarkdownStreamMessage", () => {
  let container: HTMLDivElement
  let element: ShinyMarkdownStreamOutput

  beforeEach(() => {
    // Set up global mocks using vitest's stubGlobal
    vi.stubGlobal("Shiny", mockShiny)

    // Mock customElements
    vi.stubGlobal("customElements", {
      define: vi.fn(),
      get: vi.fn().mockReturnValue(ShinyMarkdownStreamOutput),
    })

    // Create test container
    container = document.createElement("div")
    document.body.appendChild(container)

    // Create element
    element = new ShinyMarkdownStreamOutput()
    element.id = "test-element"
    container.appendChild(element)
    element.connectedCallback()
  })

  afterEach(() => {
    document.body.removeChild(container)
    vi.clearAllMocks()
    vi.unstubAllGlobals() // Clean up global stubs
  })

  it("should handle content messages", async () => {
    const message = {
      id: "test-element",
      content: "Test message content",
      operation: "replace" as const,
    }

    await handleShinyMarkdownStreamMessage(message)

    expect(element.getAttribute("content")).toBe("Test message content")
  })

  it("should handle streaming messages", async () => {
    const message = {
      id: "test-element",
      isStreaming: true,
    }

    await handleShinyMarkdownStreamMessage(message)

    expect(element.hasAttribute("streaming")).toBe(true)
  })

  it("should handle append operations", async () => {
    // First set some initial content
    element.updateContent("Initial content", "replace")

    const message = {
      id: "test-element",
      content: " appended content",
      operation: "append" as const,
    }

    await handleShinyMarkdownStreamMessage(message)

    expect(element.getAttribute("content")).toBe(
      "Initial content appended content",
    )
  })

  it("should handle missing element gracefully", async () => {
    const showShinyClientMessage = await import("../../utils/_utils").then(
      (m) => m.showShinyClientMessage,
    )

    const message = {
      id: "non-existent-element",
      content: "Test content",
      operation: "replace" as const,
    }

    await handleShinyMarkdownStreamMessage(message)

    expect(showShinyClientMessage).toHaveBeenCalledWith({
      status: "error",
      message: expect.stringContaining("non-existent-element"),
    })
  })
})
