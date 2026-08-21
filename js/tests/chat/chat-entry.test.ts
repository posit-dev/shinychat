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
      <shiny-chat-artifact title="Preview" width="32rem" open resizable="false">
        <input value="Preserved artifact">
        <script data-artifact-dependency>window.__artifact = true</script>
      </shiny-chat-artifact>
    `
    const initialInput = host.querySelector(
      "shiny-chat-artifact input",
    ) as HTMLInputElement
    const initialDependency = host.querySelector(
      "shiny-chat-artifact script",
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
      expect(host.querySelector(".shiny-chat-artifact")).not.toBeNull()
    })

    const panel = host.querySelector(
      ".shiny-chat-artifact",
    ) as HTMLElement | null
    expect(panel).not.toBeNull()
    expect(panel?.hidden).toBe(false)
    expect(panel?.style.getPropertyValue("--shiny-chat-artifact-width")).toBe(
      "32rem",
    )
    expect(
      host.querySelector("#artifact-entry-artifact-title")?.textContent,
    ).toBe("Preview")
    expect(host.querySelector(".shiny-chat-artifact input")).toBe(initialInput)
    expect(host.querySelector(".shiny-chat-artifact script")).toBe(
      initialDependency,
    )
    expect(artifactWasPresentAtUnbind).toBe(true)
    expect(host.querySelector('[role="separator"]')).toBeNull()
  })

  it("routes preloaded tool calls through the content router (tool-grouping attr)", async () => {
    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "preloaded-tools")
    host.setAttribute("tool-grouping", "all")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content-type="markdown"
          content='<shiny-tool-result data-shinychat-react request-id="r1" tool-name="foo" status="success" value="done" value-type="text"></shiny-tool-result>'
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input placeholder="p"></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    // Preloaded tool HTML is routed into a tool_loop block and rendered as a
    // condensed tool group — a quiet Tier-1 row (the tool name in code font,
    // since this call has no title) that morphs into the leaf card on expand.
    await waitFor(() => {
      expect(host.querySelector(".shiny-chat-tool-group__row")).not.toBeNull()
      expect(
        host.querySelector(".shiny-chat-tool-group__toolname")?.textContent,
      ).toBe("foo")
    })

    const row = host.querySelector(".shiny-chat-tool-group__row") as HTMLElement
    await act(async () => {
      row.click()
    })

    expect(host.querySelector(".shiny-tool-card")).not.toBeNull()
    expect(host.textContent).toContain("done")
  })

  it("re-routes the existing transcript when tool-grouping changes", async () => {
    // `tool-grouping` is observed, so switching it regroups the conversation
    // already on screen instead of only future messages.
    const call = (id: string, name: string) =>
      `<shiny-tool-result data-shinychat-react request-id="${id}" tool-name="${name}" status="success" value="v" value-type="text"></shiny-tool-result>`

    const host = document.createElement("shiny-chat-container")
    host.setAttribute("id", "live-grouping")
    host.setAttribute("tool-grouping", "none")
    host.innerHTML = `
      <shiny-chat-messages>
        <shiny-chat-message
          data-role="assistant"
          content-type="markdown"
          content='${call("r1", "foo")}${call("r2", "foo")}'
        ></shiny-chat-message>
      </shiny-chat-messages>
      <shiny-chat-input placeholder="p"></shiny-chat-input>
    `

    await act(async () => {
      document.body.appendChild(host)
    })

    const rows = () => host.querySelectorAll(".shiny-chat-tool-group__row")
    await waitFor(() => expect(rows()).toHaveLength(2))

    await act(async () => {
      host.setAttribute("tool-grouping", "tool")
    })

    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(
      host.querySelector(".shiny-chat-tool-group__count")?.textContent,
    ).toBe("×2")
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
