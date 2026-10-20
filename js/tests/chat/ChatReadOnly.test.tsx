/**
 * Read-only conversations (unavailable saved model context): the server sets
 * `active_read_only` on history_update; the client replaces the composer with
 * a status bar + New chat button, hides edit/retry (sibling nav unaffected),
 * guards the ordinary send path against same-tick forged submits, and
 * transfers focus between the composer and the bar.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import type { ChatAction } from "../../src/transport/types"
import { resetHistoryStoreRegistryForTests } from "../../src/chat/historyStore"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

// The fake is textarea-based, so jsdom focus assertions (activeElement) work
// against it, unlike ProseMirror's no-op focus.
vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

const READ_ONLY_COPY =
  "This conversation can be viewed but not continued. Its saved model context couldn't be loaded."

let chatSeq = 0

function renderChat(
  transport: ReturnType<typeof createMockTransport>,
  toolbarEl?: HTMLElement,
) {
  // Unique ids per render: history stores are keyed by elementId and outlive
  // a component across tests within this file.
  const elementId = `readonly-chat-${++chatSeq}`
  render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId={elementId}
      inputId={`${elementId}-input`}
      uploadAccept={[]}
      maxUploadSize={null}
      toolbarEl={toolbarEl}
    />,
  )
  return elementId
}

function fireHistoryUpdate(
  transport: ReturnType<typeof createMockTransport>,
  elementId: string,
  extra: Partial<Extract<ChatAction, { type: "history_update" }>> = {},
) {
  act(() => {
    transport.fire(elementId, {
      type: "history_update",
      enabled: true,
      conversations: [],
      active_id: "conv-1",
      ...extra,
    })
  })
}

beforeEach(() => {
  installShinyWindowStub()
})

afterEach(() => {
  resetHistoryStoreRegistryForTests()
})

describe("read-only composer bar", () => {
  it("replaces the chat input with a status bar and restores it when writable again", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    const editor = () => screen.queryByRole("textbox", { name: "Chat message" })
    expect(editor()).not.toBeNull()
    expect(screen.queryByRole("status")).toBeNull()

    fireHistoryUpdate(transport, elementId, { active_read_only: true })

    expect(editor()).toBeNull()
    const bar = screen.getByRole("status")
    expect(bar.textContent).toContain(READ_ONLY_COPY)
    const newChat = screen.getByRole("button", { name: "New chat" })
    expect(newChat).toBeInTheDocument()
    expect(bar).not.toContainElement(newChat)
    // The button is described by the bar text, so focused entry reads the
    // explanation even for AT that skips newly-mounted role=status content.
    const descriptionId = newChat.getAttribute("aria-describedby")
    expect(descriptionId).toBeTruthy()
    expect(document.getElementById(descriptionId!)?.textContent).toBe(
      READ_ONLY_COPY,
    )

    // Absent flag means writable (older servers never send it).
    fireHistoryUpdate(transport, elementId)
    expect(screen.queryByRole("status")).toBeNull()
    expect(editor()).not.toBeNull()
  })

  it("hides edit and retry but leaves sibling navigation usable", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    fireHistoryUpdate(transport, elementId, {
      transition_protocol: "completion-v2",
    })
    act(() => {
      transport.fire(elementId, {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hello", content_type: "markdown" }],
        },
      })
      transport.fire(elementId, {
        type: "update_siblings",
        data: { 0: { index: 0, total: 2 } },
      })
      transport.fire(elementId, {
        type: "update_exchange_metadata",
        data: {
          0: {
            status: "error",
            retryable: true,
            error_message: "The response stream could not be started.",
          },
        },
      })
    })

    expect(
      screen.getByRole("button", { name: "Edit message" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Retry message" }),
    ).toBeInTheDocument()

    fireHistoryUpdate(transport, elementId, {
      active_read_only: true,
      transition_protocol: "completion-v2",
    })

    expect(screen.queryByRole("button", { name: "Edit message" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Retry message" })).toBeNull()
    // readOnly is not folded into the shared message `disabled` prop:
    // sibling navigation stays available.
    expect(screen.getByRole("button", { name: "Next version" })).toBeEnabled()
    // Error text from the exchange metadata is display, not a control.
    expect(
      screen.getByText("The response stream could not be started."),
    ).toBeInTheDocument()
  })

  it("sends history-new from the bar and disables the button while the transition is pending", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    fireHistoryUpdate(transport, elementId, {
      active_read_only: true,
      transition_protocol: "completion-v2",
    })

    const newChat = screen.getByRole("button", { name: "New chat" })
    expect(newChat).toBeEnabled()
    fireEvent.click(newChat)

    expect(transport.sendHistoryNew).toHaveBeenCalledExactlyOnceWith(
      elementId,
      expect.any(String),
    )
    expect(newChat).toHaveAttribute("aria-disabled", "true")
    fireEvent.click(newChat)
    expect(transport.sendHistoryNew).toHaveBeenCalledTimes(1)
  })
})

describe("read-only focus transfer", () => {
  it("moves focus from the focused composer to the New chat button on entry", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    const editor = screen.getByRole("textbox", { name: "Chat message" })
    act(() => editor.focus())

    fireHistoryUpdate(transport, elementId, { active_read_only: true })

    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "New chat" }),
    )
  })

  it("does not steal focus from unrelated controls on entry", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    fireHistoryUpdate(transport, elementId)
    const trigger = screen.getByRole("button", {
      name: /conversation history/i,
    })
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    fireHistoryUpdate(transport, elementId, { active_read_only: true })

    expect(document.activeElement).toBe(trigger)
  })

  it("keeps New chat focus while app output is streaming and rejects busy clicks", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)
    fireHistoryUpdate(transport, elementId, { active_read_only: true })
    const newChat = screen.getByRole("button", { name: "New chat" })
    act(() => newChat.focus())

    act(() => {
      transport.fire(elementId, {
        type: "chunk_start",
        message: { role: "assistant", segments: [] },
      })
    })

    expect(newChat).toHaveAttribute("aria-disabled", "true")
    expect(newChat).not.toBeDisabled()
    expect(document.activeElement).toBe(newChat)
    fireEvent.click(newChat)
    expect(transport.sendHistoryNew).not.toHaveBeenCalled()

    act(() => transport.fire(elementId, { type: "chunk_end" }))
    expect(newChat).not.toHaveAttribute("aria-disabled")
    expect(document.activeElement).toBe(newChat)
  })

  it("does not steal focus from a toolbar control that remains mounted", () => {
    const transport = createMockTransport()
    const toolbar = document.createElement("div")
    const control = document.createElement("button")
    control.textContent = "Toolbar action"
    toolbar.append(control)
    const elementId = renderChat(transport, toolbar)
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    act(() => editor.focus())
    act(() => control.focus())
    expect(document.activeElement).toBe(control)

    fireHistoryUpdate(transport, elementId, { active_read_only: true })

    expect(control).toBeInTheDocument()
    expect(document.activeElement).toBe(control)
  })

  it("returns focus to a usable input after New chat clears the read-only state", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    const editor = screen.getByRole("textbox", { name: "Chat message" })
    act(() => editor.focus())
    fireHistoryUpdate(transport, elementId, { active_read_only: true })
    const newChat = screen.getByRole("button", { name: "New chat" })
    expect(document.activeElement).toBe(newChat)

    fireEvent.click(newChat)
    expect(transport.sendHistoryNew).toHaveBeenCalled()

    // Server completes the New chat: writable again, input restored.
    fireHistoryUpdate(transport, elementId, { active_id: null })

    const restored = screen.getByRole("textbox", { name: "Chat message" })
    expect(document.activeElement).toBe(restored)

    // And the restored input is actually usable.
    fireEvent.change(restored, { target: { value: "fresh start" } })
    fireEvent.keyDown(restored, { key: "Enter" })
    expect(transport.sendInput).toHaveBeenCalledWith(
      `${elementId}-input`,
      "fresh start",
    )
  })
})

describe("read-only send guards", () => {
  it("accepts an update_input submit while writable (control)", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    act(() => {
      transport.fire(elementId, {
        type: "update_input",
        value: "hello",
        submit: true,
      })
    })

    expect(transport.sendInput).toHaveBeenCalledWith(
      `${elementId}-input`,
      "hello",
    )
    expect(screen.getByText("hello")).toBeInTheDocument()
  })

  it("rejects a same-tick update_input submit after readOnly without rendering phantom input", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    act(() => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: "conv-1",
        active_read_only: true,
      })
      // Arrives before React unmounts the input: the store-level guard in
      // the send path must stop it even though the composer is still mounted.
      transport.fire(elementId, {
        type: "update_input",
        value: "forged",
        submit: true,
      })
    })

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.queryByText("forged")).toBeNull()
    expect(screen.getByRole("status").textContent).toContain(READ_ONLY_COPY)
  })

  it("does not send a submitting suggestion click while read-only", () => {
    const transport = createMockTransport()
    const elementId = renderChat(transport)

    act(() => {
      transport.fire(elementId, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "Try <span class='suggestion submit' data-suggestion='forged suggestion'>this</span>",
              content_type: "html",
            },
          ],
        },
      })
    })
    fireHistoryUpdate(transport, elementId, { active_read_only: true })

    fireEvent.click(document.querySelector(".suggestion")!)

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.queryByText("forged suggestion")).toBeNull()
  })
})
