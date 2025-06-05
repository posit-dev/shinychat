import { beforeEach, afterEach, vi } from "vitest"
import "@testing-library/jest-dom"

// Mock window.Shiny for tests
Object.defineProperty(window, "Shiny", {
  value: {
    addCustomMessageHandler: vi.fn(),
    setInputValue: vi.fn(),
    renderDependenciesAsync: vi.fn().mockResolvedValue(undefined),
    bindAll: vi.fn().mockResolvedValue(undefined),
    unbindAll: vi.fn(),
    initializeInputs: vi.fn(),
  },
  writable: true,
})

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false, // Default to light mode for tests
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated
    removeListener: vi.fn(), // Deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Clean up after each test
afterEach(() => {
  vi.clearAllMocks()
})

// Helper to create DOM elements for testing
export function createTestContainer(): HTMLDivElement {
  const container = document.createElement("div")
  container.style.height = "400px"
  container.style.overflow = "auto"
  document.body.appendChild(container)
  return container
}

export function cleanupTestContainer(container: HTMLElement): void {
  if (container && container.parentNode) {
    container.parentNode.removeChild(container)
  }
}

// Helper to mock matchMedia with specific conditions
export function mockMatchMedia(matches: boolean = false): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(), // Deprecated
      removeListener: vi.fn(), // Deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

// Helper to test dark mode behavior
export function mockDarkMode(): void {
  mockMatchMedia(true)
}

// Helper to test light mode behavior
export function mockLightMode(): void {
  mockMatchMedia(false)
}
