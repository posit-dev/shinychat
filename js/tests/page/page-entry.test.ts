import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent } from "@testing-library/react"
import type { ConversationMeta } from "../../src/transport/types"
import {
  getHistoryStore,
  resetHistoryStoreRegistryForTests,
} from "../../src/chat/historyStore"
import { PAGE_MOBILE_MEDIA_QUERY } from "../../src/page/page-entry"

type MediaListener = (event: MediaQueryListEvent) => void

const conversations: ConversationMeta[] = [
  {
    id: "first",
    title: "First conversation",
    created_at: "2026-08-18T09:00:00.000Z",
    updated_at: "2026-08-18T10:00:00.000Z",
  },
]

class ResizeObserverStub {
  private static instances = new Set<ResizeObserverStub>()
  private readonly targets = new Set<Element>()

  constructor(private readonly callback: ResizeObserverCallback) {
    ResizeObserverStub.instances.add(this)
  }

  observe(target: Element) {
    this.targets.add(target)
  }

  unobserve(target: Element) {
    this.targets.delete(target)
  }

  disconnect() {
    this.targets.clear()
    ResizeObserverStub.instances.delete(this)
  }

  static resize(target: Element) {
    ResizeObserverStub.instances.forEach((observer) => {
      if (!observer.targets.has(target)) return
      observer.callback(
        [
          {
            target,
            contentRect: target.getBoundingClientRect(),
          } as ResizeObserverEntry,
        ],
        observer as unknown as ResizeObserver,
      )
    })
  }

  static reset() {
    ResizeObserverStub.instances.clear()
  }
}

function installMatchMedia(initialMatches: boolean) {
  const listeners = new Set<MediaListener>()
  const mediaQuery = {
    matches: initialMatches,
    media: PAGE_MOBILE_MEDIA_QUERY,
    onchange: null,
    addEventListener: (_type: string, listener: MediaListener) => {
      listeners.add(listener)
    },
    removeEventListener: (_type: string, listener: MediaListener) => {
      listeners.delete(listener)
    },
    addListener: (listener: MediaListener) => {
      listeners.add(listener)
    },
    removeListener: (listener: MediaListener) => {
      listeners.delete(listener)
    },
    dispatchEvent: () => true,
  } as MediaQueryList

  window.matchMedia = vi.fn(() => mediaQuery)

  return {
    mediaQuery,
    listenerCount: () => listeners.size,
    setMatches(matches: boolean) {
      Object.defineProperty(mediaQuery, "matches", {
        configurable: true,
        value: matches,
      })
      const event = { matches, media: PAGE_MOBILE_MEDIA_QUERY }
      listeners.forEach((listener) => listener(event as MediaQueryListEvent))
    },
  }
}

function pageFixture({
  identity = true,
  pages = true,
  sidebar = true,
  chatId = "chat",
  homeOpen = "open",
  homeResizable = true,
  homeWidth = "20rem",
  customOpen = "closed",
  customResizable = false,
  customWidth = "24rem",
  alwaysPage = false,
  homeSidebarKey = "home",
  layoutWidth = 1000,
}: {
  identity?: boolean
  pages?: boolean
  sidebar?: boolean
  chatId?: string
  homeOpen?: "auto" | "open" | "closed" | "always"
  homeResizable?: boolean
  homeWidth?: string
  customOpen?: "auto" | "open" | "closed" | "always"
  customResizable?: boolean
  customWidth?: string
  alwaysPage?: boolean
  homeSidebarKey?: "home" | "default"
  layoutWidth?: number
} = {}) {
  const page = document.createElement("shiny-chat-page")
  page.dataset.chatId = chatId
  page.dataset.activePage = "home"
  page.dataset.testLayoutWidth = layoutWidth.toString()
  page.innerHTML = `
    <header class="shiny-chat-page-header">
      <button
        type="button"
        class="shiny-chat-page-sidebar-toggle"
        aria-expanded="false"
      >Menu</button>
      ${
        identity
          ? `<button
              type="button"
              class="shiny-chat-page-identity"
              data-page-home
              aria-label="Return to chat"
            >Assistant</button>`
          : `<div class="shiny-chat-page-identity">Assistant</div>`
      }
      <div class="shiny-chat-page-controls-mount-desktop">
        <div class="shiny-chat-page-controls">
          <nav class="shiny-chat-page-nav" aria-label="Pages">
            ${
              pages
                ? `
                  <button
                    type="button"
                    class="shiny-chat-page-nav-link"
                    data-page-target="default-page"
                  >Default</button>
                  <button
                    type="button"
                    class="shiny-chat-page-nav-link"
                    data-page-target="custom-page"
                  >Custom</button>
                  <button
                    type="button"
                    class="shiny-chat-page-nav-link"
                    data-page-target="no-sidebar"
                  >No sidebar</button>
                  ${
                    alwaysPage
                      ? `<button
                          type="button"
                          class="shiny-chat-page-nav-link"
                          data-page-target="always-page"
                        >Always</button>`
                      : ""
                  }
                `
                : ""
            }
          </nav>
          <div class="shiny-chat-page-toolbar"></div>
        </div>
      </div>
    </header>
    <div class="shiny-chat-page-body">
      <aside class="shiny-chat-page-sidebar">
        <div class="shiny-chat-page-controls-mount-mobile"></div>
        ${
          sidebar
            ? `
              <div
                class="shiny-chat-page-sidebar-panel"
                data-sidebar-for="home"
                data-sidebar-open="${homeOpen}"
                data-sidebar-width="${homeWidth}"
                data-sidebar-resizable="${homeResizable}"
              >
                <button type="button">Home action</button>
                <details>
                  <summary>More actions</summary>
                  <button type="button">Nested action</button>
                </details>
              </div>
            `
            : ""
        }
        <div
          class="shiny-chat-page-sidebar-panel"
          data-sidebar-for="default"
          data-sidebar-open="auto"
          data-sidebar-width="280px"
          data-sidebar-resizable="true"
          hidden
        >
          <button type="button">Default action</button>
        </div>
        <div
          class="shiny-chat-page-sidebar-panel"
          data-sidebar-for="page-2"
          data-sidebar-open="${customOpen}"
          data-sidebar-width="${customWidth}"
          data-sidebar-resizable="${customResizable}"
          hidden
        >
          <button type="button">Custom action</button>
        </div>
        ${
          alwaysPage
            ? `<div
                class="shiny-chat-page-sidebar-panel"
                data-sidebar-for="always"
                data-sidebar-open="always"
                data-sidebar-width="18rem"
                data-sidebar-resizable="true"
                hidden
              >
                <button type="button">Always action</button>
              </div>`
            : ""
        }
      </aside>
      <main class="shiny-chat-page-main">
        <section
          class="shiny-chat-page-panel shiny-chat-page-home"
          data-page-value="home"
          data-page-toolbar-source="home"
          ${sidebar ? `data-sidebar-key="${homeSidebarKey}"` : ""}
        >
          <shiny-chat-container id="chat">
            <textarea class="draft">unfinished draft</textarea>
            <div class="stream-state">partial response</div>
            <div class="artifact-state">
              <input value="artifact draft">
            </div>
          </shiny-chat-container>
        </section>
        ${
          pages
            ? `
              <section
                class="shiny-chat-page-panel"
                data-page-value="default-page"
                data-sidebar-key="default"
                data-page-toolbar-source="home"
                hidden
              >Default page</section>
              <section
                class="shiny-chat-page-panel"
                data-page-value="custom-page"
                data-sidebar-key="page-2"
                data-page-toolbar-source="custom-page"
                hidden
              >Custom page</section>
              <section
                class="shiny-chat-page-panel"
                data-page-value="no-sidebar"
                hidden
              >No sidebar page</section>
              ${
                alwaysPage
                  ? `<section
                      class="shiny-chat-page-panel"
                      data-page-value="always-page"
                      data-sidebar-key="always"
                      hidden
                    >Always page</section>`
                  : ""
              }
            `
            : ""
        }
      </main>
    </div>
    <div class="shiny-chat-page-toolbar-sources">
      <div class="shiny-chat-page-toolbar-source" data-page-toolbar-source="home">
        <div class="shiny-chat-page-toolbar-content">
          <input id="shiny-toolbar-input" value="initial">
        </div>
      </div>
      <div class="shiny-chat-page-toolbar-source" data-page-toolbar-source="custom-page">
        <div class="shiny-chat-page-toolbar-content">
          <input id="custom-toolbar-input" value="custom initial">
        </div>
      </div>
    </div>
  `

  const currentLayoutWidth = () => Number(page.dataset.testLayoutWidth)
  const layoutRect = () => new DOMRect(0, 0, currentLayoutWidth(), 700)
  Object.defineProperty(page, "getBoundingClientRect", {
    configurable: true,
    value: layoutRect,
  })
  for (const element of page.querySelectorAll<HTMLElement>(
    ".shiny-chat-page-body, .shiny-chat-page-main",
  )) {
    Object.defineProperty(element, "getBoundingClientRect", {
      configurable: true,
      value: layoutRect,
    })
  }
  const aside = page.querySelector<HTMLElement>(".shiny-chat-page-sidebar")!
  Object.defineProperty(aside, "getBoundingClientRect", {
    configurable: true,
    value: () => {
      const configured =
        page.style.getPropertyValue("--shiny-chat-page-sidebar-width") ||
        aside.dataset.sidebarWidth ||
        "0"
      const numeric = Number.parseFloat(configured)
      const requested = configured.endsWith("rem") ? numeric * 16 : numeric
      const width = Math.max(
        150,
        Math.min(
          Number.isFinite(requested) ? requested : 280,
          currentLayoutWidth() - 360,
        ),
      )
      return new DOMRect(0, 0, width, 700)
    },
  })

  document.body.append(page)
  return page
}

function getPageElements(page: HTMLElement) {
  return {
    aside: page.querySelector<HTMLElement>(".shiny-chat-page-sidebar")!,
    controls: page.querySelector<HTMLElement>(".shiny-chat-page-controls")!,
    desktopMount: page.querySelector<HTMLElement>(
      ".shiny-chat-page-controls-mount-desktop",
    )!,
    mobileMount: page.querySelector<HTMLElement>(
      ".shiny-chat-page-controls-mount-mobile",
    )!,
    toggle: page.querySelector<HTMLButtonElement>(
      ".shiny-chat-page-sidebar-toggle",
    )!,
    identity: page.querySelector<HTMLButtonElement>(
      "button.shiny-chat-page-identity",
    ),
    panels: Array.from(
      page.querySelectorAll<HTMLElement>(".shiny-chat-page-panel"),
    ),
    sidebarPanels: Array.from(
      page.querySelectorAll<HTMLElement>(".shiny-chat-page-sidebar-panel"),
    ),
    navButtons: Array.from(
      page.querySelectorAll<HTMLButtonElement>(".shiny-chat-page-nav-link"),
    ),
    get resizer() {
      return page.querySelector<HTMLElement>(".shiny-chat-page-sidebar-resizer")
    },
  }
}

beforeEach(() => {
  installMatchMedia(false)
  ResizeObserverStub.reset()
  vi.stubGlobal("ResizeObserver", ResizeObserverStub)
})

afterEach(() => {
  document.body.replaceChildren()
  resetHistoryStoreRegistryForTests()
  ResizeObserverStub.reset()
  vi.unstubAllGlobals()
})

describe("shiny-chat-page navigation", () => {
  it("switches pages without replacing the mounted chat or its descendants", () => {
    const page = pageFixture()
    const { identity, navButtons, panels } = getPageElements(page)
    const onResize = vi.fn()
    window.addEventListener("resize", onResize)
    const chat = page.querySelector("shiny-chat-container")!
    const draft = page.querySelector<HTMLTextAreaElement>(".draft")!
    const streamState = page.querySelector<HTMLElement>(".stream-state")!
    const artifact = page.querySelector<HTMLElement>(".artifact-state")!
    const artifactInput = artifact.querySelector<HTMLInputElement>("input")!
    draft.value = "preserved user draft"
    streamState.textContent = "continued response"
    artifactInput.value = "preserved artifact state"
    Object.defineProperty(chat, "scrollTop", {
      configurable: true,
      value: 180,
      writable: true,
    })

    expect(page.dataset.activePage).toBe("home")
    expect(identity?.getAttribute("aria-current")).toBe("page")
    expect(identity?.hasAttribute("aria-label")).toBe(false)

    navButtons[1]!.click()

    expect(page.dataset.activePage).toBe("custom-page")
    expect(panels.map((panel) => panel.hidden)).toEqual([
      true,
      true,
      false,
      true,
    ])
    expect(navButtons[1]!.getAttribute("aria-current")).toBe("page")
    expect(identity?.hasAttribute("aria-current")).toBe(false)
    expect(page.querySelector("shiny-chat-container")).toBe(chat)
    expect(page.querySelector(".draft")).toBe(draft)
    expect(draft.value).toBe("preserved user draft")
    expect(streamState.textContent).toBe("continued response")
    expect(page.querySelector(".artifact-state")).toBe(artifact)
    expect(artifactInput.value).toBe("preserved artifact state")
    expect(chat.scrollTop).toBe(180)
    expect(identity?.getAttribute("aria-label")).toBe("Return to chat")

    identity!.click()

    expect(page.dataset.activePage).toBe("home")
    expect(panels.map((panel) => panel.hidden)).toEqual([
      false,
      true,
      true,
      true,
    ])
    expect(identity?.getAttribute("aria-current")).toBe("page")
    expect(identity?.hasAttribute("aria-label")).toBe(false)
    expect(
      navButtons.every((button) => !button.hasAttribute("aria-current")),
    ).toBe(true)
    expect(onResize).toHaveBeenCalledTimes(2)
    window.removeEventListener("resize", onResize)
  })

  it("moves the selected toolbar subtree without cloning its controls", () => {
    const page = pageFixture()
    const { identity, navButtons } = getPageElements(page)
    const toolbar = page.querySelector<HTMLElement>(".shiny-chat-page-toolbar")!
    const homeInput = page.querySelector<HTMLInputElement>(
      "#shiny-toolbar-input",
    )!
    const customInput = page.querySelector<HTMLInputElement>(
      "#custom-toolbar-input",
    )!

    homeInput.value = "home state"
    navButtons[0]!.click()
    expect(toolbar.querySelector("#shiny-toolbar-input")).toBe(homeInput)
    expect(page.querySelectorAll("#shiny-toolbar-input")).toHaveLength(1)

    navButtons[1]!.click()
    expect(toolbar.querySelector("#custom-toolbar-input")).toBe(customInput)
    expect(page.querySelectorAll("#custom-toolbar-input")).toHaveLength(1)
    expect(page.querySelector("#shiny-toolbar-input")).toBe(homeInput)
    customInput.value = "custom state"

    identity!.click()
    expect(toolbar.querySelector("#shiny-toolbar-input")).toBe(homeInput)
    expect(homeInput.value).toBe("home state")
    expect(page.querySelector("#custom-toolbar-input")).toBe(customInput)
    expect(customInput.value).toBe("custom state")
    expect(
      page.querySelectorAll(".shiny-chat-page-toolbar-content"),
    ).toHaveLength(2)
  })

  it("synchronizes home, default, custom, and absent sidebar metadata", () => {
    const page = pageFixture()
    const { aside, navButtons, sidebarPanels, identity } = getPageElements(page)

    expect(aside.dataset.sidebarKey).toBe("home")
    expect(aside.dataset.sidebarOpen).toBe("open")
    expect(aside.dataset.sidebarWidth).toBe("20rem")
    expect(aside.dataset.sidebarResizable).toBe("true")
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "20rem",
    )
    expect(sidebarPanels.map((panel) => panel.hidden)).toEqual([
      false,
      true,
      true,
    ])

    navButtons[0]!.click()
    expect(aside.dataset.sidebarKey).toBe("default")
    expect(aside.dataset.sidebarOpen).toBe("auto")
    expect(aside.dataset.sidebarWidth).toBe("280px")
    expect(aside.dataset.sidebarResizable).toBe("true")
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "280px",
    )
    expect(sidebarPanels.map((panel) => panel.hidden)).toEqual([
      true,
      false,
      true,
    ])

    navButtons[1]!.click()
    expect(aside.dataset.sidebarKey).toBe("page-2")
    expect(aside.dataset.sidebarOpen).toBe("closed")
    expect(aside.dataset.sidebarWidth).toBe("24rem")
    expect(aside.dataset.sidebarResizable).toBe("false")
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "24rem",
    )
    expect(sidebarPanels.map((panel) => panel.hidden)).toEqual([
      true,
      true,
      false,
    ])

    navButtons[2]!.click()
    expect(aside.hasAttribute("data-sidebar-key")).toBe(false)
    expect(aside.hasAttribute("data-sidebar-open")).toBe(false)
    expect(aside.hasAttribute("data-sidebar-width")).toBe(false)
    expect(aside.hasAttribute("data-sidebar-resizable")).toBe(false)
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "",
    )
    expect(sidebarPanels.every((panel) => panel.hidden)).toBe(true)

    identity!.click()
    expect(aside.dataset.sidebarKey).toBe("home")
    expect(sidebarPanels[0]!.hidden).toBe(false)
  })

  it("degrades safely and marks malformed required DOM", () => {
    const page = document.createElement("shiny-chat-page")
    page.innerHTML = `<main class="shiny-chat-page-main"></main>`

    expect(() => document.body.append(page)).not.toThrow()
    expect(page.dataset.pageError).toContain("invalid-dom:")
    expect(page.dataset.pageError).toContain("home-panel")
  })
})

describe("shiny-chat-page responsive controls", () => {
  it("moves one controls node between mounts and preserves Shiny input identity", () => {
    const media = installMatchMedia(false)
    const page = pageFixture()
    const { controls, desktopMount, mobileMount } = getPageElements(page)
    const shinyInput = page.querySelector<HTMLInputElement>(
      "#shiny-toolbar-input",
    )!
    shinyInput.value = "live Shiny state"

    expect(window.matchMedia).toHaveBeenCalledWith(PAGE_MOBILE_MEDIA_QUERY)
    expect(controls.parentElement).toBe(desktopMount)
    expect(page.querySelectorAll(".shiny-chat-page-controls")).toHaveLength(1)
    expect(
      page.querySelector<HTMLButtonElement>(".shiny-chat-page-sidebar-close")!
        .hidden,
    ).toBe(true)

    media.setMatches(true)

    expect(controls.parentElement).toBe(mobileMount)
    expect(page.querySelector("#shiny-toolbar-input")).toBe(shinyInput)
    expect(shinyInput.value).toBe("live Shiny state")
    expect(
      page.querySelector<HTMLButtonElement>(".shiny-chat-page-sidebar-close")!
        .hidden,
    ).toBe(false)

    media.setMatches(false)

    expect(controls.parentElement).toBe(desktopMount)
    expect(page.querySelector("#shiny-toolbar-input")).toBe(shinyInput)
    expect(page.querySelectorAll(".shiny-chat-page-controls")).toHaveLength(1)
  })

  it("uses the toggle for the sidebar without opening a desktop dialog", () => {
    installMatchMedia(false)
    const page = pageFixture()
    const { toggle, aside } = getPageElements(page)

    toggle.click()

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
    expect(aside.hidden).toBe(true)
    expect(aside.hasAttribute("role")).toBe(false)
  })
})

describe("shiny-chat-page desktop sidebar state", () => {
  it("allows an explicitly open sidebar to be closed and reopened", () => {
    const page = pageFixture({ homeOpen: "open" })
    const { aside, toggle } = getPageElements(page)

    expect(aside.hidden).toBe(false)
    expect(toggle.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")

    toggle.click()
    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")

    toggle.click()
    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })

  it("allows an explicitly closed sidebar to be opened", () => {
    const page = pageFixture({ customOpen: "closed" })
    const { aside, navButtons, toggle } = getPageElements(page)

    navButtons[1]!.click()

    expect(aside.hidden).toBe(true)
    expect(toggle.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")

    toggle.click()
    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })

  it("keeps an always-open sidebar visible with a disabled toggle slot", () => {
    const page = pageFixture({ alwaysPage: true })
    const { aside, navButtons, toggle } = getPageElements(page)

    navButtons[3]!.click()

    expect(aside.hidden).toBe(false)
    expect(toggle.hidden).toBe(false)
    expect(toggle.disabled).toBe(true)
    expect(toggle).toHaveAttribute("aria-disabled", "true")
    expect(toggle.getAttribute("aria-expanded")).toBe("true")

    toggle.click()
    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })

  it("keeps the toggle slot disabled when the selected page has no sidebar", () => {
    const page = pageFixture()
    const { aside, navButtons, toggle } = getPageElements(page)

    navButtons[2]!.click()

    expect(aside.hidden).toBe(true)
    expect(toggle.hidden).toBe(false)
    expect(toggle.disabled).toBe(true)
    expect(toggle).toHaveAttribute("aria-disabled", "true")

    toggle.click()
    expect(aside.hidden).toBe(true)
  })

  it("opens a custom auto sidebar on desktop", () => {
    const page = pageFixture({ customOpen: "auto" })
    const { aside, navButtons, toggle } = getPageElements(page)

    navButtons[1]!.click()

    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })

  it("restores each page sidebar's user-selected open state", () => {
    const page = pageFixture({
      homeOpen: "open",
      customOpen: "closed",
      customResizable: true,
    })
    const { aside, identity, navButtons, toggle } = getPageElements(page)

    toggle.click()
    expect(aside.hidden).toBe(true)

    navButtons[1]!.click()
    expect(aside.hidden).toBe(true)
    toggle.click()
    expect(aside.hidden).toBe(false)

    identity!.click()
    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")

    navButtons[1]!.click()
    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })
})

describe("shiny-chat-page automatic history sidebar", () => {
  it("replays an initialized history snapshot when the page connects", () => {
    getHistoryStore("chat").updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(getHistoryStore("chat").listenerCount).toBe(0)
  })

  it("opens after the first delayed initialized snapshot has conversations", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
    expect(store.listenerCount).toBe(1)

    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(store.listenerCount).toBe(0)
  })

  it("keeps auto history closed for an empty initialized snapshot", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    store.updateHistory({
      enabled: true,
      conversations: [],
      activeId: null,
    })

    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
    expect(store.listenerCount).toBe(0)
  })

  it("keeps auto history closed when history is disabled", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    store.updateHistory({
      enabled: false,
      conversations,
      activeId: "first",
    })

    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
  })

  it("does not reconsider the first initialized history decision", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    store.updateHistory({
      enabled: true,
      conversations: [],
      activeId: null,
    })
    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
  })

  it("gives a user toggle before initialization precedence over history", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    toggle.click()
    toggle.click()
    expect(aside.hidden).toBe(true)
    expect(store.listenerCount).toBe(0)

    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    expect(aside.hidden).toBe(true)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
  })

  it("caches a mobile history decision and applies it on desktop", () => {
    const media = installMatchMedia(true)
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })
    const { aside, toggle } = getPageElements(page)

    store.updateHistory({
      enabled: true,
      conversations,
      activeId: "first",
    })

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")

    media.setMatches(false)

    expect(aside.hidden).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
  })

  it("removes a pending history listener when disconnected", () => {
    const store = getHistoryStore("chat")
    const page = pageFixture({ homeSidebarKey: "default" })

    expect(store.listenerCount).toBe(1)

    page.remove()

    expect(store.listenerCount).toBe(0)
  })
})

describe("shiny-chat-page sidebar resizing", () => {
  it("shows the separator only for an open resizable desktop sidebar", () => {
    const media = installMatchMedia(false)
    const page = pageFixture()
    const { navButtons, resizer, toggle } = getPageElements(page)

    expect(resizer).not.toBeNull()
    expect(resizer!.hidden).toBe(false)

    toggle.click()
    expect(resizer!.hidden).toBe(true)

    toggle.click()
    expect(resizer!.hidden).toBe(false)

    navButtons[1]!.click()
    toggle.click()
    expect(resizer!.hidden).toBe(true)

    media.setMatches(true)
    expect(resizer!.hidden).toBe(true)
  })

  it("keeps the separator available for an always-open resizable sidebar", () => {
    const page = pageFixture({ alwaysPage: true })
    const { navButtons, resizer, toggle } = getPageElements(page)

    navButtons[3]!.click()

    expect(toggle.hidden).toBe(false)
    expect(toggle.disabled).toBe(true)
    expect(resizer).not.toBeNull()
    expect(resizer!.hidden).toBe(false)
  })

  it("supports Arrow, Home, and End keyboard resizing with ARIA bounds", () => {
    const page = pageFixture({ layoutWidth: 1000 })
    const { resizer } = getPageElements(page)

    expect(resizer).not.toBeNull()
    expect(resizer).toHaveAttribute("role", "separator")
    expect(resizer).toHaveAttribute("aria-orientation", "vertical")
    expect(resizer).toHaveAttribute("aria-valuemin", "150")
    expect(resizer).toHaveAttribute("aria-valuemax", "640")
    expect(resizer).toHaveAttribute("aria-valuenow", "320")

    fireEvent.keyDown(resizer!, { key: "ArrowRight" })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "330px",
    )

    fireEvent.keyDown(resizer!, { key: "ArrowLeft" })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "320px",
    )

    fireEvent.keyDown(resizer!, { key: "Home" })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "150px",
    )
    expect(resizer).toHaveAttribute("aria-valuenow", "150")

    fireEvent.keyDown(resizer!, { key: "End" })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "640px",
    )
    expect(resizer).toHaveAttribute("aria-valuenow", "640")
    expect(resizer).toHaveAttribute("aria-valuetext", "640 pixels")
  })

  it("positions the separator from rendered width and observes container resizing", () => {
    const page = pageFixture({
      homeWidth: "900px",
      layoutWidth: 1000,
    })
    const { resizer } = getPageElements(page)
    const body = page.querySelector<HTMLElement>(".shiny-chat-page-body")!

    expect(
      page.style.getPropertyValue("--shiny-chat-page-sidebar-rendered-width"),
    ).toBe("640px")
    expect(resizer).toHaveAttribute("aria-valuenow", "640")
    expect(resizer).toHaveAttribute("aria-valuemax", "640")

    page.dataset.testLayoutWidth = "800"
    ResizeObserverStub.resize(body)

    expect(
      page.style.getPropertyValue("--shiny-chat-page-sidebar-rendered-width"),
    ).toBe("440px")
    expect(resizer).toHaveAttribute("aria-valuenow", "440")
    expect(resizer).toHaveAttribute("aria-valuemax", "440")
  })

  it("resizes by pointer and clamps to sidebar and main-area minimums", () => {
    const page = pageFixture({ layoutWidth: 1000 })
    const { resizer } = getPageElements(page)

    expect(resizer).not.toBeNull()

    fireEvent.pointerDown(resizer!, {
      pointerId: 1,
      clientX: 320,
      button: 0,
      isPrimary: true,
    })
    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 500 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "500px",
    )

    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 0 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "150px",
    )

    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 1000 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "640px",
    )
    fireEvent.pointerUp(resizer!, { pointerId: 1 })
  })

  it("accepts only one primary pointer and cancels capture on page changes", () => {
    const page = pageFixture({
      customOpen: "open",
      customResizable: true,
      layoutWidth: 1000,
    })
    const { navButtons, resizer } = getPageElements(page)

    fireEvent.pointerDown(resizer!, {
      pointerId: 1,
      clientX: 320,
      button: 2,
    })
    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 500 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "20rem",
    )

    fireEvent.pointerDown(resizer!, {
      pointerId: 1,
      clientX: 320,
      button: 0,
      isPrimary: true,
    })
    fireEvent.pointerDown(resizer!, {
      pointerId: 2,
      clientX: 320,
      button: 0,
      isPrimary: true,
    })
    fireEvent.pointerMove(resizer!, { pointerId: 2, clientX: 500 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "20rem",
    )

    navButtons[1]!.click()
    expect(resizer).not.toHaveAttribute("data-resizing")
    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 500 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "24rem",
    )
  })

  it("ends resizing when pointer capture is lost", () => {
    const page = pageFixture()
    const { resizer } = getPageElements(page)

    fireEvent.pointerDown(resizer!, {
      pointerId: 1,
      clientX: 320,
      button: 0,
      isPrimary: true,
    })
    expect(resizer).toHaveAttribute("data-resizing")

    fireEvent.lostPointerCapture(resizer!, { pointerId: 1 })

    expect(resizer).not.toHaveAttribute("data-resizing")
    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 500 })
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "20rem",
    )
  })

  it("persists resized widths independently for each sidebar panel", () => {
    const page = pageFixture({
      customOpen: "open",
      customResizable: true,
      layoutWidth: 1000,
    })
    const { identity, navButtons, resizer } = getPageElements(page)

    expect(resizer).not.toBeNull()
    fireEvent.pointerDown(resizer!, {
      pointerId: 1,
      clientX: 320,
      button: 0,
      isPrimary: true,
    })
    fireEvent.pointerMove(resizer!, { pointerId: 1, clientX: 420 })
    fireEvent.pointerUp(resizer!, { pointerId: 1 })

    navButtons[1]!.click()
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "24rem",
    )
    fireEvent.pointerDown(resizer!, {
      pointerId: 2,
      clientX: 384,
      button: 0,
      isPrimary: true,
    })
    fireEvent.pointerMove(resizer!, { pointerId: 2, clientX: 500 })
    fireEvent.pointerUp(resizer!, { pointerId: 2 })

    identity!.click()
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "420px",
    )

    navButtons[1]!.click()
    expect(page.style.getPropertyValue("--shiny-chat-page-sidebar-width")).toBe(
      "500px",
    )
  })
})

describe("shiny-chat-page mobile app menu", () => {
  it("opens as a dialog, traps focus, and closes on Escape with focus return", () => {
    installMatchMedia(true)
    const page = pageFixture()
    const { aside, toggle } = getPageElements(page)

    toggle.click()

    expect(page.dataset.mobileMenuOpen).toBe("true")
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(aside.getAttribute("role")).toBe("dialog")
    expect(aside.getAttribute("aria-modal")).toBe("true")
    expect(aside.getAttribute("tabindex")).toBe("-1")
    expect(document.activeElement).toBe(aside)
    expect(
      page.querySelectorAll(".shiny-chat-page-sidebar-scrim"),
    ).toHaveLength(1)

    const focusable = Array.from(
      aside.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), summary",
      ),
    ).filter((element) => !element.closest("[hidden]"))
    const first = focusable[0]!
    const last = aside.querySelector<HTMLElement>("summary")!

    fireEvent.keyDown(document, { key: "Tab" })
    expect(document.activeElement).toBe(first)

    first.focus()
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true })
    expect(document.activeElement).toBe(last)

    last.focus()
    fireEvent.keyDown(document, { key: "Tab" })
    expect(document.activeElement).toBe(first)

    fireEvent.keyDown(document, { key: "Escape" })

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
    expect(aside.hasAttribute("role")).toBe(false)
    expect(aside.hasAttribute("aria-modal")).toBe(false)
    expect(aside.hasAttribute("tabindex")).toBe(false)
    expect(document.activeElement).toBe(toggle)
    expect(page.querySelector(".shiny-chat-page-sidebar-scrim")).toBeNull()
  })

  it("closes on scrim click and returns focus to the toggle", () => {
    installMatchMedia(true)
    const page = pageFixture()
    const { toggle } = getPageElements(page)
    toggle.click()

    page.querySelector<HTMLElement>(".shiny-chat-page-sidebar-scrim")!.click()

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(document.activeElement).toBe(toggle)
  })

  it("provides one empty close button that closes and returns focus", () => {
    installMatchMedia(true)
    const page = pageFixture()
    const { toggle } = getPageElements(page)
    const close = page.querySelector<HTMLButtonElement>(
      ".shiny-chat-page-sidebar-close",
    )!

    expect(close.type).toBe("button")
    expect(close.getAttribute("aria-label")).toBe("Close app menu")
    expect(close.textContent).toBe("")
    expect(close.hidden).toBe(false)
    expect(
      page.querySelectorAll(".shiny-chat-page-sidebar-close"),
    ).toHaveLength(1)

    toggle.click()
    close.click()

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(document.activeElement).toBe(toggle)
  })

  it("closes on navigation and preserves the selected active state", () => {
    installMatchMedia(true)
    const page = pageFixture()
    const { toggle, navButtons } = getPageElements(page)
    toggle.click()

    navButtons[1]!.click()

    expect(page.dataset.activePage).toBe("custom-page")
    expect(navButtons[1]!.getAttribute("aria-current")).toBe("page")
    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(document.activeElement).toBe(toggle)
  })

  it("clears dialog state and returns controls to desktop on media change", () => {
    const media = installMatchMedia(true)
    const page = pageFixture()
    const { aside, controls, desktopMount, toggle } = getPageElements(page)
    toggle.click()

    media.setMatches(false)

    expect(controls.parentElement).toBe(desktopMount)
    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(aside.hasAttribute("role")).toBe(false)
    expect(aside.hasAttribute("aria-modal")).toBe(false)
    expect(page.querySelector(".shiny-chat-page-sidebar-scrim")).toBeNull()
  })

  it("cleans up listeners and scrims across disconnect and reconnect", () => {
    const media = installMatchMedia(true)
    const page = pageFixture()
    const { toggle } = getPageElements(page)
    expect(media.listenerCount()).toBe(1)

    toggle.click()
    expect(
      page.querySelectorAll(".shiny-chat-page-sidebar-scrim"),
    ).toHaveLength(1)

    page.remove()

    expect(media.listenerCount()).toBe(0)
    expect(page.querySelector(".shiny-chat-page-sidebar-scrim")).toBeNull()

    document.body.append(page)
    expect(media.listenerCount()).toBe(1)
    expect(
      page.querySelectorAll(".shiny-chat-page-sidebar-close"),
    ).toHaveLength(1)

    toggle.click()
    expect(page.dataset.mobileMenuOpen).toBe("true")
    expect(
      page.querySelectorAll(".shiny-chat-page-sidebar-scrim"),
    ).toHaveLength(1)
  })
})

describe("shiny-chat-page without secondary pages", () => {
  it("does not require an identity button when no page navigation exists", () => {
    const page = pageFixture({ identity: false, pages: false })

    expect(page.dataset.pageError).toBeUndefined()
    expect(page.querySelector("button.shiny-chat-page-identity")).toBeNull()
    expect(page.dataset.activePage).toBe("home")
    expect(
      page.querySelector<HTMLElement>(".shiny-chat-page-home")!.hidden,
    ).toBe(false)
  })

  it("keeps the mobile app menu available without a sidebar panel", () => {
    installMatchMedia(true)
    const page = pageFixture({ identity: false, pages: false, sidebar: false })
    const { aside, controls, mobileMount, toggle } = getPageElements(page)

    expect(aside.hasAttribute("data-sidebar-key")).toBe(false)
    expect(controls.parentElement).toBe(mobileMount)

    toggle.click()

    expect(page.dataset.mobileMenuOpen).toBe("true")
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(aside.getAttribute("role")).toBe("dialog")
  })
})
