import { vi } from "vitest"

// jsdom doesn't provide IntersectionObserver
class MockIntersectionObserver {
  constructor(
    private callback: IntersectionObserverCallback,
    private options?: IntersectionObserverInit,
  ) {}
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
  readonly root = null
  readonly rootMargin = ""
  readonly thresholds: ReadonlyArray<number> = []
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

globalThis.IntersectionObserver =
  MockIntersectionObserver as unknown as typeof IntersectionObserver

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
