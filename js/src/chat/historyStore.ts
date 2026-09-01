import type { ConversationMeta, ChatTransport } from "../transport/types"
import { uuid } from "../utils/uuid"

type TransitionProtocol = "completion-v1" | "completion-v2"

const completionTransitionProtocols: readonly TransitionProtocol[] = [
  "completion-v1",
  "completion-v2",
]

export interface HistorySnapshot {
  initialized: boolean
  enabled: boolean
  conversations: readonly ConversationMeta[]
  activeId: string | null
  busy: boolean
  connected: boolean
  transitionProtocol: TransitionProtocol | null
  historyTransitionPending: string | null
}

export interface HistoryActions {
  select(id: string): void
  create(): void
  rename(id: string, title: string): void
  delete(id: string): void
}

const initialSnapshot: HistorySnapshot = Object.freeze({
  initialized: false,
  enabled: false,
  conversations: Object.freeze([]),
  activeId: null,
  busy: false,
  connected: false,
  transitionProtocol: null,
  historyTransitionPending: null,
})

type Listener = () => void

export class HistoryStore {
  private snapshot: HistorySnapshot = initialSnapshot
  private listeners = new Set<Listener>()
  private transport: ChatTransport | null = null

  constructor(readonly elementId: string) {}

  readonly actions: HistoryActions = {
    select: (conversationId) => {
      const transport = this.activeTransport()
      if (transport && !this.isMutationBlocked()) {
        transport.sendHistorySelect(this.elementId, conversationId)
      }
    },
    create: () => {
      const transport = this.activeTransport()
      if (!transport || this.isMutationBlocked()) return
      const requestId =
        this.snapshot.activeId === null || !this.supportsCompletionProtocol()
          ? undefined
          : this.beginTransition()
      if (requestId === undefined) {
        transport.sendHistoryNew(this.elementId)
      } else {
        transport.sendHistoryNew(this.elementId, requestId)
      }
    },
    rename: (conversationId, title) => {
      const transport = this.activeTransport()
      if (!transport || this.isMutationBlocked()) return
      transport.sendHistoryRename(this.elementId, conversationId, title)
    },
    delete: (conversationId) => {
      const transport = this.activeTransport()
      if (!transport || this.isMutationBlocked()) return
      const requestId =
        conversationId === this.snapshot.activeId &&
        this.supportsCompletionProtocol()
          ? this.beginTransition()
          : undefined
      if (requestId === undefined) {
        transport.sendHistoryDelete(this.elementId, conversationId)
      } else {
        transport.sendHistoryDelete(this.elementId, conversationId, requestId)
      }
    },
  }

  getSnapshot = (): HistorySnapshot => this.snapshot

  subscribe = (listener: Listener): (() => void) => {
    retainRegistryEntry(this.elementId, this)
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
      cleanupRegistryEntry(this.elementId, this)
    }
  }

  setTransport(transport: ChatTransport | null): void {
    this.transport = transport
    this.publish({ ...this.snapshot, connected: transport !== null })
  }

  updateHistory({
    enabled,
    conversations,
    activeId,
    transitionProtocol,
  }: {
    enabled: boolean
    conversations: ConversationMeta[]
    activeId: string | null
    transitionProtocol?: string
  }): void {
    const nextConversations = conversationsEqual(
      this.snapshot.conversations,
      conversations,
    )
      ? this.snapshot.conversations
      : Object.freeze(
          conversations.map((conversation) => ({ ...conversation })),
        )

    const normalizedProtocol = normalizeTransitionProtocol(transitionProtocol)
    this.publish({
      initialized: true,
      enabled,
      conversations: nextConversations,
      activeId,
      busy: this.snapshot.busy,
      connected: this.snapshot.connected,
      transitionProtocol: normalizedProtocol,
      historyTransitionPending:
        normalizedProtocol !== null
          ? this.snapshot.historyTransitionPending
          : null,
    })
  }

  setBusy(busy: boolean): void {
    this.publish({ ...this.snapshot, busy })
  }

  beginEditTransition(): string | null {
    if (!this.supportsEditProjectionProtocol() || this.isMutationBlocked())
      return null
    return this.beginTransition()
  }

  acceptEditProjection(requestId: string): boolean {
    if (this.snapshot.historyTransitionPending !== requestId) return false
    // Projection installs the ordinary input/loading state immediately after
    // this call. Mark history busy first so no mutation can slip between the
    // matching wire action and React's state commit.
    this.setBusy(true)
    return true
  }

  isMutationBlocked(): boolean {
    return this.snapshot.busy || this.hasPendingTransition()
  }

  completeHistoryTransition(requestId: string): void {
    if (this.snapshot.historyTransitionPending !== requestId) return
    this.publish({ ...this.snapshot, historyTransitionPending: null })
  }

  get listenerCount(): number {
    return this.listeners.size
  }

  private activeTransport(): ChatTransport | null {
    return this.snapshot.connected ? this.transport : null
  }

  private hasPendingTransition(): boolean {
    return this.snapshot.historyTransitionPending !== null
  }

  private supportsCompletionProtocol(): boolean {
    return this.snapshot.transitionProtocol !== null
  }

  private supportsEditProjectionProtocol(): boolean {
    return this.snapshot.transitionProtocol === "completion-v2"
  }

  private beginTransition(): string {
    const requestId = uuid()
    this.publish({ ...this.snapshot, historyTransitionPending: requestId })
    return requestId
  }

  private publish(next: HistorySnapshot): void {
    if (snapshotsEqual(this.snapshot, next)) return
    this.snapshot = Object.freeze(next)
    for (const listener of this.listeners) {
      listener()
    }
  }
}

interface RegistryEntry {
  store: HistoryStore
  owners: Map<symbol, ChatTransport>
  cleanupGeneration: number
}

const registry = new Map<string, RegistryEntry>()

export interface HistoryStoreRegistration {
  store: HistoryStore
  release(): void
}

export function getHistoryStore(elementId: string): HistoryStore {
  let entry = registry.get(elementId)
  if (!entry) {
    entry = {
      store: new HistoryStore(elementId),
      owners: new Map(),
      cleanupGeneration: 0,
    }
    registry.set(elementId, entry)
  }
  return entry.store
}

/**
 * Claim a chat's shared history state for one mounted ChatApp.
 *
 * A second live owner may share the same transport, but a different transport
 * is rejected because its history actions would otherwise be routed
 * unpredictably. The store itself outlives a temporary lack of owners while
 * React subscribers remain mounted, allowing late consumers to replay state.
 */
export function acquireHistoryStore(
  elementId: string,
  transport: ChatTransport,
): HistoryStoreRegistration {
  const store = getHistoryStore(elementId)
  const entry = registry.get(elementId)!

  const existingTransport = entry.owners.values().next().value as
    | ChatTransport
    | undefined
  if (existingTransport && existingTransport !== transport) {
    throw new Error(
      `History store for "${elementId}" is already owned by a different ChatTransport.`,
    )
  }

  entry.cleanupGeneration += 1
  const owner = Symbol(elementId)
  entry.owners.set(owner, transport)
  entry.store.setTransport(transport)

  let released = false
  return {
    store,
    release() {
      if (released) return
      released = true
      const current = registry.get(elementId)
      if (!current || current.store !== entry.store) return

      current.owners.delete(owner)
      const nextTransport = current.owners.values().next().value as
        | ChatTransport
        | undefined
      current.store.setTransport(nextTransport ?? null)
      cleanupRegistryEntry(elementId, current.store)
    },
  }
}

function cleanupRegistryEntry(elementId: string, store: HistoryStore): void {
  const entry = registry.get(elementId)
  if (
    !entry ||
    entry.store !== store ||
    entry.owners.size !== 0 ||
    store.listenerCount !== 0
  )
    return

  const cleanupGeneration = ++entry.cleanupGeneration
  queueMicrotask(() => {
    const current = registry.get(elementId)
    if (
      current?.store === store &&
      current.cleanupGeneration === cleanupGeneration &&
      current.owners.size === 0 &&
      store.listenerCount === 0
    ) {
      registry.delete(elementId)
    }
  })
}

function retainRegistryEntry(elementId: string, store: HistoryStore): void {
  const entry = registry.get(elementId)
  if (entry?.store === store) {
    entry.cleanupGeneration += 1
  }
}

function conversationsEqual(
  a: readonly ConversationMeta[],
  b: readonly ConversationMeta[],
): boolean {
  return (
    a.length === b.length &&
    a.every(
      (conversation, index) =>
        conversation.id === b[index]?.id &&
        conversation.title === b[index]?.title &&
        conversation.created_at === b[index]?.created_at &&
        conversation.updated_at === b[index]?.updated_at,
    )
  )
}

function snapshotsEqual(a: HistorySnapshot, b: HistorySnapshot): boolean {
  return (
    a.initialized === b.initialized &&
    a.enabled === b.enabled &&
    a.conversations === b.conversations &&
    a.activeId === b.activeId &&
    a.busy === b.busy &&
    a.connected === b.connected &&
    a.transitionProtocol === b.transitionProtocol &&
    a.historyTransitionPending === b.historyTransitionPending
  )
}

function normalizeTransitionProtocol(
  protocol: string | undefined,
): TransitionProtocol | null {
  return completionTransitionProtocols.includes(protocol as TransitionProtocol)
    ? (protocol as TransitionProtocol)
    : null
}

export function resetHistoryStoreRegistryForTests(): void {
  registry.clear()
}
