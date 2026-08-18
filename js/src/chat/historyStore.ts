import type { ConversationMeta, ChatTransport } from "../transport/types"

export interface HistorySnapshot {
  initialized: boolean
  enabled: boolean
  conversations: readonly ConversationMeta[]
  activeId: string | null
  busy: boolean
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
})

type Listener = () => void

export class HistoryStore {
  private snapshot: HistorySnapshot = initialSnapshot
  private listeners = new Set<Listener>()
  private transport: ChatTransport | null = null

  constructor(readonly elementId: string) {}

  readonly actions: HistoryActions = {
    select: (conversationId) => {
      if (!this.snapshot.busy) {
        this.requireTransport().sendHistorySelect(
          this.elementId,
          conversationId,
        )
      }
    },
    create: () => {
      if (!this.snapshot.busy) {
        this.requireTransport().sendHistoryNew(this.elementId)
      }
    },
    rename: (conversationId, title) => {
      this.requireTransport().sendHistoryRename(
        this.elementId,
        conversationId,
        title,
      )
    },
    delete: (conversationId) => {
      if (!this.snapshot.busy) {
        this.requireTransport().sendHistoryDelete(
          this.elementId,
          conversationId,
        )
      }
    },
  }

  getSnapshot = (): HistorySnapshot => this.snapshot

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
      cleanupRegistryEntry(this.elementId, this)
    }
  }

  setTransport(transport: ChatTransport | null): void {
    this.transport = transport
  }

  updateHistory({
    enabled,
    conversations,
    activeId,
  }: {
    enabled: boolean
    conversations: ConversationMeta[]
    activeId: string | null
  }): void {
    const nextConversations = conversationsEqual(
      this.snapshot.conversations,
      conversations,
    )
      ? this.snapshot.conversations
      : Object.freeze(
          conversations.map((conversation) => ({ ...conversation })),
        )

    this.publish({
      initialized: true,
      enabled,
      conversations: nextConversations,
      activeId,
      busy: this.snapshot.busy,
    })
  }

  setBusy(busy: boolean): void {
    this.publish({ ...this.snapshot, busy })
  }

  get listenerCount(): number {
    return this.listeners.size
  }

  private requireTransport(): ChatTransport {
    if (!this.transport) {
      throw new Error(
        `History store for "${this.elementId}" has no active ChatTransport.`,
      )
    }
    return this.transport
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
}

const registry = new Map<string, RegistryEntry>()

export interface HistoryStoreRegistration {
  store: HistoryStore
  release(): void
}

export function getHistoryStore(elementId: string): HistoryStore {
  let entry = registry.get(elementId)
  if (!entry) {
    entry = { store: new HistoryStore(elementId), owners: new Map() }
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
    entry?.store === store &&
    entry.owners.size === 0 &&
    store.listenerCount === 0
  ) {
    registry.delete(elementId)
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
    a.busy === b.busy
  )
}

export function resetHistoryStoreRegistryForTests(): void {
  registry.clear()
}
