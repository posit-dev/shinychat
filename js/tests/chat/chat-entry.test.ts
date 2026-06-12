import {
  describe,
  it,
  expect,
  beforeAll,
  beforeEach,
  afterEach,
  vi,
} from "vitest"
import { act, waitFor } from "@testing-library/react"
import { installShinyWindowStub } from "../helpers/mocks"

beforeAll(async () => {
  installShinyWindowStub()
  await import("../../src/chat/chat-entry")
})

beforeEach(() => {
  installShinyWindowStub()
})

afterEach(async () => {
  await act(async () => {
    document.body.replaceChildren()
  })
})

describe("chat-entry custom element boot", () => {
  it("boots from server-rendered HTML using child input attributes and initial messages", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "chat-entry-test")
    host.setAttribute(
      "icon-assistant",
      '<span class="assistant-icon">assistant</span>',
    )
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content-type="markdown"
          content="Hello from the server"
        ></shiny-chat-message>
        <shiny-chat-message
          data-role="user"
          content-type="markdown"
          content="User reply"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input
        id="server-input-id"
        placeholder="Server placeholder"
      ></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })

    const editorWrapper = host.querySelector(
      "#server-input-id",
    ) as HTMLElement | null
    expect(editorWrapper).toBeTruthy()
    expect(editorWrapper?.id).toBe("server-input-id")
    const emptyParagraph = host.querySelector('[role="textbox"]')
    expect(emptyParagraph?.getAttribute("data-placeholder")).toBe(
      "Server placeholder",
    )

    expect(host.textContent).toContain("Hello from the server")
    expect(host.textContent).toContain("User reply")
    expect(host.querySelector(".assistant-icon")).not.toBeNull()

    expect(window.Shiny?.unbindAll).toHaveBeenCalledWith(host)
  })

  it("falls back to the conventional input id when no child input id is provided", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "fallback-chat")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content="Hello"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input placeholder="Fallback placeholder"></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })

    const editorWrapper = host.querySelector(
      "#fallback-chat_user_input",
    ) as HTMLElement | null
    expect(editorWrapper).toBeTruthy()
    expect(editorWrapper?.id).toBe("fallback-chat_user_input")
    const emptyParagraph = host.querySelector('[role="textbox"]')
    expect(emptyParagraph?.getAttribute("data-placeholder")).toBe(
      "Fallback placeholder",
    )
  })

  it("unmounts cleanly when disconnected", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "disconnect-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })

    await act(async () => {
      expect(() => {
        host.remove()
      }).not.toThrow()
    })
  })

  it("tears down when genuinely removed (not moved)", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "remove-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })

    const unbindAll = window.Shiny!.unbindAll as ReturnType<typeof vi.fn>
    const callsForHost = () =>
      unbindAll.mock.calls.filter((args) => args[0] === host).length
    const before = callsForHost()

    await act(async () => {
      host.remove()
      // Let the deferred teardown timer fire (no reconnect cancels it).
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(callsForHost()).toBeGreaterThan(before)
  })

  it("preserves the rendered conversation when moved to another container", async () => {
    const left = document.createElement("div")
    const right = document.createElement("div")
    document.body.append(left, right)

    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "move-chat")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content-type="markdown"
          content="Hello from the server"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input id="move-input"></shiny-chat-input>
    `

    await act(async () => {
      left.appendChild(host)
    })

    await waitFor(() => {
      expect(host.textContent).toContain("Hello from the server")
    })

    // Capture the rendered message element so we can prove it survives the
    // move intact rather than being torn down and rebuilt from scratch.
    const messageBefore = host.querySelector(".shiny-chat-message")
    expect(messageBefore).not.toBeNull()

    // Simulate the move: appendTo another container triggers
    // disconnectedCallback -> connectedCallback.
    await act(async () => {
      right.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })

    expect(host.textContent).toContain("Hello from the server")
    // Same DOM node => React state (including any streamed messages) preserved.
    expect(host.querySelector(".shiny-chat-message")).toBe(messageBefore)
  })
})

describe("current conversation id delivery", () => {
  it("sends stored current conversation id alongside browser token", async () => {
    localStorage.setItem("shinychat-current:current-id-chat", "conv-xyz")

    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "current-id-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await act(async () => {
      await Promise.resolve()
    })

    const setInputValue = window.Shiny!.setInputValue as ReturnType<
      typeof vi.fn
    >
    const currentIdCall = setInputValue.mock.calls.find((args) =>
      String(args[0]).endsWith("_history_current_id"),
    )
    expect(currentIdCall).toBeDefined()
    expect(currentIdCall![1]).toBe("conv-xyz")
  })

  it("sends empty string when no current conversation id is stored", async () => {
    localStorage.removeItem("shinychat-current:no-current-chat")

    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "no-current-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await act(async () => {
      await Promise.resolve()
    })

    const setInputValue = window.Shiny!.setInputValue as ReturnType<
      typeof vi.fn
    >
    const currentIdCall = setInputValue.mock.calls.find((args) =>
      String(args[0]).endsWith("_history_current_id"),
    )
    expect(currentIdCall).toBeDefined()
    expect(currentIdCall![1]).toBe("")
  })
})

describe("browser token delivery", () => {
  it("sends browser token immediately when Shiny is already initialized", async () => {
    // Default stub has initializedPromise pre-resolved.
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "token-ready-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    // Flush microtasks so the .then() callback has run.
    await act(async () => {
      await Promise.resolve()
    })

    const setInputValue = window.Shiny!.setInputValue as ReturnType<
      typeof vi.fn
    >
    const tokenCall = setInputValue.mock.calls.find((args) =>
      String(args[0]).endsWith("_history_browser_token"),
    )
    expect(tokenCall).toBeDefined()
    expect(typeof tokenCall![1]).toBe("string")
    expect((tokenCall![1] as string).length).toBeGreaterThan(0)
  })

  it("defers browser token until Shiny initializes on page load", async () => {
    // Install a stub whose initializedPromise starts unresolved.
    const { resolveShinyInit } = installShinyWindowStub({
      initializedPromiseResolved: false,
    })

    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "token-deferred-chat")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    // Flush microtasks — promise is still pending, so no token yet.
    await act(async () => {
      await Promise.resolve()
    })

    const setInputValue = window.Shiny!.setInputValue as ReturnType<
      typeof vi.fn
    >
    const tokenCallsBefore = setInputValue.mock.calls.filter((args) =>
      String(args[0]).endsWith("_history_browser_token"),
    )
    expect(tokenCallsBefore).toHaveLength(0)

    // Simulate Shiny finishing initialization.
    await act(async () => {
      resolveShinyInit()
      await Promise.resolve()
    })

    const tokenCallsAfter = setInputValue.mock.calls.filter((args) =>
      String(args[0]).endsWith("_history_browser_token"),
    )
    expect(tokenCallsAfter).toHaveLength(1)
    expect(typeof tokenCallsAfter[0]![1]).toBe("string")
  })
})
