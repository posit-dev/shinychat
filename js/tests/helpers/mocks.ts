import { vi } from "vitest"
import type {
  ChatTransport,
  ShinyLifecycle,
  ChatAction,
} from "../../src/transport/types"

/** Mock transport with `fire` to simulate server messages and `listenerCount` for assertions. */
export function createMockTransport(): ChatTransport & {
  fire: (id: string, action: ChatAction) => void
  listenerCount: (id: string) => number
} {
  const listeners = new Map<string, Set<(action: ChatAction) => void>>()

  return {
    sendInput: vi.fn(),
    sendCancel: vi.fn(),
    sendSlashCommand: vi.fn(),
    sendMessagesSnapshot: vi.fn(),
    sendHistorySelect: vi.fn(),
    sendHistoryNew: vi.fn(),
    sendHistoryRename: vi.fn(),
    sendHistoryDelete: vi.fn(),
    onMessage(id, callback) {
      if (!listeners.has(id)) listeners.set(id, new Set())
      listeners.get(id)!.add(callback)
      return () => {
        listeners.get(id)?.delete(callback)
      }
    },
    fire(id, action) {
      const cbs = listeners.get(id)
      if (cbs) {
        for (const cb of cbs) cb(action)
      }
    },
    listenerCount(id) {
      return listeners.get(id)?.size ?? 0
    },
  }
}

/** Mock ShinyLifecycle with all methods as vi.fn() stubs. */
export function createMockShinyLifecycle(): ShinyLifecycle {
  return {
    renderDependencies: vi.fn(async () => {}),
    bindAll: vi.fn(async () => {}),
    unbindAll: vi.fn(),
    showClientMessage: vi.fn(),
  }
}

/**
 * Create a minimal `initializedPromise` stub that mimics Shiny's
 * `InitStatusPromise<void>`. By default the promise is pre-resolved so
 * tests don't have to await anything; pass `resolved: false` to get a
 * pending promise with a `resolve()` handle for timing tests.
 */
export function createInitializedPromise(
  opts: { resolved: boolean } = { resolved: true },
): {
  promise: Promise<void> & { resolved(): boolean }
  resolve: () => void
} {
  let resolveFn!: () => void
  let isResolved = opts.resolved

  const inner = new Promise<void>((res) => {
    resolveFn = () => {
      isResolved = true
      res()
    }
  })

  const promise = Object.assign(inner, {
    resolved() {
      return isResolved
    },
  })

  if (opts.resolved) {
    resolveFn()
  }

  return { promise, resolve: resolveFn }
}

/** Install a stub `window.Shiny` for tests that need it. Call in `beforeEach`. */
export function installShinyWindowStub(
  opts: { initializedPromiseResolved?: boolean } = {},
): { resolveShinyInit: () => void } {
  const { promise, resolve } = createInitializedPromise({
    resolved: opts.initializedPromiseResolved ?? true,
  })
  ;(window as unknown as Record<string, unknown>).Shiny = {
    setInputValue: vi.fn(),
    addCustomMessageHandler: vi.fn(),
    bindAll: vi.fn(),
    unbindAll: vi.fn(),
    initializeInputs: vi.fn(),
    renderDependenciesAsync: vi.fn(),
    initializedPromise: promise,
  }
  return { resolveShinyInit: resolve }
}
