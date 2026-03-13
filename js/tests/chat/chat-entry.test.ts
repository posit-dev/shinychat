import { describe, it, expect, beforeAll, beforeEach, afterEach } from "vitest"
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
          content-type="semi-markdown"
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
      expect(host.querySelector("textarea")).not.toBeNull()
    })

    const textarea = host.querySelector(
      "textarea",
    ) as HTMLTextAreaElement | null
    expect(textarea).toBeTruthy()
    expect(textarea?.id).toBe("server-input-id")
    expect(textarea?.placeholder).toBe("Server placeholder")

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
      expect(host.querySelector("textarea")).not.toBeNull()
    })

    const textarea = host.querySelector(
      "textarea",
    ) as HTMLTextAreaElement | null
    expect(textarea).toBeTruthy()
    expect(textarea?.id).toBe("fallback-chat_user_input")
    expect(textarea?.placeholder).toBe("Fallback placeholder")
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
      expect(host.querySelector("textarea")).not.toBeNull()
    })

    await act(async () => {
      expect(() => {
        host.remove()
      }).not.toThrow()
    })
  })
})
