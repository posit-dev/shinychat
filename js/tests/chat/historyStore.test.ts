import { afterEach, describe, expect, it, vi } from "vitest"
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
]

afterEach(() => {
  resetHistoryStoreRegistryForTests()
})

describe("historyStore", () => {
  it("replays the latest snapshot to late readers", () => {
    const registration = acquireHistoryStore("chat", createMockTransport())
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })
    registration.store.setBusy(true)

    const lateStore = getHistoryStore("chat")

    expect(lateStore).toBe(registration.store)
    expect(lateStore.getSnapshot()).toMatchObject({
      initialized: true,
      enabled: true,
      conversations,
      activeId: "first",
      busy: true,
    })
  })

  it("notifies every subscriber only when its snapshot changes", () => {
    const store = getHistoryStore("chat")
    const first = vi.fn()
    const second = vi.fn()
    const unsubscribeFirst = store.subscribe(first)
    const unsubscribeSecond = store.subscribe(second)

    const before = store.getSnapshot()
    store.setBusy(false)
    expect(store.getSnapshot()).toBe(before)
    expect(first).not.toHaveBeenCalled()
    expect(second).not.toHaveBeenCalled()

    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    const afterHistory = store.getSnapshot()
    store.updateHistory({
      enabled: true,
      conversations: [{ ...conversations[0]! }],
      activeId: "first",
    })
    expect(store.getSnapshot()).toBe(afterHistory)
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    store.setBusy(true)
    expect(first).toHaveBeenCalledTimes(2)
    expect(second).toHaveBeenCalledTimes(2)

    unsubscribeFirst()
    unsubscribeSecond()
  })

  it("isolates histories by resolved chat id", () => {
    const one = getHistoryStore("one")
    const two = getHistoryStore("two")

    one.updateHistory({ enabled: true, conversations, activeId: "first" })

    expect(two.getSnapshot()).toMatchObject({
      initialized: false,
      enabled: false,
      conversations: [],
      activeId: null,
      busy: false,
    })
  })

  it("keeps busy state consistent and blocks unsafe actions", () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)

    registration.store.actions.select("first")
    registration.store.actions.create()
    registration.store.actions.rename("first", "Renamed")
    registration.store.actions.delete("first")
    expect(transport.sendHistorySelect).toHaveBeenCalledWith("chat", "first")
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("chat")
    expect(transport.sendHistoryRename).toHaveBeenCalledWith(
      "chat",
      "first",
      "Renamed",
    )
    expect(transport.sendHistoryDelete).toHaveBeenCalledWith("chat", "first")

    registration.store.setBusy(true)
    registration.store.actions.select("second")
    registration.store.actions.create()
    registration.store.actions.rename("second", "Nope")
    registration.store.actions.delete("second")
    expect(transport.sendHistorySelect).toHaveBeenCalledTimes(1)
    expect(transport.sendHistoryNew).toHaveBeenCalledTimes(1)
    expect(transport.sendHistoryRename).toHaveBeenCalledTimes(2)
    expect(transport.sendHistoryDelete).toHaveBeenCalledTimes(1)
  })

  it("replaces transport after release and rejects concurrent conflicts", () => {
    const firstTransport = createMockTransport()
    const secondTransport = createMockTransport()
    const first = acquireHistoryStore("chat", firstTransport)

    expect(() => acquireHistoryStore("chat", secondTransport)).toThrow(
      /different ChatTransport/,
    )

    first.release()
    const second = acquireHistoryStore("chat", secondTransport)
    second.store.actions.create()

    expect(secondTransport.sendHistoryNew).toHaveBeenCalledWith("chat")
  })

  it("keeps mounted subscribers live through owner cleanup and removes empty entries", () => {
    const registration = acquireHistoryStore("chat", createMockTransport())
    const subscriber = vi.fn()
    const unsubscribe = registration.store.subscribe(subscriber)

    registration.release()
    const retained = getHistoryStore("chat")
    expect(retained).toBe(registration.store)

    retained.setBusy(true)
    expect(subscriber).toHaveBeenCalledTimes(1)

    unsubscribe()
    expect(getHistoryStore("chat")).not.toBe(retained)
  })
})
