import { vi } from "vitest"

// jsdom doesn't provide ResizeObserver (needed by use-stick-to-bottom)
class MockResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

globalThis.ResizeObserver =
  MockResizeObserver as unknown as typeof ResizeObserver

// jsdom doesn't implement scrollTo on elements
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = vi.fn()
}
