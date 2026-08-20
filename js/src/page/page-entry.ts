import { getHistoryStore } from "../chat/historyStore"
import {
  createResizeHandle,
  type ResizeHandleElement,
  type ResizeRequestDetail,
} from "../resize-handle"

export const PAGE_MOBILE_MEDIA_QUERY = "(max-width: 799px)"

const PAGE_SELECTOR = ".shiny-chat-page-panel"
const SIDEBAR_PANEL_SELECTOR = ".shiny-chat-page-sidebar-panel"
const SIDEBAR_METADATA = ["open", "width", "resizable"] as const
const DEFAULT_SIDEBAR_KEY = "default"
const MIN_SIDEBAR_WIDTH = 150
const MIN_MAIN_WIDTH = 360
const SIDEBAR_MOTION_DURATION = 180
const TOAST_OFFSET_PROPERTY = "--shiny-chat-page-toast-offset"
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

interface BootstrapTooltip {
  dispose: () => void
  setContent: (content: Record<string, HTMLElement>) => void
}

interface BootstrapTooltipConstructor {
  new (
    element: Element,
    config: {
      html: boolean
      placement: string
      title: HTMLElement
    },
  ): BootstrapTooltip
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
  private static toastOffsetOwner: ChatPageElement | null = null

  private initialized = false
  private mobile = false
  private layoutInitialized = false
  private mediaQuery: MediaQueryList | null = null
  private cleanupListeners: Array<() => void> = []

  private toggle: HTMLButtonElement | null = null
  private identity: HTMLButtonElement | null = null
  private identityTooltip: BootstrapTooltip | null = null
  private identityTitleObserver: MutationObserver | null = null
  private identityTitle: HTMLElement | null = null
  private mobileHomeLink: HTMLButtonElement | null = null
  private identityReturnLabel = "Return to chat"
  private header: HTMLElement | null = null
  private controls: HTMLElement | null = null
  private toolbarScoped: HTMLElement | null = null
  private toolbarGlobal: HTMLElement | null = null
  private toolbarSources = new Map<string, HTMLElement>()
  private activeToolbarSource: HTMLElement | null = null
  private desktopMount: HTMLElement | null = null
  private mobileMount: HTMLElement | null = null
  private body: HTMLElement | null = null
  private aside: HTMLElement | null = null
  private closeButton: HTMLButtonElement | null = null
  private resizeHandle: ResizeHandleElement | null = null
  private sections: HTMLElement[] = []
  private navButtons: HTMLButtonElement[] = []
  private sidebarPanels: HTMLElement[] = []
  private sidebarStates = new Map<string, PageSidebarState>()
  private scrim: HTMLElement | null = null
  private historyUnsubscribe: (() => void) | null = null
  private sidebarMutationObserver: MutationObserver | null = null
  private historyAutoDecided = false
  private resizingSidebarKey: string | null = null
  private sidebarMotionFrame: number | null = null
  private sidebarMotionTimer: number | null = null

  connectedCallback() {
    if (this.initialized) return
    if (!this.captureDom()) return

    this.initialized = true
    this.initializeIdentityTooltip()
    this.bindInteractions()
    this.bindMediaQuery()
    this.bindResizeObserver()

    const requestedPage = this.dataset.activePage || "home"
    if (!this.selectPage(requestedPage, false)) {
      this.selectPage("home", false)
    }
    this.bindHistoryAutoOpen()
    this.sidebarMotionFrame = window.requestAnimationFrame(() => {
      this.sidebarMotionFrame = null
      this.setAttribute("data-sidebar-motion-ready", "")
    })
  }

  disconnectedCallback() {
    this.identityTooltip?.dispose()
    this.identityTooltip = null
    this.identityTitleObserver?.disconnect()
    this.identityTitleObserver = null
    this.historyUnsubscribe?.()
    this.historyUnsubscribe = null
    this.cleanupListeners.splice(0).forEach((cleanup) => cleanup())
    this.closeMobileMenu(false)
    this.removeScrim()
    this.cancelSidebarMotion()
    this.mediaQuery = null
    this.layoutInitialized = false
    this.initialized = false
    if (ChatPageElement.toastOffsetOwner === this) {
      document.documentElement.style.removeProperty(TOAST_OFFSET_PROPERTY)
      ChatPageElement.toastOffsetOwner = null
    }
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
    const headers = this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-header",
    )
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
    if (headers.length !== 1) errors.push("header")
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
    this.header = headers[0]!
    this.toolbarScoped = this.controls.querySelector<HTMLElement>(
      ".shiny-chat-page-toolbar-scoped",
    )
    this.toolbarGlobal = this.controls.querySelector<HTMLElement>(
      ".shiny-chat-page-toolbar-global",
    )
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
    this.identityTitle =
      this.identity?.querySelector<HTMLElement>(
        ".shiny-chat-page-identity-title",
      ) ?? null
    this.captureMobileHomeLink()
    this.identityReturnLabel =
      this.identity?.getAttribute("aria-label")?.trim() || "Return to chat"
    this.sections = sections
    this.navButtons = Array.from(
      this.controls.querySelectorAll<HTMLButtonElement>(
        "button.shiny-chat-page-nav-link[data-page-target]:not(.shiny-chat-page-home-link)",
      ),
    )
    this.captureToolbarSources()
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

  private captureToolbarSources() {
    this.toolbarSources.clear()
    this.querySelectorAll<HTMLElement>(
      ".shiny-chat-page-toolbar-source[data-page-toolbar-source]",
    ).forEach((source) => {
      const key = source.dataset.pageToolbarSource?.trim()
      if (!key || this.toolbarSources.has(key)) return
      this.toolbarSources.set(key, source)
    })
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

    if (this.mobileHomeLink) {
      this.listen(this.mobileHomeLink, "click", () => {
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
      this.listen(this.resizeHandle, "resize-request", (event) => {
        this.setSidebarWidth(
          (event as CustomEvent<ResizeRequestDetail>).detail.value,
        )
      })
      this.listen(this.resizeHandle, "resize-start", () => {
        this.resizingSidebarKey = this.activeSidebarState()?.key ?? null
        this.setAttribute("data-sidebar-resizing", "")
      })
      this.listen(this.resizeHandle, "resize-end", () => {
        this.resizingSidebarKey = null
        this.removeAttribute("data-sidebar-resizing")
      })
    }

    this.listen(window, "resize", () => {
      this.updateResizeHandle()
      this.updateToastOffset()
    })
  }

  private bindResizeObserver() {
    if (
      typeof ResizeObserver === "undefined" ||
      !this.body ||
      !this.aside ||
      !this.header
    ) {
      return
    }

    const observer = new ResizeObserver(() => {
      this.updateResizeHandle()
      this.updateToastOffset()
    })
    observer.observe(this.body)
    observer.observe(this.aside)
    observer.observe(this.header)
    this.cleanupListeners.push(() => observer.disconnect())

    // The outer box does not change when asynchronous sidebar output grows.
    // Observe content mutations so fit-content can refresh its intrinsic width.
    const mutations = new MutationObserver(() => this.updateResizeHandle())
    this.sidebarMutationObserver = mutations
    this.observeSidebarMutations()
    this.cleanupListeners.push(() => {
      mutations.disconnect()
      if (this.sidebarMutationObserver === mutations) {
        this.sidebarMutationObserver = null
      }
    })
  }

  private observeSidebarMutations() {
    if (!this.sidebarMutationObserver || !this.aside) return
    this.sidebarMutationObserver.observe(this.aside, {
      childList: true,
      characterData: true,
      subtree: true,
    })
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
    if (matches) {
      this.setAttribute("data-responsive-takeover", "")
      this.cancelSidebarMotion()
    } else {
      this.removeAttribute("data-responsive-takeover")
      if (changed) this.suppressSidebarMotionThroughNextFrame()
    }
    this.mobile = matches
    this.layoutInitialized = true
    this.updateMobileHomeLink()

    const mount = matches ? this.mobileMount : this.desktopMount
    if (this.controls.parentElement !== mount) mount.append(this.controls)
    if (this.closeButton) this.closeButton.hidden = !matches

    if (!matches) {
      this.closeMobileMenu(wasOpen)
      this.applyDesktopSidebarState()
    } else if (changed) {
      this.closeMobileMenu(false)
      if (this.aside) {
        this.aside.hidden = false
        this.aside.removeAttribute("inert")
        this.aside.setAttribute("aria-hidden", "false")
      }
      this.updateToggleState()
      this.updateResizeHandle()
    }
    this.updateToastOffset()
  }

  private selectPage(value: string, closeMenu = true) {
    const selected = this.sections.find(
      (section) => section.dataset.pageValue === value,
    )
    if (!selected) return false
    this.cancelSidebarResize()
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
      this.updateIdentityTooltip()
    }
    if (this.mobileHomeLink) {
      if (value === "home") {
        this.mobileHomeLink.setAttribute("aria-current", "page")
      } else {
        this.mobileHomeLink.removeAttribute("aria-current")
      }
    }

    this.syncSidebar(selected)
    this.syncToolbar(selected)
    if (closeMenu && this.mobile) this.closeMobileMenu()
    this.updateToastOffset()
    window.dispatchEvent(new Event("resize"))
    return true
  }

  private initializeIdentityTooltip() {
    const identity = this.identity
    const title = this.identityTitle
    if (!identity || !title) return

    this.identityTitleObserver = new MutationObserver(() => {
      this.updateIdentityTooltip()
      this.updateMobileHomeLink()
    })
    this.identityTitleObserver.observe(title, {
      childList: true,
      characterData: true,
      subtree: true,
    })

    const Tooltip = (
      window as Window & {
        bootstrap?: { Tooltip?: BootstrapTooltipConstructor }
      }
    ).bootstrap?.Tooltip
    if (!Tooltip) return

    this.identityTooltip = new Tooltip(identity, {
      html: true,
      placement: "bottom",
      title: this.identityTooltipContent(),
    })
  }

  private identityTooltipContent() {
    const content = document.createElement("span")
    if (this.dataset.activePage !== "home") {
      content.append(this.identityReturnLabel, document.createElement("br"))
    }
    content.append(this.mobileHomeLabel())
    return content
  }

  private updateIdentityTooltip() {
    this.identityTooltip?.setContent({
      ".tooltip-inner": this.identityTooltipContent(),
    })
  }

  private captureMobileHomeLink() {
    const nav = this.controls?.querySelector<HTMLElement>(
      ".shiny-chat-page-nav",
    )
    const existing = nav?.querySelector<HTMLButtonElement>(
      "button.shiny-chat-page-home-link",
    )
    this.mobileHomeLink = null

    if (!this.identity || !nav) {
      existing?.remove()
      return
    }

    const link = existing ?? document.createElement("button")
    link.type = "button"
    link.className = "shiny-chat-page-nav-link shiny-chat-page-home-link"
    link.dataset.pageTarget = "home"
    let title = link.querySelector<HTMLElement>(".shiny-chat-page-nav-title")
    if (!title) {
      title = document.createElement("span")
      title.className = "shiny-chat-page-nav-title"
      link.append(title)
    }
    if (!link.isConnected) nav.prepend(link)
    this.mobileHomeLink = link
    this.updateMobileHomeLink()
  }

  private updateMobileHomeLink() {
    if (!this.mobileHomeLink) return

    const label = this.mobileHomeLabel()
    const title = this.mobileHomeLink.querySelector<HTMLElement>(
      ".shiny-chat-page-nav-title",
    )
    if (title) title.textContent = label
    this.mobileHomeLink.hidden = !this.mobile
  }

  private mobileHomeLabel() {
    return this.identityTitle?.textContent?.trim() || "Home"
  }

  private updateToastOffset() {
    const bottom = this.header?.getBoundingClientRect().bottom
    if (!bottom || !Number.isFinite(bottom)) return

    document.documentElement.style.setProperty(
      TOAST_OFFSET_PROPERTY,
      `${Math.ceil(bottom)}px`,
    )
    ChatPageElement.toastOffsetOwner = this
  }

  private syncToolbar(selected: HTMLElement) {
    if (!this.toolbarScoped || this.toolbarSources.size === 0) return

    const key = selected.dataset.pageToolbarSource?.trim()
    const desired = key ? this.toolbarSources.get(key) : undefined
    if (desired === this.activeToolbarSource) return

    if (this.activeToolbarSource) {
      this.activeToolbarSource.append(...this.toolbarScoped.childNodes)
    } else {
      this.toolbarScoped.replaceChildren()
    }
    this.activeToolbarSource = null

    if (!desired) return
    const content = desired.querySelector<HTMLElement>(
      ":scope > .shiny-chat-page-toolbar-content",
    )
    if (!content) return

    this.toolbarScoped.append(content)
    this.activeToolbarSource = desired
  }

  private syncSidebar(selected: HTMLElement) {
    if (!this.aside) return

    // Do not carry a prior sidebar's rendered target into the next selection.
    // updateResizeHandle() reseeds this from the newly active configuration.
    this.style.removeProperty("--shiny-chat-page-sidebar-rendered-width")
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
      this.aside.removeAttribute("inert")
      this.aside.setAttribute("aria-hidden", "false")
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

    if (state) {
      this.aside.dataset.sidebarWidth = state.width
      this.style.setProperty("--shiny-chat-page-sidebar-width", state.width)
    }
    this.presentDesktopSidebar(open)
    this.updateToggleState()
    this.updateResizeHandle()
  }

  private presentDesktopSidebar(open: boolean) {
    if (!this.aside) return
    this.cancelSidebarMotion()

    if (open) {
      this.aside.hidden = false
      this.aside.removeAttribute("inert")
      this.aside.setAttribute("aria-hidden", "false")
      const reveal = () => {
        this.sidebarMotionFrame = null
        if (!this.mobile && this.activeSidebarState()?.open) {
          this.setAttribute("data-sidebar-open", "")
        }
      }
      if (this.shouldAnimateSidebar()) {
        this.sidebarMotionFrame = window.requestAnimationFrame(reveal)
      } else {
        reveal()
      }
      return
    }

    this.removeAttribute("data-sidebar-open")
    this.aside.setAttribute("aria-hidden", "true")
    this.aside.setAttribute("inert", "")
    if (!this.shouldAnimateSidebar()) {
      this.aside.hidden = true
      return
    }

    this.sidebarMotionTimer = window.setTimeout(() => {
      this.sidebarMotionTimer = null
      if (!this.hasAttribute("data-sidebar-open")) this.aside!.hidden = true
    }, SIDEBAR_MOTION_DURATION)
  }

  private shouldAnimateSidebar() {
    const reducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    return (
      this.hasAttribute("data-sidebar-motion-ready") &&
      !this.mobile &&
      !this.hasAttribute("data-responsive-takeover") &&
      !this.hasAttribute("data-sidebar-handoff") &&
      !reducedMotion
    )
  }

  private cancelSidebarMotion() {
    if (this.sidebarMotionFrame !== null) {
      window.cancelAnimationFrame(this.sidebarMotionFrame)
      this.sidebarMotionFrame = null
    }
    if (this.sidebarMotionTimer !== null) {
      window.clearTimeout(this.sidebarMotionTimer)
      this.sidebarMotionTimer = null
    }
  }

  private suppressSidebarMotionThroughNextFrame() {
    this.setAttribute("data-sidebar-handoff", "")
    window.requestAnimationFrame(() => {
      this.removeAttribute("data-sidebar-handoff")
    })
  }

  private updateToggleState() {
    if (!this.toggle || !this.aside) return
    const state = this.activeSidebarState()
    const available = this.mobile
      ? this.hasMobileMenuContent()
      : this.sidebarStates.size > 0
    const toggleDisabled =
      available && !this.mobile && (state?.openMode === "always" || !state)
    const open =
      available &&
      (this.mobile
        ? this.hasAttribute("data-mobile-menu-open")
        : Boolean(state?.open))
    const alwaysOpen = !this.mobile && state?.openMode === "always"
    const unavailable = toggleDisabled && !alwaysOpen
    const toggleLabel = alwaysOpen
      ? "App menu is always open"
      : unavailable
        ? "App menu unavailable on this page"
        : "Toggle app menu"

    this.toggle.hidden = !available
    this.header?.toggleAttribute("data-sidebar-toggle-hidden", !available)
    this.toggle.disabled = toggleDisabled
    this.toggle.setAttribute("aria-disabled", toggleDisabled ? "true" : "false")
    this.toggle.setAttribute("aria-expanded", open ? "true" : "false")
    this.toggle.setAttribute("aria-label", toggleLabel)
    if (unavailable) {
      this.toggle.setAttribute("title", toggleLabel)
      this.toggle.removeAttribute("aria-controls")
    } else {
      if (alwaysOpen) {
        this.toggle.setAttribute("title", toggleLabel)
      } else {
        this.toggle.removeAttribute("title")
      }
      this.toggle.setAttribute("aria-controls", this.aside.id)
    }
  }

  private hasMobileMenuContent() {
    return (
      this.sidebarStates.size > 0 ||
      this.navButtons.length > 0 ||
      this.hasMeaningfulContent(this.toolbarGlobal) ||
      this.hasMeaningfulContent(
        this.toolbarScoped?.querySelector<HTMLElement>(
          ":scope > .shiny-chat-page-toolbar-content",
        ) ?? null,
      ) ||
      Array.from(this.toolbarSources.values()).some((source) =>
        this.hasMeaningfulContent(
          source.querySelector<HTMLElement>(
            ":scope > .shiny-chat-page-toolbar-content",
          ),
        ),
      ) ||
      Boolean(this.mobileHomeLink)
    )
  }

  private hasMeaningfulContent(element: HTMLElement | null) {
    return Boolean(element?.children.length || element?.textContent?.trim())
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

  private captureResizeHandle(): ResizeHandleElement | null {
    if (!this.body) return null

    const existing = Array.from(
      this.body.querySelectorAll<ResizeHandleElement>(
        ":scope > .shiny-chat-page-sidebar-resizer",
      ),
    )
    const handle =
      existing.shift() ?? createResizeHandle({ boundaryActivation: true })
    existing.forEach((duplicate) => duplicate.remove())

    handle.className = "shiny-chat-page-sidebar-resizer"
    if (!handle.isConnected) this.body.append(handle)
    return handle
  }

  private updateResizeHandle() {
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
    const maximum = this.maximumSidebarWidth()
    const width = Math.round(
      Math.min(
        Math.max(this.requestedSidebarWidth(), MIN_SIDEBAR_WIDTH),
        maximum,
      ),
    )
    this.style.setProperty(
      "--shiny-chat-page-sidebar-rendered-width",
      `${width}px`,
    )
    this.resizeHandle.configure({
      value: width,
      min: MIN_SIDEBAR_WIDTH,
      max: maximum,
      panelSide: "inline-end",
      disabled: !enabled,
      label: "Resize sidebar",
      boundaryActivation: true,
    })
    if (!enabled) {
      return
    }
  }

  private requestedSidebarWidth() {
    const configured = this.activeSidebarState()?.width ?? "280px"
    const pixels = configured.match(/^\s*(\d+(?:\.\d+)?)px\s*$/i)
    if (pixels) return Number.parseFloat(pixels[1]!)

    const rem = configured.match(/^\s*(\d+(?:\.\d+)?)rem\s*$/i)
    if (rem) {
      const rootSize = Number.parseFloat(
        window.getComputedStyle(document.documentElement).fontSize,
      )
      return (
        Number.parseFloat(rem[1]!) * (Number.isFinite(rootSize) ? rootSize : 16)
      )
    }

    const percent = configured.match(/^\s*(\d+(?:\.\d+)?)%\s*$/)
    if (percent) {
      const available = this.body?.getBoundingClientRect().width ?? 0
      if (available > 0)
        return (available * Number.parseFloat(percent[1]!)) / 100
    }

    if (configured.trim().toLowerCase() === "fit-content") {
      const panel = this.aside?.querySelector<HTMLElement>(
        ".shiny-chat-page-sidebar-panel:not([hidden])",
      )
      if (panel) {
        const probe = panel.cloneNode(true) as HTMLElement
        probe.dataset.shinyChatSidebarMeasurement = ""
        probe
          .querySelectorAll("[id]")
          .forEach((element) => element.removeAttribute("id"))
        probe.style.cssText =
          "position:fixed;visibility:hidden;pointer-events:none;contain:layout style;inline-size:max-content;block-size:auto;inset:0 auto auto -10000px;"
        // Keep the probe out of flow but under the real sidebar so inherited
        // page variables, such as the configured sidebar padding, apply.
        this.sidebarMutationObserver?.disconnect()
        let measured = 0
        try {
          this.aside?.append(probe)
          measured = probe.getBoundingClientRect().width
        } finally {
          probe.remove()
          this.observeSidebarMutations()
        }
        if (measured > 0) return measured
      }
    }

    // Resolve uncommon valid CSS widths against the stable page body, never
    // the sidebar whose geometry changes while the reveal animation runs.
    if (this.body) {
      const probe = document.createElement("div")
      probe.style.cssText =
        "position:absolute;visibility:hidden;pointer-events:none;contain:layout style;inline-size:auto;block-size:0;overflow:hidden;"
      probe.style.width = configured
      this.body.append(probe)
      const measured = probe.getBoundingClientRect().width
      probe.remove()
      if (measured > 0) return measured
    }

    return 280
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
    this.updateResizeHandle()
    window.dispatchEvent(new Event("resize"))
  }

  private cancelSidebarResize() {
    if (!this.resizeHandle || !this.resizingSidebarKey) return

    this.resizeHandle.configure({
      value: this.currentSidebarWidth(),
      min: MIN_SIDEBAR_WIDTH,
      max: this.maximumSidebarWidth(),
      panelSide: "inline-end",
      disabled: true,
      label: "Resize sidebar",
      boundaryActivation: true,
    })
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
        [
          ":scope > button.shiny-chat-page-sidebar-close",
          ":scope > .bslib-toolbar button.shiny-chat-page-sidebar-close",
        ].join(", "),
      ),
    )
    const button = existing.shift() ?? document.createElement("button")
    existing.forEach((duplicate) => duplicate.remove())

    button.type = "button"
    if (!button.isConnected) {
      button.className = "shiny-chat-page-sidebar-close"
      button.setAttribute("aria-label", "Close app menu")
      this.aside.prepend(button)
    }
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
