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

// jsdom doesn't implement getClientRects on Range (needed by prosemirror-view
// when focusing the editor, which calls scrollToSelection → coordsAtPos)
const emptyRect = { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as DOMRectList
}
if (!Range.prototype.getBoundingClientRect) {
  Range.prototype.getBoundingClientRect = () => emptyRect as DOMRect
}
