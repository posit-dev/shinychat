export const PAGE_MOBILE_MEDIA_QUERY = "(max-width: 799px)"

const PAGE_SELECTOR = ".shiny-chat-page-panel"
const SIDEBAR_PANEL_SELECTOR = ".shiny-chat-page-sidebar-panel"
const SIDEBAR_METADATA = ["open", "width", "resizable"] as const
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
  private aside: HTMLElement | null = null
  private closeButton: HTMLButtonElement | null = null
  private sections: HTMLElement[] = []
  private navButtons: HTMLButtonElement[] = []
  private sidebarPanels: HTMLElement[] = []
  private scrim: HTMLElement | null = null

  connectedCallback() {
    if (this.initialized) return
    if (!this.captureDom()) return

    this.initialized = true
    this.bindInteractions()
    this.bindMediaQuery()

    const requestedPage = this.dataset.activePage || "home"
    if (!this.selectPage(requestedPage, false)) {
      this.selectPage("home", false)
    }
  }

  disconnectedCallback() {
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
    const mains = this.querySelectorAll<HTMLElement>(".shiny-chat-page-main")
    const toggles = this.querySelectorAll<HTMLButtonElement>(
      "button.shiny-chat-page-sidebar-toggle",
    )
    const errors: string[] = []

    if (controls.length !== 1) errors.push("controls")
    if (desktopMounts.length !== 1) errors.push("desktop-mount")
    if (mobileMounts.length !== 1) errors.push("mobile-mount")
    if (asides.length !== 1) errors.push("sidebar")
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
    this.aside = asides[0]!
    this.toggle = toggles[0]!
    this.closeButton = this.captureCloseButton()
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
    this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-sidebar-scrim",
    ).forEach((scrim) => scrim.remove())

    return true
  }

  private bindInteractions() {
    if (!this.toggle) return

    this.listen(this.toggle, "click", () => {
      if (!this.mobile) return
      if (this.hasAttribute("data-mobile-menu-open")) {
        this.closeMobileMenu()
      } else {
        this.openMobileMenu()
      }
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
      this.syncDesktopToggleState()
    } else if (changed) {
      this.closeMobileMenu(false)
    }
  }

  private selectPage(value: string, closeMenu = true) {
    const selected = this.sections.find(
      (section) => section.dataset.pageValue === value,
    )
    if (!selected) return false

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

    const width = activePanel?.dataset.sidebarWidth?.trim()
    if (width) {
      this.style.setProperty("--shiny-chat-page-sidebar-width", width)
    } else {
      this.style.removeProperty("--shiny-chat-page-sidebar-width")
    }

    if (!this.mobile) this.syncDesktopToggleState()
  }

  private syncDesktopToggleState() {
    if (!this.toggle || !this.aside) return
    const configuredOpen = this.aside.dataset.sidebarOpen
    this.toggle.setAttribute(
      "aria-expanded",
      configuredOpen === "open" || configuredOpen === "always"
        ? "true"
        : "false",
    )
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
