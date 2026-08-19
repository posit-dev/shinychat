import { getHistoryStore } from "../chat/historyStore"

export const PAGE_MOBILE_MEDIA_QUERY = "(max-width: 799px)"

const PAGE_SELECTOR = ".shiny-chat-page-panel"
const SIDEBAR_PANEL_SELECTOR = ".shiny-chat-page-sidebar-panel"
const SIDEBAR_METADATA = ["open", "width", "resizable"] as const
const DEFAULT_SIDEBAR_KEY = "default"
const MIN_SIDEBAR_WIDTH = 150
const MIN_MAIN_WIDTH = 360
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "object",
  "embed",
  "audio[controls]",
  "video[controls]",
  "summary",
  "[contenteditable]:not([contenteditable='false'])",
  "[tabindex]:not([tabindex='-1'])",
].join(",")

type SidebarOpenMode = "auto" | "open" | "closed" | "always"

interface PageSidebarState {
  key: string
  openMode: SidebarOpenMode
  open: boolean
  width: string
  resizable: boolean
}

function sidebarOpenMode(value: string | undefined): SidebarOpenMode {
  return value === "open" ||
    value === "closed" ||
    value === "always" ||
    value === "auto"
    ? value
    : "auto"
}

function directChildrenMatching<T extends Element>(
  parent: Element,
  selector: string,
): T[] {
  return Array.from(parent.children).filter((child): child is T =>
    child.matches(selector),
  )
}

function isVisibleFocusable(element: HTMLElement, boundary: HTMLElement) {
  if (
    element.hidden ||
    element.matches(":disabled") ||
    element.getAttribute("aria-disabled") === "true" ||
    element.closest("[hidden], [inert], [aria-hidden='true']")
  ) {
    return false
  }

  const closedDetails = element.closest("details:not([open])")
  if (
    closedDetails &&
    closedDetails.querySelector(":scope > summary") !== element
  ) {
    return false
  }

  for (
    let current: HTMLElement | null = element;
    current && boundary.contains(current);
    current = current.parentElement
  ) {
    const style = window.getComputedStyle(current)
    if (style.display === "none" || style.visibility === "hidden") return false
    if (current === boundary) break
  }

  return true
}

class ChatPageElement extends HTMLElement {
  private initialized = false
  private mobile = false
  private layoutInitialized = false
  private mediaQuery: MediaQueryList | null = null
  private cleanupListeners: Array<() => void> = []

  private toggle: HTMLButtonElement | null = null
  private identity: HTMLButtonElement | null = null
  private identityReturnLabel = "Return to chat"
  private controls: HTMLElement | null = null
  private desktopMount: HTMLElement | null = null
  private mobileMount: HTMLElement | null = null
  private body: HTMLElement | null = null
  private aside: HTMLElement | null = null
  private closeButton: HTMLButtonElement | null = null
  private resizeHandle: HTMLElement | null = null
  private sections: HTMLElement[] = []
  private navButtons: HTMLButtonElement[] = []
  private sidebarPanels: HTMLElement[] = []
  private sidebarStates = new Map<string, PageSidebarState>()
  private scrim: HTMLElement | null = null
  private historyUnsubscribe: (() => void) | null = null
  private historyAutoDecided = false
  private resizePointerId: number | null = null
  private resizeSidebarKey: string | null = null
  private resizeStartX = 0
  private resizeStartWidth = 0

  connectedCallback() {
    if (this.initialized) return
    if (!this.captureDom()) return

    this.initialized = true
    this.bindInteractions()
    this.bindMediaQuery()
    this.bindResizeObserver()

    const requestedPage = this.dataset.activePage || "home"
    if (!this.selectPage(requestedPage, false)) {
      this.selectPage("home", false)
    }
    this.bindHistoryAutoOpen()
  }

  disconnectedCallback() {
    this.historyUnsubscribe?.()
    this.historyUnsubscribe = null
    this.finishSidebarResize()
    this.cleanupListeners.splice(0).forEach((cleanup) => cleanup())
    this.closeMobileMenu(false)
    this.removeScrim()
    this.mediaQuery = null
    this.layoutInitialized = false
    this.initialized = false
  }

  private captureDom() {
    delete this.dataset.pageError

    const controls = this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-controls",
    )
    const desktopMounts = this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-controls-mount-desktop",
    )
    const mobileMounts = this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-controls-mount-mobile",
    )
    const asides = this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-sidebar",
    )
    const bodies = this.querySelectorAll<HTMLElement>(".shiny-chat-page-body")
    const mains = this.querySelectorAll<HTMLElement>(".shiny-chat-page-main")
    const toggles = this.querySelectorAll<HTMLButtonElement>(
      "button.shiny-chat-page-sidebar-toggle",
    )
    const errors: string[] = []

    if (controls.length !== 1) errors.push("controls")
    if (desktopMounts.length !== 1) errors.push("desktop-mount")
    if (mobileMounts.length !== 1) errors.push("mobile-mount")
    if (asides.length !== 1) errors.push("sidebar")
    if (bodies.length !== 1) errors.push("body")
    if (mains.length !== 1) errors.push("main")
    if (toggles.length !== 1) errors.push("sidebar-toggle")

    const main = mains[0]
    const sections = main
      ? directChildrenMatching<HTMLElement>(main, PAGE_SELECTOR)
      : []
    if (
      sections.filter((section) => section.dataset.pageValue === "home")
        .length !== 1
    ) {
      errors.push("home-panel")
    }

    if (errors.length > 0) {
      this.dataset.pageError = `invalid-dom:${errors.join(",")}`
      return false
    }

    this.controls = controls[0]!
    this.desktopMount = desktopMounts[0]!
    this.mobileMount = mobileMounts[0]!
    this.body = bodies[0]!
    this.aside = asides[0]!
    this.toggle = toggles[0]!
    this.closeButton = this.captureCloseButton()
    this.resizeHandle = this.captureResizeHandle()
    this.identity = this.querySelector<HTMLButtonElement>(
      "button.shiny-chat-page-identity[data-page-home]",
    )
    this.identityReturnLabel =
      this.identity?.getAttribute("aria-label")?.trim() || "Return to chat"
    this.sections = sections
    this.navButtons = Array.from(
      this.controls.querySelectorAll<HTMLButtonElement>(
        "button.shiny-chat-page-nav-link[data-page-target]",
      ),
    )
    this.sidebarPanels = directChildrenMatching<HTMLElement>(
      this.aside,
      SIDEBAR_PANEL_SELECTOR,
    )
    this.captureSidebarStates()
    this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-sidebar-scrim",
    ).forEach((scrim) => scrim.remove())

    return true
  }

  private captureSidebarStates() {
    this.sidebarPanels.forEach((panel) => {
      const key = panel.dataset.sidebarFor?.trim()
      if (!key || this.sidebarStates.has(key)) return

      const openMode = sidebarOpenMode(panel.dataset.sidebarOpen)
      this.sidebarStates.set(key, {
        key,
        openMode,
        open:
          openMode === "open" ||
          openMode === "always" ||
          (openMode === "auto" && key !== DEFAULT_SIDEBAR_KEY),
        width: panel.dataset.sidebarWidth?.trim() || "280px",
        resizable: panel.dataset.sidebarResizable !== "false",
      })
    })
  }

  private bindInteractions() {
    if (!this.toggle) return

    this.listen(this.toggle, "click", () => {
      if (this.toggle?.disabled) return
      if (this.mobile) {
        if (this.hasAttribute("data-mobile-menu-open")) {
          this.closeMobileMenu()
        } else {
          this.openMobileMenu()
        }
        return
      }

      const state = this.activeSidebarState()
      if (!state || state.openMode === "always") return
      if (
        state.key === DEFAULT_SIDEBAR_KEY &&
        state.openMode === "auto" &&
        !this.historyAutoDecided
      ) {
        this.cancelHistoryAutoOpen()
      }
      state.open = !state.open
      this.applyDesktopSidebarState()
      window.dispatchEvent(new Event("resize"))
    })

    if (this.closeButton) {
      this.listen(this.closeButton, "click", () => {
        if (this.mobile) this.closeMobileMenu()
      })
    }

    if (this.identity) {
      this.listen(this.identity, "click", () => {
        this.selectPage("home")
      })
    }

    this.navButtons.forEach((button) => {
      this.listen(button, "click", () => {
        const target = button.dataset.pageTarget
        if (target) this.selectPage(target)
      })
    })

    const onKeyDown = (event: KeyboardEvent) => {
      if (!this.mobile || !this.hasAttribute("data-mobile-menu-open")) return
      if (event.key === "Escape") {
        event.preventDefault()
        this.closeMobileMenu()
      } else if (event.key === "Tab") {
        this.trapMobileFocus(event)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    this.cleanupListeners.push(() =>
      document.removeEventListener("keydown", onKeyDown),
    )

    if (this.resizeHandle) {
      this.listen(this.resizeHandle, "pointerdown", (event) => {
        this.onResizePointerDown(event as PointerEvent)
      })
      this.listen(this.resizeHandle, "pointermove", (event) => {
        this.onResizePointerMove(event as PointerEvent)
      })
      this.listen(this.resizeHandle, "pointerup", (event) => {
        this.onResizePointerEnd(event as PointerEvent)
      })
      this.listen(this.resizeHandle, "pointercancel", (event) => {
        this.onResizePointerEnd(event as PointerEvent)
      })
      this.listen(this.resizeHandle, "lostpointercapture", (event) => {
        this.onResizePointerEnd(event as PointerEvent)
      })
      this.listen(this.resizeHandle, "keydown", (event) => {
        this.onResizeKeyDown(event as KeyboardEvent)
      })
    }

    this.listen(window, "resize", () => this.updateResizeHandle())
  }

  private bindResizeObserver() {
    if (typeof ResizeObserver === "undefined" || !this.body || !this.aside) {
      return
    }

    const observer = new ResizeObserver(() => this.updateResizeHandle())
    observer.observe(this.body)
    observer.observe(this.aside)
    this.cleanupListeners.push(() => observer.disconnect())
  }

  private bindMediaQuery() {
    if (typeof window.matchMedia !== "function") {
      this.applyResponsiveLayout(false)
      return
    }

    this.mediaQuery = window.matchMedia(PAGE_MOBILE_MEDIA_QUERY)
    const onChange = (event: MediaQueryListEvent) => {
      this.applyResponsiveLayout(event.matches)
    }

    if (typeof this.mediaQuery.addEventListener === "function") {
      this.mediaQuery.addEventListener("change", onChange)
      this.cleanupListeners.push(() =>
        this.mediaQuery?.removeEventListener("change", onChange),
      )
    } else {
      this.mediaQuery.addListener(onChange)
      this.cleanupListeners.push(() =>
        this.mediaQuery?.removeListener(onChange),
      )
    }

    this.applyResponsiveLayout(this.mediaQuery.matches)
  }

  private applyResponsiveLayout(matches: boolean) {
    if (!this.controls || !this.desktopMount || !this.mobileMount) return

    const changed = !this.layoutInitialized || this.mobile !== matches
    const wasOpen = this.hasAttribute("data-mobile-menu-open")
    this.mobile = matches
    this.layoutInitialized = true

    const mount = matches ? this.mobileMount : this.desktopMount
    if (this.controls.parentElement !== mount) mount.append(this.controls)
    if (this.closeButton) this.closeButton.hidden = !matches

    if (!matches) {
      this.closeMobileMenu(wasOpen)
      this.applyDesktopSidebarState()
    } else if (changed) {
      this.closeMobileMenu(false)
      if (this.aside) this.aside.hidden = false
      this.updateToggleState()
      this.updateResizeHandle()
    }
  }

  private selectPage(value: string, closeMenu = true) {
    const selected = this.sections.find(
      (section) => section.dataset.pageValue === value,
    )
    if (!selected) return false
    this.finishSidebarResize()

    this.sections.forEach((section) => {
      section.hidden = section !== selected
    })
    this.dataset.activePage = value

    this.navButtons.forEach((button) => {
      if (value !== "home" && button.dataset.pageTarget === value) {
        button.setAttribute("aria-current", "page")
      } else {
        button.removeAttribute("aria-current")
      }
    })
    if (this.identity) {
      if (value === "home") {
        this.identity.setAttribute("aria-current", "page")
        this.identity.removeAttribute("aria-label")
      } else {
        this.identity.removeAttribute("aria-current")
        this.identity.setAttribute("aria-label", this.identityReturnLabel)
      }
    }

    this.syncSidebar(selected)
    if (closeMenu && this.mobile) this.closeMobileMenu()
    window.dispatchEvent(new Event("resize"))
    return true
  }

  private syncSidebar(selected: HTMLElement) {
    if (!this.aside) return

    const sidebarKey = selected.dataset.sidebarKey?.trim()
    if (sidebarKey) {
      this.aside.dataset.sidebarKey = sidebarKey
    } else {
      delete this.aside.dataset.sidebarKey
    }

    let activePanel: HTMLElement | undefined
    this.sidebarPanels.forEach((panel) => {
      const matches =
        Boolean(sidebarKey) && panel.dataset.sidebarFor === sidebarKey
      panel.hidden = !matches
      if (matches && !activePanel) activePanel = panel
    })

    SIDEBAR_METADATA.forEach((name) => {
      const attribute = `data-sidebar-${name}`
      const value = activePanel?.getAttribute(attribute)
      if (value === null || value === undefined) {
        this.aside?.removeAttribute(attribute)
      } else {
        this.aside?.setAttribute(attribute, value)
      }
    })

    const state = sidebarKey ? this.sidebarStates.get(sidebarKey) : undefined
    if (state) {
      this.aside.dataset.sidebarWidth = state.width
      this.style.setProperty("--shiny-chat-page-sidebar-width", state.width)
    } else {
      this.style.removeProperty("--shiny-chat-page-sidebar-width")
    }

    if (this.mobile) {
      this.aside.hidden = false
      this.updateToggleState()
      this.updateResizeHandle()
    } else {
      this.applyDesktopSidebarState()
    }
  }

  private applyDesktopSidebarState() {
    if (!this.toggle || !this.aside) return
    const state = this.activeSidebarState()
    const open = Boolean(state?.open)

    this.aside.hidden = !open
    if (state) {
      this.aside.dataset.sidebarWidth = state.width
      this.style.setProperty("--shiny-chat-page-sidebar-width", state.width)
    }
    this.updateToggleState()
    this.updateResizeHandle()
  }

  private updateToggleState() {
    if (!this.toggle) return
    const state = this.activeSidebarState()
    const open = this.mobile
      ? this.hasAttribute("data-mobile-menu-open")
      : Boolean(state?.open)
    const toggleDisabled =
      !this.mobile && (state?.openMode === "always" || !state)

    this.toggle.hidden = false
    this.toggle.disabled = toggleDisabled
    this.toggle.setAttribute("aria-disabled", toggleDisabled ? "true" : "false")
    this.toggle.setAttribute("aria-expanded", open ? "true" : "false")
  }

  private activeSidebarState() {
    const key = this.aside?.dataset.sidebarKey?.trim()
    return key ? this.sidebarStates.get(key) : undefined
  }

  private bindHistoryAutoOpen() {
    if (this.historyAutoDecided || this.historyUnsubscribe) return
    const state = this.sidebarStates.get(DEFAULT_SIDEBAR_KEY)
    const chatId = this.dataset.chatId?.trim()
    if (!state || state.openMode !== "auto" || !chatId) return

    const store = getHistoryStore(chatId)
    const consumeInitializedSnapshot = () => {
      const snapshot = store.getSnapshot()
      if (!snapshot.initialized || this.historyAutoDecided) return

      this.historyAutoDecided = true
      state.open = snapshot.enabled && snapshot.conversations.length > 0
      this.historyUnsubscribe?.()
      this.historyUnsubscribe = null
      if (!this.mobile && this.activeSidebarState() === state) {
        this.applyDesktopSidebarState()
        window.dispatchEvent(new Event("resize"))
      }
    }

    this.historyUnsubscribe = store.subscribe(consumeInitializedSnapshot)
    consumeInitializedSnapshot()
  }

  private cancelHistoryAutoOpen() {
    this.historyAutoDecided = true
    this.historyUnsubscribe?.()
    this.historyUnsubscribe = null
  }

  private captureResizeHandle() {
    if (!this.body) return null

    const existing = Array.from(
      this.body.querySelectorAll<HTMLElement>(
        ":scope > .shiny-chat-page-sidebar-resizer",
      ),
    )
    const handle = existing.shift() ?? document.createElement("div")
    existing.forEach((duplicate) => duplicate.remove())

    handle.className = "shiny-chat-page-sidebar-resizer"
    handle.setAttribute("role", "separator")
    handle.setAttribute("aria-label", "Resize sidebar")
    handle.setAttribute("aria-orientation", "vertical")
    handle.setAttribute("aria-keyshortcuts", "ArrowLeft ArrowRight Home End")
    handle.title = "Drag to resize sidebar"
    handle.replaceChildren()

    const indicator = document.createElement("div")
    indicator.className = "shiny-chat-page-sidebar-resize-indicator"
    const instructions = document.createElement("div")
    instructions.className = "visually-hidden"
    instructions.textContent =
      "Use arrow keys to resize the sidebar, Shift for larger steps, Home or End for minimum or maximum width."
    handle.append(indicator, instructions)
    if (!handle.isConnected) this.body.append(handle)
    return handle
  }

  private updateResizeHandle(renderedWidth?: number) {
    if (!this.resizeHandle) return
    if (this.mobile) {
      this.style.removeProperty("--shiny-chat-page-sidebar-max-width")
    } else {
      this.style.setProperty(
        "--shiny-chat-page-sidebar-max-width",
        `${this.maximumSidebarWidth()}px`,
      )
    }

    const state = this.activeSidebarState()
    const enabled =
      !this.mobile && Boolean(state?.open && state.resizable && this.aside)

    this.resizeHandle.hidden = !enabled
    this.resizeHandle.setAttribute("aria-hidden", enabled ? "false" : "true")
    if (!enabled) {
      this.resizeHandle.removeAttribute("tabindex")
      this.finishSidebarResize()
      return
    }

    const width = Math.round(renderedWidth ?? this.currentSidebarWidth())
    this.style.setProperty(
      "--shiny-chat-page-sidebar-rendered-width",
      `${width}px`,
    )
    this.resizeHandle.tabIndex = 0
    this.resizeHandle.setAttribute(
      "aria-valuemin",
      MIN_SIDEBAR_WIDTH.toString(),
    )
    this.resizeHandle.setAttribute(
      "aria-valuemax",
      this.maximumSidebarWidth().toString(),
    )
    this.resizeHandle.setAttribute("aria-valuenow", width.toString())
    this.resizeHandle.setAttribute("aria-valuetext", `${width} pixels`)
  }

  private currentSidebarWidth() {
    const measured = this.aside?.getBoundingClientRect().width ?? 0
    if (measured > 0) return measured

    const width = this.activeSidebarState()?.width
    const pixelWidth = width?.match(/^(\d+(?:\.\d+)?)px$/)
    return pixelWidth ? Number(pixelWidth[1]) : 280
  }

  private maximumSidebarWidth() {
    const available =
      this.body?.getBoundingClientRect().width ||
      this.getBoundingClientRect().width ||
      window.innerWidth
    return Math.max(MIN_SIDEBAR_WIDTH, Math.round(available - MIN_MAIN_WIDTH))
  }

  private setSidebarWidth(width: number) {
    const state = this.activeSidebarState()
    if (!state) return

    const bounded = Math.round(
      Math.min(Math.max(width, MIN_SIDEBAR_WIDTH), this.maximumSidebarWidth()),
    )
    state.width = `${bounded}px`
    if (this.aside) this.aside.dataset.sidebarWidth = state.width
    this.style.setProperty("--shiny-chat-page-sidebar-width", state.width)
    this.updateResizeHandle(bounded)
    window.dispatchEvent(new Event("resize"))
  }

  private onResizePointerDown(event: PointerEvent) {
    const state = this.activeSidebarState()
    if (
      this.mobile ||
      !state?.open ||
      !state.resizable ||
      !this.resizeHandle ||
      this.resizePointerId !== null ||
      event.button !== 0 ||
      event.isPrimary === false
    ) {
      return
    }

    event.preventDefault()
    this.resizePointerId = event.pointerId
    this.resizeSidebarKey = state.key
    this.resizeStartX = event.clientX
    this.resizeStartWidth = this.currentSidebarWidth()
    this.dataset.sidebarResizing = "true"
    this.resizeHandle.setPointerCapture?.(event.pointerId)
  }

  private onResizePointerMove(event: PointerEvent) {
    if (event.pointerId !== this.resizePointerId) return
    if (this.activeSidebarState()?.key !== this.resizeSidebarKey) {
      this.finishSidebarResize()
      return
    }
    event.preventDefault()
    this.setSidebarWidth(
      this.resizeStartWidth + (event.clientX - this.resizeStartX),
    )
  }

  private onResizePointerEnd(event: PointerEvent) {
    if (event.pointerId !== this.resizePointerId) return
    this.finishSidebarResize()
  }

  private finishSidebarResize() {
    if (this.resizePointerId === null) return
    const pointerId = this.resizePointerId
    this.resizePointerId = null
    this.resizeSidebarKey = null
    if (this.resizeHandle?.hasPointerCapture?.(pointerId)) {
      this.resizeHandle.releasePointerCapture(pointerId)
    }
    delete this.dataset.sidebarResizing
  }

  private onResizeKeyDown(event: KeyboardEvent) {
    const state = this.activeSidebarState()
    if (this.mobile || !state?.open || !state.resizable) return

    const step = event.shiftKey ? 50 : 10
    let width = this.currentSidebarWidth()
    switch (event.key) {
      case "ArrowLeft":
        width -= step
        break
      case "ArrowRight":
        width += step
        break
      case "Home":
        width = MIN_SIDEBAR_WIDTH
        break
      case "End":
        width = this.maximumSidebarWidth()
        break
      default:
        return
    }

    event.preventDefault()
    this.setSidebarWidth(width)
  }

  private openMobileMenu() {
    if (!this.mobile || !this.aside || !this.toggle) return

    this.setAttribute("data-mobile-menu-open", "true")
    this.toggle.setAttribute("aria-expanded", "true")
    this.aside.setAttribute("role", "dialog")
    this.aside.setAttribute("aria-modal", "true")
    this.aside.setAttribute("tabindex", "-1")
    this.ensureScrim()
    this.aside.focus({ preventScroll: true })
  }

  private closeMobileMenu(restoreFocus = true) {
    const wasOpen = this.hasAttribute("data-mobile-menu-open")
    this.removeAttribute("data-mobile-menu-open")
    this.toggle?.setAttribute("aria-expanded", "false")
    this.aside?.removeAttribute("role")
    this.aside?.removeAttribute("aria-modal")
    this.aside?.removeAttribute("tabindex")
    this.removeScrim()

    if (wasOpen && restoreFocus && this.toggle?.isConnected) {
      this.toggle.focus({ preventScroll: true })
    }
  }

  private ensureScrim() {
    if (this.scrim?.isConnected || !this.aside) return

    const scrim = document.createElement("div")
    scrim.className = "shiny-chat-page-sidebar-scrim"
    scrim.addEventListener("click", this.onScrimClick)
    this.aside.parentElement?.insertBefore(scrim, this.aside)
    this.scrim = scrim
  }

  private captureCloseButton() {
    if (!this.aside) return null

    const existing = Array.from(
      this.aside.querySelectorAll<HTMLButtonElement>(
        ":scope > button.shiny-chat-page-sidebar-close",
      ),
    )
    const button = existing.shift() ?? document.createElement("button")
    existing.forEach((duplicate) => duplicate.remove())

    button.type = "button"
    button.className = "shiny-chat-page-sidebar-close"
    button.setAttribute("aria-label", "Close app menu")
    button.replaceChildren()
    if (!button.isConnected) this.aside.prepend(button)
    return button
  }

  private removeScrim() {
    if (!this.scrim) return
    this.scrim.removeEventListener("click", this.onScrimClick)
    this.scrim.remove()
    this.scrim = null
  }

  private readonly onScrimClick = () => {
    this.closeMobileMenu()
  }

  private trapMobileFocus(event: KeyboardEvent) {
    if (!this.aside) return

    const focusable = Array.from(
      this.aside.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((element) => isVisibleFocusable(element, this.aside!))
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement

    if (!first || !last) {
      event.preventDefault()
      this.aside.focus()
      return
    }

    if (
      event.shiftKey &&
      (active === first ||
        active === this.aside ||
        !this.aside.contains(active))
    ) {
      event.preventDefault()
      last.focus()
    } else if (
      !event.shiftKey &&
      (active === last || active === this.aside || !this.aside.contains(active))
    ) {
      event.preventDefault()
      first.focus()
    }
  }

  private listen(target: EventTarget, type: string, listener: EventListener) {
    target.addEventListener(type, listener)
    this.cleanupListeners.push(() => target.removeEventListener(type, listener))
  }
}

if (!customElements.get("shiny-chat-page")) {
  customElements.define("shiny-chat-page", ChatPageElement)
}
