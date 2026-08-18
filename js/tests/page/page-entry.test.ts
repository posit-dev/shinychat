import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent } from "@testing-library/react"
import { PAGE_MOBILE_MEDIA_QUERY } from "../../src/page/page-entry"

type MediaListener = (event: MediaQueryListEvent) => void

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
}: {
  identity?: boolean
  pages?: boolean
  sidebar?: boolean
} = {}) {
  const page = document.createElement("shiny-chat-page")
  page.dataset.activePage = "home"
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
                `
                : ""
            }
          </nav>
          <div class="shiny-chat-page-toolbar">
            <input id="shiny-toolbar-input" value="initial">
          </div>
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
                data-sidebar-open="open"
                data-sidebar-width="20rem"
                data-sidebar-resizable="true"
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
          data-sidebar-open="closed"
          data-sidebar-width="24rem"
          data-sidebar-resizable="false"
          hidden
        >
          <button type="button">Custom action</button>
        </div>
      </aside>
      <main class="shiny-chat-page-main">
        <section
          class="shiny-chat-page-panel shiny-chat-page-home"
          data-page-value="home"
          ${sidebar ? 'data-sidebar-key="home"' : ""}
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
                hidden
              >Default page</section>
              <section
                class="shiny-chat-page-panel"
                data-page-value="custom-page"
                data-sidebar-key="page-2"
                hidden
              >Custom page</section>
              <section
                class="shiny-chat-page-panel"
                data-page-value="no-sidebar"
                hidden
              >No sidebar page</section>
            `
            : ""
        }
      </main>
    </div>
  `
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
  }
}

beforeEach(() => {
  installMatchMedia(false)
})

afterEach(() => {
  document.body.replaceChildren()
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

  it("does not open the app menu in desktop mode", () => {
    installMatchMedia(false)
    const page = pageFixture()
    const { toggle, aside } = getPageElements(page)

    toggle.click()

    expect(page.hasAttribute("data-mobile-menu-open")).toBe(false)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(aside.hasAttribute("role")).toBe(false)
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
