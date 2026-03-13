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

/** Install a stub `window.Shiny` for tests that need it. Call in `beforeEach`. */
export function installShinyWindowStub(): void {
  ;(window as unknown as Record<string, unknown>).Shiny = {
    setInputValue: vi.fn(),
    addCustomMessageHandler: vi.fn(),
    bindAll: vi.fn(),
    unbindAll: vi.fn(),
    initializeInputs: vi.fn(),
    renderDependenciesAsync: vi.fn(),
  }
}
