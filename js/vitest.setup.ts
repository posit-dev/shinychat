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
const emptyRect = {
  top: 0,
  bottom: 0,
  left: 0,
  right: 0,
  width: 0,
  height: 0,
  x: 0,
  y: 0,
  toJSON: () => ({}),
}
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () =>
    ({
      length: 0,
      item: () => null,
      [Symbol.iterator]: [][Symbol.iterator],
    }) as DOMRectList
}
if (!Range.prototype.getBoundingClientRect) {
  Range.prototype.getBoundingClientRect = () => emptyRect as DOMRect
}

// Node 25 ships a native localStorage that lacks removeItem/clear and shadows
// jsdom's Storage. Replace with a full in-memory implementation so all tests
// that read/write localStorage get consistent, resettable behaviour.
const _localStore: Record<string, string> = {}
const _localStorageMock: Storage = {
  getItem: (key) => _localStore[key] ?? null,
  setItem: (key, val) => {
    _localStore[key] = val
  },
  removeItem: (key) => {
    delete _localStore[key]
  },
  clear: () => {
    for (const k of Object.keys(_localStore)) delete _localStore[k]
  },
  key: (i) => Object.keys(_localStore)[i] ?? null,
  get length() {
    return Object.keys(_localStore).length
  },
}
vi.stubGlobal("localStorage", _localStorageMock)
