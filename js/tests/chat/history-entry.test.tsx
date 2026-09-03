import { afterEach, beforeAll, describe, expect, it } from "vitest"
import { act, fireEvent, waitFor, within } from "@testing-library/react"
import type { ConversationMeta } from "../../src/transport/types"
import {
  acquireHistoryStore,
  getHistoryStore,
  resetHistoryStoreRegistryForTests,
} from "../../src/chat/historyStore"
import { createMockTransport } from "../helpers/mocks"

const conversations: ConversationMeta[] = [
  {
    id: "first",
    title: "First conversation",
    created_at: "2026-08-18T09:00:00.000Z",
    updated_at: "2026-08-18T10:00:00.000Z",
  },
  {
    id: "second",
    title: "Second conversation",
    created_at: "2026-08-17T09:00:00.000Z",
    updated_at: "2026-08-17T10:00:00.000Z",
  },
]

beforeAll(async () => {
  await import("../../src/chat/history-entry")
})

afterEach(async () => {
  await act(async () => {
    document.body.replaceChildren()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  resetHistoryStoreRegistryForTests()
})

async function appendHistory(forId: string | null): Promise<HTMLElement> {
  const host = document.createElement("shiny-chat-history")
  if (forId !== null) host.setAttribute("for", forId)
  await act(async () => {
    document.body.appendChild(host)
  })
  return host
}

function historyItemButton(
  host: HTMLElement,
  title: string,
): HTMLButtonElement {
  const titleEl = Array.from(
    host.querySelectorAll(".shiny-chat-history-item-title"),
  ).find((element) => element.textContent === title)
  return titleEl?.closest(
    ".shiny-chat-history-item-select",
  ) as HTMLButtonElement
}

function menuFor(host: HTMLElement, title: string): HTMLElement {
  const titleEl = Array.from(
    host.querySelectorAll(".shiny-chat-history-item-title"),
  ).find((element) => element.textContent === title)
  const item = titleEl?.closest(".shiny-chat-history-item") as HTMLElement
  const menu = item.querySelector(".shiny-chat-history-itemmenu") as HTMLElement
  fireEvent.click(
    within(menu).getByRole("button", { name: /conversation actions/i }),
  )
  return document.querySelector(".shiny-chat-history-menu") as HTMLElement
}

describe("shiny-chat-history custom element", () => {
  it("replays existing history to late and multiple mounts", async () => {
    const first = await appendHistory("chat")
    expect(first.childElementCount).toBe(0)

    const transport = createMockTransport()
    await act(async () => {
      const registration = acquireHistoryStore("chat", transport)
      registration.store.updateHistory({
        enabled: true,
        conversations,
        activeId: "first",
      })
    })

    await waitFor(() => {
      expect(within(first).getByText("First conversation")).toBeTruthy()
    })
    expect(
      within(first).getByRole("region", { name: /conversation history/i }),
    ).toBeTruthy()

    const second = await appendHistory("chat")
    await waitFor(() => {
      expect(within(second).getByText("Second conversation")).toBeTruthy()
    })

    fireEvent.change(
      within(first).getByRole("textbox", { name: /search conversations/i }),
      { target: { value: "first" } },
    )
    expect(within(first).queryByText("Second conversation")).toBeNull()
    expect(within(second).getByText("Second conversation")).toBeTruthy()
  })

  it("retargets for to the new store without retaining the old subscription", async () => {
    const firstTransport = createMockTransport()
    const secondTransport = createMockTransport()
    const firstRegistration = acquireHistoryStore("first-chat", firstTransport)
    const secondRegistration = acquireHistoryStore(
      "second-chat",
      secondTransport,
    )
    firstRegistration.store.updateHistory({
      enabled: true,
      conversations: [{ ...conversations[0]!, id: "first", title: "First" }],
      activeId: null,
    })
    secondRegistration.store.updateHistory({
      enabled: true,
      conversations: [{ ...conversations[1]!, id: "second", title: "Second" }],
      activeId: null,
    })
    const host = await appendHistory("first-chat")

    await waitFor(() => {
      expect(within(host).getByText("First")).toBeTruthy()
    })
    expect(firstRegistration.store.listenerCount).toBe(1)
    expect(secondRegistration.store.listenerCount).toBe(0)

    await act(async () => {
      host.setAttribute("for", "second-chat")
    })
    await waitFor(() => {
      expect(within(host).getByText("Second")).toBeTruthy()
    })
    expect(firstRegistration.store.listenerCount).toBe(0)
    expect(secondRegistration.store.listenerCount).toBe(1)

    fireEvent.click(
      within(host).getByRole("button", { name: /new conversation/i }),
    )
    expect(firstTransport.sendHistoryNew).not.toHaveBeenCalled()
    expect(secondTransport.sendHistoryNew).toHaveBeenCalledWith("second-chat")
  })

  it("routes inline selection, new, rename, and delete actions through the store", async () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: null,
    })
    const host = await appendHistory("chat")

    await waitFor(() => {
      expect(within(host).getByText("First conversation")).toBeTruthy()
    })

    fireEvent.click(historyItemButton(host, "First conversation"))
    fireEvent.click(
      within(host).getByRole("button", { name: /new conversation/i }),
    )
    expect(transport.sendHistorySelect).toHaveBeenCalledWith("chat", "first")
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("chat")

    const menu = menuFor(host, "First conversation")
    fireEvent.click(within(menu).getByText("Rename"))
    const rename = within(host).getByRole("textbox", {
      name: /rename conversation/i,
    })
    fireEvent.change(rename, { target: { value: "Renamed" } })
    fireEvent.keyDown(rename, { key: "Enter" })
    expect(transport.sendHistoryRename).toHaveBeenCalledWith(
      "chat",
      "first",
      "Renamed",
    )

    const deleteMenu = menuFor(host, "First conversation")
    fireEvent.click(within(deleteMenu).getByText("Delete"))
    fireEvent.click(
      within(host).getByRole("button", { name: /confirm delete/i }),
    )
    expect(transport.sendHistoryDelete).toHaveBeenCalledWith("chat", "first")
  })

  it("disables every history action during a pending edit transition", async () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v2",
    })
    const host = await appendHistory("chat")

    await waitFor(() => {
      expect(within(host).getByText("First conversation")).toBeTruthy()
    })

    const menu = menuFor(host, "First conversation")
    await act(async () => {
      expect(registration.store.beginEditTransition()).not.toBeNull()
    })

    await waitFor(() => {
      expect(
        within(host).getByRole("button", { name: /new conversation/i }),
      ).toHaveProperty("disabled", true)
      expect(historyItemButton(host, "First conversation")).toHaveProperty(
        "disabled",
        true,
      )
      expect(
        within(menu).getByRole("button", { name: "Rename" }),
      ).toHaveProperty("disabled", true)
      expect(
        within(menu).getByRole("button", { name: "Delete" }),
      ).toHaveProperty("disabled", true)
    })
  })

  it("disables unsafe actions while busy or disconnected", async () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: null,
    })
    const host = await appendHistory("chat")

    await waitFor(() => {
      expect(
        within(host).getByRole("button", { name: /new conversation/i }),
      ).toBeTruthy()
    })

    await act(async () => {
      registration.store.setBusy(true)
    })
    await waitFor(() => {
      expect(
        within(host).getByRole("button", { name: /new conversation/i }),
      ).toHaveProperty("disabled", true)
    })

    await act(async () => {
      registration.store.setBusy(false)
      registration.release()
    })
    await waitFor(() => {
      expect(
        within(host).getByRole("button", { name: /new conversation/i }),
      ).toHaveProperty("disabled", true)
    })
    expect(
      within(host).getAllByRole("button", { name: /conversation actions/i })[0],
    ).toHaveProperty("disabled", true)

    expect(() => {
      getHistoryStore("chat").actions.rename("first", "Ignored")
    }).not.toThrow()
    expect(transport.sendHistoryRename).not.toHaveBeenCalled()
  })

  it("keeps its root through DOM moves and unsubscribes after genuine removal", async () => {
    const store = getHistoryStore("chat")
    store.updateHistory({ enabled: true, conversations, activeId: null })
    const left = document.createElement("div")
    const right = document.createElement("div")
    document.body.append(left, right)

    const host = document.createElement("shiny-chat-history")
    host.setAttribute("for", "chat")
    await act(async () => {
      left.appendChild(host)
    })
    await waitFor(() => {
      expect(within(host).getByText("First conversation")).toBeTruthy()
    })
    const rootBefore = host.querySelector(".shiny-chat-history-inline")

    await act(async () => {
      right.appendChild(host)
    })
    expect(host.querySelector(".shiny-chat-history-inline")).toBe(rootBefore)
    expect(host.querySelectorAll(".shiny-chat-history-inline")).toHaveLength(1)
    expect(store.listenerCount).toBe(1)

    await act(async () => {
      host.remove()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(store.listenerCount).toBe(0)
  })

  it("stays empty and marked invalid without a nonblank for target", async () => {
    const missing = await appendHistory(null)
    const blank = await appendHistory("   ")

    await act(async () => {
      await Promise.resolve()
    })
    expect(missing.dataset.historyError).toBe("missing-for")
    expect(blank.dataset.historyError).toBe("missing-for")
    expect(missing.childElementCount).toBe(0)
    expect(blank.childElementCount).toBe(0)
  })
})
