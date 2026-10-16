import { afterEach, describe, expect, it, vi } from "vitest"
import type { ConversationMeta } from "../../src/transport/types"
import * as uuidUtils from "../../src/utils/uuid"
import {
  acquireHistoryStore,
  getHistoryStore,
  isHistorySubmissionBlocked,
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
  vi.restoreAllMocks()
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
      connected: false,
    })
  })

  it("seeds completion-v2 until the first authoritative history update", () => {
    const store = getHistoryStore("chat")

    store.seedCompletionV2TransitionProtocol()
    const seededSnapshot = store.getSnapshot()
    expect(seededSnapshot).toMatchObject({
      initialized: false,
      enabled: false,
      conversations: [],
      activeId: null,
      transitionProtocol: "completion-v2",
      historyTransitionPending: null,
    })
    expect(isHistorySubmissionBlocked(seededSnapshot)).toBe(true)

    store.seedCompletionV2TransitionProtocol()
    expect(store.getSnapshot()).toBe(seededSnapshot)

    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v2",
    })
    expect(store.getSnapshot()).toMatchObject({
      initialized: true,
      enabled: true,
      transitionProtocol: "completion-v2",
      historyTransitionPending: null,
    })
    expect(isHistorySubmissionBlocked(store.getSnapshot())).toBe(false)
  })

  it("withdraws a seed and clears a pending transition on a runtime update", () => {
    const store = getHistoryStore("chat")
    vi.spyOn(uuidUtils, "uuid").mockReturnValue("seed-pending")

    store.seedCompletionV2TransitionProtocol()
    expect(store.beginEditTransition()).toBe("seed-pending")
    expect(isHistorySubmissionBlocked(store.getSnapshot())).toBe(true)

    store.updateHistory({
      enabled: false,
      conversations: [],
      activeId: null,
    })

    expect(store.getSnapshot()).toMatchObject({
      initialized: true,
      enabled: false,
      conversations: [],
      activeId: null,
      transitionProtocol: null,
      historyTransitionPending: null,
    })
    expect(isHistorySubmissionBlocked(store.getSnapshot())).toBe(false)
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
    expect(transport.sendHistoryRename).toHaveBeenCalledTimes(1)
    expect(transport.sendHistoryDelete).toHaveBeenCalledTimes(1)
  })

  it("uses completion-v1 only for active New/Delete transitions", () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    registration.store.actions.create()
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("chat")
    expect(registration.store.getSnapshot().historyTransitionPending).toBeNull()

    registration.store.actions.delete("first")
    expect(transport.sendHistoryDelete).toHaveBeenCalledWith("chat", "first")
    expect(registration.store.getSnapshot().historyTransitionPending).toBeNull()

    vi.spyOn(uuidUtils, "uuid")
      .mockReturnValueOnce("request-new")
      .mockReturnValueOnce("request-delete")
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })

    registration.store.actions.create()
    expect(transport.sendHistoryNew).toHaveBeenLastCalledWith(
      "chat",
      "request-new",
    )
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-new",
    )

    registration.store.completeHistoryTransition("stale")
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-new",
    )
    registration.store.completeHistoryTransition("request-new")
    expect(registration.store.getSnapshot().historyTransitionPending).toBeNull()

    registration.store.actions.delete("other")
    expect(transport.sendHistoryDelete).toHaveBeenCalledWith("chat", "other")
    expect(registration.store.getSnapshot().historyTransitionPending).toBeNull()

    registration.store.actions.delete("first")
    expect(transport.sendHistoryDelete).toHaveBeenLastCalledWith(
      "chat",
      "first",
      "request-delete",
    )
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-delete",
    )
  })

  it("replaces capability state and clears transitions on every protocol change", () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    const requestId = vi
      .spyOn(uuidUtils, "uuid")
      .mockReturnValue("request-pending")

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    registration.store.actions.create()
    expect(requestId).toHaveBeenCalledOnce()
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-pending",
    )

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })
    expect(registration.store.getSnapshot()).toMatchObject({
      transitionProtocol: null,
      historyTransitionPending: null,
    })

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    registration.store.actions.create()
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-pending",
    )

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "unknown",
    })
    expect(registration.store.getSnapshot()).toMatchObject({
      transitionProtocol: null,
      historyTransitionPending: null,
    })

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v2",
    })
    expect(registration.store.beginEditTransition()).toBe("request-pending")
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "request-pending",
    )

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    expect(registration.store.getSnapshot()).toMatchObject({
      transitionProtocol: "completion-v1",
      historyTransitionPending: null,
    })
    expect(registration.store.acceptEditProjection("request-pending")).toBe(
      false,
    )
  })

  it("uses completion-v2 for edit/navigation transitions while retaining v1 New/Delete", () => {
    const transport = createMockTransport()
    const registration = acquireHistoryStore("chat", transport)
    const requestIds = vi
      .spyOn(uuidUtils, "uuid")
      .mockReturnValueOnce("v1-new")
      .mockReturnValueOnce("v2-edit")
      .mockReturnValueOnce("v2-navigation")

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    expect(registration.store.beginEditTransition()).toBeNull()
    registration.store.actions.create()
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("chat", "v1-new")
    registration.store.completeHistoryTransition("v1-new")

    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v2",
    })
    expect(registration.store.beginEditTransition()).toBe("v2-edit")
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "v2-edit",
    )
    registration.store.completeHistoryTransition("v2-edit")
    expect(registration.store.beginNavigationTransition()).toBe("v2-navigation")

    registration.store.actions.select("first")
    registration.store.actions.rename("first", "Blocked")
    registration.store.actions.create()
    registration.store.actions.delete("first")
    expect(transport.sendHistorySelect).not.toHaveBeenCalled()
    expect(transport.sendHistoryRename).not.toHaveBeenCalled()
    expect(transport.sendHistoryNew).toHaveBeenCalledTimes(1)
    expect(transport.sendHistoryDelete).not.toHaveBeenCalled()
  })

  it("accepts only the matching edit projection and keeps mutation busy", () => {
    const registration = acquireHistoryStore("chat", createMockTransport())
    vi.spyOn(uuidUtils, "uuid").mockReturnValue("edit-request")
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v2",
    })

    expect(registration.store.beginEditTransition()).toBe("edit-request")
    expect(registration.store.acceptEditProjection("stale")).toBe(false)
    expect(registration.store.getSnapshot().busy).toBe(false)
    expect(registration.store.acceptEditProjection("edit-request")).toBe(true)
    expect(registration.store.getSnapshot().busy).toBe(true)

    registration.store.completeHistoryTransition("stale")
    expect(registration.store.getSnapshot().historyTransitionPending).toBe(
      "edit-request",
    )
    registration.store.completeHistoryTransition("edit-request")
    expect(registration.store.getSnapshot().historyTransitionPending).toBeNull()
  })

  it("uses remount-safe UUIDs so stale completions cannot release a new transition", async () => {
    const requestIds = vi
      .spyOn(uuidUtils, "uuid")
      .mockReturnValueOnce("request-before-remount")
      .mockReturnValueOnce("request-after-remount")
    const first = acquireHistoryStore("chat", createMockTransport())
    first.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    first.store.actions.create()
    expect(first.store.getSnapshot().historyTransitionPending).toBe(
      "request-before-remount",
    )

    first.release()
    await Promise.resolve()

    const second = acquireHistoryStore("chat", createMockTransport())
    expect(second.store).not.toBe(first.store)
    second.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
      transitionProtocol: "completion-v1",
    })
    second.store.actions.create()
    expect(requestIds).toHaveBeenCalledTimes(2)

    second.store.completeHistoryTransition("request-before-remount")
    expect(second.store.getSnapshot().historyTransitionPending).toBe(
      "request-after-remount",
    )
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

  it("retains replayed data with detached no-op actions until reacquisition", async () => {
    const firstTransport = createMockTransport()
    const registration = acquireHistoryStore("chat", firstTransport)
    registration.store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })
    const subscriber = vi.fn()
    const unsubscribe = registration.store.subscribe(subscriber)

    registration.release()
    const retained = getHistoryStore("chat")
    expect(retained).toBe(registration.store)
    expect(retained.getSnapshot()).toMatchObject({
      initialized: true,
      enabled: true,
      conversations,
      activeId: "first",
      connected: false,
    })

    expect(() => {
      retained.actions.select("first")
      retained.actions.create()
      retained.actions.rename("first", "Renamed")
      retained.actions.delete("first")
    }).not.toThrow()
    expect(firstTransport.sendHistorySelect).not.toHaveBeenCalled()
    expect(firstTransport.sendHistoryNew).not.toHaveBeenCalled()
    expect(firstTransport.sendHistoryRename).not.toHaveBeenCalled()
    expect(firstTransport.sendHistoryDelete).not.toHaveBeenCalled()
    expect(subscriber).toHaveBeenCalledTimes(1)

    const secondTransport = createMockTransport()
    const replacement = acquireHistoryStore("chat", secondTransport)
    expect(replacement.store).toBe(retained)
    expect(retained.getSnapshot().connected).toBe(true)
    retained.actions.rename("first", "Renamed")
    expect(secondTransport.sendHistoryRename).toHaveBeenCalledWith(
      "chat",
      "first",
      "Renamed",
    )

    replacement.release()
    unsubscribe()
    await Promise.resolve()
    expect(getHistoryStore("chat")).not.toBe(retained)
  })
})
