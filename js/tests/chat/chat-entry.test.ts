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
    // ChatContainerElement defers React unmount to distinguish removal from a
    // DOM move, then Tiptap defers Editor.destroy() by another timer tick.
    // Keep jsdom alive until both teardown stages have completed.
    await new Promise((resolve) => setTimeout(resolve, 5))
  })
})

describe("chat-entry custom element boot", () => {
  it("honors a live show-history preference from server markup", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "history-entry")
    host.setAttribute("show-history", "false")
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
    expect(host.querySelector(".shiny-chat-history-trigger")).toBeNull()

    await act(async () => {
      host.removeAttribute("show-history")
    })

    // History starts disabled until the server publishes its first snapshot,
    // but the live attribute update must retain a mounted chat without error.
    expect(host.querySelector('[role="textbox"]')).not.toBeNull()
  })

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

  it("seeds and preserves an initial artifact from server markup", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "artifact-entry")
    host.innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
      <shiny-chat-drawer title="Preview" width="32rem" open resizable="false">
        <input value="Preserved artifact">
        <script data-drawer-dependency>window.__artifact = true</script>
      </shiny-chat-drawer>
    `
    const initialInput = host.querySelector(
      "shiny-chat-drawer input",
    ) as HTMLInputElement
    const initialDependency = host.querySelector(
      "shiny-chat-drawer script",
    ) as HTMLScriptElement
    let artifactWasPresentAtUnbind = false
    const unbindAll = window.Shiny!.unbindAll as ReturnType<typeof vi.fn>
    unbindAll.mockImplementation((element: HTMLElement) => {
      if (element === host) {
        artifactWasPresentAtUnbind = element.contains(initialInput)
      }
    })

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector(".shiny-chat-drawer")).not.toBeNull()
    })

    const panel = host.querySelector(".shiny-chat-drawer") as HTMLElement | null
    expect(panel).not.toBeNull()
    expect(panel?.hidden).toBe(false)
    expect(panel?.style.getPropertyValue("--_drawer-width")).toBe("32rem")
    expect(
      host.querySelector("#artifact-entry-drawer-title")?.textContent,
    ).toBe("Preview")
    expect(host.querySelector(".shiny-chat-drawer input")).toBe(initialInput)
    expect(host.querySelector(".shiny-chat-drawer script")).toBe(
      initialDependency,
    )
    expect(artifactWasPresentAtUnbind).toBe(true)
    expect(host.querySelector('[role="separator"]')).toBeNull()
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

  it("parses attachment-accept and max-attachment-size attributes", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "upload-attr-chat")
    host.setAttribute("allow-attachments", "true")
    host.setAttribute("attachment-accept", "application/pdf")
    host.setAttribute("max-attachment-size", "1234")
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

    // The parsed attachment-accept attribute feeds the file input's accept attr.
    const fileInput = host.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null
    expect(fileInput).not.toBeNull()
    expect(fileInput?.accept).toBe("application/pdf")
  })

  it("does not render a derived aside favicon when aside-favicon is false", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "aside-favicon-off")
    host.setAttribute("aside-favicon", "false")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content='A claim<shiny-aside label="Source" url="https://source.example"></shiny-aside>.'
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector(".shiny-aside-pill")).not.toBeNull()
    })

    expect(host.querySelector(".shiny-aside-pill img")).toBeNull()
    expect(host.innerHTML).not.toContain("icons.duckduckgo.com")
  })

  it("keeps an explicit aside icon when aside-favicon is false", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "aside-explicit-icon")
    host.setAttribute("aside-favicon", "false")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content='A claim<shiny-aside label="Source" url="https://source.example" icon="https://assets.example/source.svg"></shiny-aside>.'
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector(".shiny-aside-pill img")).not.toBeNull()
    })

    expect(
      host.querySelector(".shiny-aside-pill img")?.getAttribute("src"),
    ).toBe("https://assets.example/source.svg")
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

describe("data-initial-messages attribute", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function bootContainer(
    id: string,
    attrValue: string | null,
    innerHTML = `
      <shiny-chat-messages></shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `,
    extraAttrs: Record<string, string> = {},
  ) {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", id)
    if (attrValue !== null) {
      host.setAttribute("data-initial-messages", attrValue)
    }
    for (const [name, value] of Object.entries(extraAttrs)) {
      host.setAttribute(name, value)
    }
    host.innerHTML = innerHTML

    await act(async () => {
      document.body.appendChild(host)
    })

    await waitFor(() => {
      expect(host.querySelector('[role="textbox"]')).not.toBeNull()
    })
    return host
  }

  it("replays structured blocks into rendered messages, preserving segment order", async () => {
    const entries = [
      {
        role: "assistant",
        segments: [
          { content: "Before the call. ", content_type: "markdown" },
          {
            type: "tool_request",
            version: 1,
            request_id: "call-1",
            tool_name: "get_weather",
            title: "Looking up weather",
            intent: "check weather",
            arguments: '{"location":"Duluth"}',
          },
          {
            type: "tool_result",
            version: 1,
            request_id: "call-1",
            tool_name: "get_weather",
            status: "success",
            value: "72F and sunny",
            value_type: "text",
            title: "Looked up weather",
            expanded: true,
          },
          { content: " After the call.", content_type: "markdown" },
          {
            type: "html_block",
            version: 1,
            content: "<p class='island'>Island HTML</p>",
          },
        ],
      },
    ]

    const host = await bootContainer(
      "attr-blocks-chat",
      JSON.stringify(entries),
    )

    expect(host.querySelector(".shiny-chat-tool-group")).not.toBeNull()
    expect(host.querySelector(".shiny-tool-card")).not.toBeNull()
    expect(host.textContent).toContain("72F and sunny")

    const island = host.querySelector(".island")
    expect(island).not.toBeNull()
    expect(island!.innerHTML).toBe("Island HTML")

    const text = host.textContent ?? ""
    expect(text.indexOf("Before the call.")).toBeLessThan(
      text.indexOf("72F and sunny"),
    )
    expect(text.indexOf("72F and sunny")).toBeLessThan(
      text.indexOf("After the call."),
    )
    expect(text.indexOf("After the call.")).toBeLessThan(
      text.indexOf("Island HTML"),
    )
  })

  it("honors the container tool-grouping attribute for embedded blocks", async () => {
    const makeEntries = () => [
      {
        role: "assistant",
        segments: [
          {
            type: "tool_result",
            version: 1,
            request_id: "call-1",
            tool_name: "get_weather",
            status: "success",
            value: "72F and sunny",
            value_type: "text",
          },
          {
            type: "tool_result",
            version: 1,
            request_id: "call-2",
            tool_name: "get_time",
            status: "success",
            value: "noon",
            value_type: "text",
          },
        ],
      },
    ]

    const grouped = await bootContainer(
      "attr-grouping-default",
      JSON.stringify(makeEntries()),
    )
    expect(grouped.querySelectorAll(".shiny-chat-tool-group")).toHaveLength(2)

    const all = await bootContainer(
      "attr-grouping-all",
      JSON.stringify(makeEntries()),
      undefined,
      { "tool-grouping": "all" },
    )
    expect(all.querySelectorAll(".shiny-chat-tool-group")).toHaveLength(1)
  })

  it("ignores non-html_block structured blocks in user-role entries but keeps html_block", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const entries = [
      {
        role: "user",
        segments: [
          { content: "User says hi", content_type: "markdown" },
          {
            type: "tool_result",
            version: 1,
            request_id: "r1",
            tool_name: "my_tool",
            status: "success",
            value: "42",
          },
          {
            type: "html_block",
            version: 1,
            content: "<p class='island'>User island</p>",
          },
        ],
      },
    ]

    const host = await bootContainer(
      "attr-user-gate-chat",
      JSON.stringify(entries),
    )

    expect(warn).toHaveBeenCalledWith(
      "Ignoring non-html_block structured block in a user-role message",
    )
    expect(host.querySelector(".shiny-chat-tool-group")).toBeNull()
    expect(host.querySelector(".shiny-tool-card")).toBeNull()
    expect(host.textContent).toContain("User says hi")
    const island = host.querySelector(".island")
    expect(island).not.toBeNull()
    expect(island!.innerHTML).toBe("User island")
  })

  it("warns and skips a block with an unsupported version but keeps the message", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const entries = [
      {
        role: "assistant",
        segments: [
          { content: "just text", content_type: "markdown" },
          {
            type: "html_block",
            version: 2,
            content: "<p class='island'>Future island</p>",
          },
        ],
      },
    ]

    const host = await bootContainer(
      "attr-version-chat",
      JSON.stringify(entries),
    )

    expect(warn).toHaveBeenCalledWith(
      "Ignoring html_block block with unsupported version: 2",
    )
    expect(host.textContent).toContain("just text")
    expect(host.querySelector(".island")).toBeNull()
  })

  it("warns and falls back to static tags when the attribute is malformed JSON", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    const host = await bootContainer(
      "attr-malformed-chat",
      "not json {",
      `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content="Static fallback"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `,
    )

    expect(warn).toHaveBeenCalledWith(
      "Ignoring malformed data-initial-messages attribute: not valid JSON",
    )
    expect(host.textContent).toContain("Static fallback")
  })

  it("warns and falls back to static tags when the attribute is not an array", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    const host = await bootContainer(
      "attr-nonarray-chat",
      '{"role":"assistant","segments":[]}',
      `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content="Static fallback"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `,
    )

    expect(warn).toHaveBeenCalledWith(
      "Ignoring malformed data-initial-messages attribute: expected a JSON array",
    )
    expect(host.textContent).toContain("Static fallback")
  })

  it("warns and skips malformed entries but keeps the surviving messages", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const entries = [
      "oops",
      { role: "assistant" },
      {
        role: "assistant",
        segments: [{ content: "Good message", content_type: "markdown" }],
      },
    ]

    const host = await bootContainer(
      "attr-bad-entry-chat",
      JSON.stringify(entries),
    )

    expect(warn).toHaveBeenCalledTimes(2)
    expect(warn).toHaveBeenCalledWith(
      "Skipping malformed entry in data-initial-messages: expected an object with a segments array",
    )
    expect(host.textContent).toContain("Good message")
  })

  it("uses the static-tag path unchanged when the attribute is absent", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    const host = await bootContainer(
      "attr-absent-chat",
      null,
      `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content-type="markdown"
          content="Static only"
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input></shiny-chat-input>
    `,
    )

    expect(host.textContent).toContain("Static only")
    expect(warn).not.toHaveBeenCalled()
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
