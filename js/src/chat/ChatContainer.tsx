import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useSyncExternalStore,
} from "react"
import { createPortal } from "react-dom"
import { useStickToBottom } from "use-stick-to-bottom"
import { ChatMessages } from "./ChatMessages"
import { ChatGreeting } from "./ChatGreeting"
import { ChatInput, type ChatInputHandle } from "./ChatInput"
import { ScrollToBottomButton } from "./ScrollToBottomButton"
import { ExternalLinkDialogComponent } from "./ExternalLinkDialog"
import { RawDOM } from "./RawDOM"
import { DRAWER_TAKEOVER_WIDTH, ChatDrawer } from "./ChatDrawer"
import {
  ChatScrollContext,
  SlashCommandsContext,
  useChatDispatch,
} from "./context"
import {
  ChatHistoryContent,
  ChatHistoryDrawer,
  HistoryIcon,
} from "./ChatHistoryDrawer"
import type { HistoryStore } from "./historyStore"
import { useFillPaddingTransfer } from "./useFillPaddingTransfer"
import { useOverlapNudge } from "./useOverlapNudge"
import type { ChatDrawerState, ChatMessageData, GreetingData } from "./state"
import type { ChatTransport, SlashCommandDef } from "../transport/types"
import type { SubmitKey } from "./tiptap/submitShortcut"
import type { AttachmentPayload } from "./attachments"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

const DEFAULT_DRAWER_LAYOUT_WIDTH = 400
const MIN_DRAWER_LAYOUT_WIDTH = 240
const MIN_CHAT_LAYOUT_WIDTH = 360
const MAX_DRAWER_LAYOUT_GAP = 24

function openLink(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer")
}

function resolveDrawerLayoutWidth(
  configuredWidth: string,
  layout: HTMLElement,
  probe: HTMLElement | null,
): string {
  const layoutWidth = layout.getBoundingClientRect().width
  if (layoutWidth <= 0) return `${DEFAULT_DRAWER_LAYOUT_WIDTH}px`

  const pixels = /^\s*(\d+(?:\.\d+)?)px\s*$/i.exec(configuredWidth)
  const percent = /^\s*(\d+(?:\.\d+)?)%\s*$/.exec(configuredWidth)
  let requested = pixels
    ? Number.parseFloat(pixels[1]!)
    : percent
      ? (layoutWidth * Number.parseFloat(percent[1]!)) / 100
      : NaN

  if (!Number.isFinite(requested)) {
    requested = probe?.getBoundingClientRect().width ?? NaN
  }

  if (!Number.isFinite(requested) || requested <= 0) {
    requested = DEFAULT_DRAWER_LAYOUT_WIDTH
  }

  const maximum = Math.max(
    MIN_DRAWER_LAYOUT_WIDTH,
    layoutWidth - MIN_CHAT_LAYOUT_WIDTH - MAX_DRAWER_LAYOUT_GAP,
  )
  return `${Math.round(
    Math.min(Math.max(requested, MIN_DRAWER_LAYOUT_WIDTH), maximum),
  )}px`
}

function DrawerRevealIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="currentColor"
      className="bi bi-layout-sidebar-inset-reverse"
    >
      <path d="M2 2a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1zm12-1a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2z" />
      <path d="M13 4a1 1 0 0 0-1-1h-2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1z" />
    </svg>
  )
}

function pageOwnsHistory(elementId: string): boolean {
  const chat = document.getElementById(elementId)
  const page = chat?.closest("shiny-chat-page")
  if (!page) return false

  return Array.from(
    page.querySelectorAll("aside.shiny-chat-page-sidebar shiny-chat-history"),
  ).some((history) => {
    if (history.getAttribute("for") !== elementId) return false

    // Navigation sidebars remain mounted so their Shiny inputs retain state.
    // Only the active sidebar can replace the embedded history trigger.
    const panel = history.closest<HTMLElement>(".shiny-chat-page-sidebar-panel")
    return panel === null || !panel.hidden
  })
}

export interface ChatContainerProps {
  transport: ChatTransport
  messages: ChatMessageData[]
  streamingMessage: ChatMessageData | null
  inputDisabled: boolean
  inputPlaceholder: string
  iconAssistant?: string
  inputId: string
  uploadAccept: string[]
  maxUploadSize: number | null
  elementId: string
  greeting?: GreetingData | null
  cancelId?: string
  enableCancel?: boolean
  enableUpload?: boolean
  cancelRequested?: boolean
  toolbarEl?: Element
  footerEl?: Element
  slashCommands: SlashCommandDef[]
  slashCommandId: string
  submitKey?: SubmitKey
  historyStore: HistoryStore
  drawer: ChatDrawerState
  drawerSource?: Element
  onEdit?: (
    index: number,
    content: string,
    attachments: AttachmentPayload[],
  ) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  siblingNavigationPending?: boolean
  showHistory: boolean
}

export interface ChatContainerHandle extends ChatInputHandle {
  beginSiblingNavigation(): void
  endSiblingNavigation(): void
}

interface ComposerPosition {
  centered: boolean
  greetingOverflows: boolean
  greetingOffset: number
  composerOffset: number
}

const CENTERED_GREETING_GAP = 12

export const ChatContainer = forwardRef<
  ChatContainerHandle,
  ChatContainerProps
>(function ChatContainer(
  {
    transport,
    messages,
    streamingMessage,
    inputDisabled,
    inputPlaceholder,
    iconAssistant,
    inputId,
    uploadAccept,
    maxUploadSize,
    elementId,
    greeting,
    cancelId,
    enableCancel,
    enableUpload,
    cancelRequested,
    toolbarEl,
    footerEl,
    slashCommands,
    slashCommandId,
    submitKey,
    historyStore,
    drawer,
    drawerSource,
    onEdit,
    onNavigate,
    siblingNavigationPending,
    showHistory,
  },
  ref,
) {
  const userMessages = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => m.content),
    [messages],
  )
  const displayedMessages = useMemo(
    () => (streamingMessage ? [...messages, streamingMessage] : messages),
    [messages, streamingMessage],
  )

  const chatInputRef = useRef<ChatInputHandle>(null)
  const drawerCloseRef = useRef<HTMLButtonElement>(null)
  const drawerRevealRef = useRef<HTMLButtonElement>(null)
  const drawerReturnFocusRef = useRef<HTMLElement | null>(null)
  const drawerRestoreFocusRef = useRef<HTMLElement | null>(null)
  const drawerReturnToRevealRef = useRef(false)
  const priorDrawerVisibleRef = useRef(drawer.visible)
  const priorDrawerTakeoverRef = useRef(false)
  const drawerLayoutRef = useRef<HTMLDivElement>(null)
  const drawerWidthProbeRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)
  const [drawerTakeover, setDrawerTakeover] = useState(false)
  const [drawerPresented, setDrawerPresented] = useState(drawer.visible)
  const [drawerResizing, setDrawerResizing] = useState(false)
  const [composerPosition, setComposerPosition] = useState<ComposerPosition>({
    centered: false,
    greetingOverflows: false,
    greetingOffset: 0,
    composerOffset: 0,
  })
  const [composerMotionReady, setComposerMotionReady] = useState(false)
  const [composerRevealing, setComposerRevealing] = useState(false)
  const [composerResizing, setComposerResizing] = useState(false)
  const composerPositionRef = useRef(composerPosition)
  composerPositionRef.current = composerPosition
  const [drawerLayoutWidth, setArtifactLayoutWidth] = useState(
    `${DEFAULT_DRAWER_LAYOUT_WIDTH}px`,
  )
  const history = useSyncExternalStore(
    historyStore.subscribe,
    historyStore.getSnapshot,
    historyStore.getSnapshot,
  )

  const [historyOpen, setHistoryOpen] = useState(false)
  const historyTriggerRef = useRef<HTMLButtonElement>(null)
  const historyOwnedByPage = useMemo(
    () => pageOwnsHistory(elementId),
    [elementId],
  )

  const [pendingUrl, setPendingUrl] = useState<string | null>(null)
  const pendingUrlRef = useRef<string | null>(null)
  pendingUrlRef.current = pendingUrl

  const { scrollRef, contentRef, scrollToBottom, stopScroll } =
    useStickToBottom({ resize: "smooth" })
  const contentElementRef = useRef<HTMLDivElement>(null)
  const savedScrollTopRef = useRef<number | null>(null)

  const handleContentRef = useCallback(
    (element: HTMLDivElement | null) => {
      contentElementRef.current = element
      if (savedScrollTopRef.current === null) {
        contentRef(element)
      }
    },
    [contentRef],
  )

  // Track scroll position of the scroll container directly. useStickToBottom's
  // own `isAtBottom` is computed from contentRef, which excludes the greeting
  // (intentionally — the greeting must not engage stick-to-bottom). But the
  // scroll-to-bottom button and the input's top shadow should still appear
  // when a long greeting alone overflows. Derive an `isAtBottom` from the
  // scroll container itself so it covers both cases uniformly.
  const [isAtBottom, setIsAtBottom] = useState(true)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const update = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight
      // ~1px fudge for fractional pixel rounding.
      setIsAtBottom(dist <= 1)
    }

    update()
    el.addEventListener("scroll", update, { passive: true })

    const ro = new ResizeObserver(update)
    ro.observe(el)
    const observeChildren = () => {
      Array.from(el.children).forEach((c) => ro.observe(c))
    }
    observeChildren()

    const mo = new MutationObserver(() => {
      observeChildren()
      update()
    })
    mo.observe(el, { childList: true })

    return () => {
      el.removeEventListener("scroll", update)
      ro.disconnect()
      mo.disconnect()
    }
  }, [scrollRef])

  const dispatch = useChatDispatch()

  const isStreaming = !!streamingMessage

  useEffect(() => {
    const frame = requestAnimationFrame(() => setComposerMotionReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    if (!composerPosition.centered) return

    setComposerRevealing(true)
    const timeout = window.setTimeout(() => setComposerRevealing(false), 300)
    return () => window.clearTimeout(timeout)
  }, [composerPosition.centered])

  // Keep the normal grid and scroll behavior intact, then translate the
  // greeting and composer as one group. Centering only the composer leaves a
  // multi-line greeting top-heavy; removing it from normal flow clips long
  // greetings before the overflow fallback can take effect.
  useLayoutEffect(() => {
    const layout = drawerLayoutRef.current
    const composer = composerRef.current
    const wrapper = layout?.querySelector(".shiny-chat-wrapper")
    const isPageChat = document
      .getElementById(elementId)
      ?.closest("shiny-chat-page")

    if (!layout || !composer || !wrapper || !isPageChat) return

    let resizeObserver: ResizeObserver | undefined
    let observedGreeting: Element | null = null
    let receivedInitialResize = false
    let resizeSettleTimer: number | undefined

    const setPosition = (nextPosition: ComposerPosition) => {
      const currentPosition = composerPositionRef.current
      if (
        currentPosition.centered === nextPosition.centered &&
        currentPosition.greetingOverflows === nextPosition.greetingOverflows &&
        currentPosition.greetingOffset === nextPosition.greetingOffset &&
        currentPosition.composerOffset === nextPosition.composerOffset
      ) {
        return
      }
      composerPositionRef.current = nextPosition
      setComposerPosition(nextPosition)
    }

    const resetPosition = () => {
      setPosition({
        centered: false,
        greetingOverflows: false,
        greetingOffset: 0,
        composerOffset: 0,
      })
    }

    const translateY = (element: Element) => {
      const value = getComputedStyle(element).translate
      if (value === "none") return 0
      const [, y] = value.split(/\s+/)
      return Number.parseFloat(y ?? "") || 0
    }

    const update = () => {
      const greetingEl = layout.querySelector(".shiny-chat-greeting")
      if (
        !greetingEl ||
        messages.length > 0 ||
        greeting?.status !== "visible"
      ) {
        resetPosition()
        return
      }

      if (resizeObserver && observedGreeting !== greetingEl) {
        if (observedGreeting) resizeObserver.unobserve(observedGreeting)
        resizeObserver.observe(greetingEl)
        observedGreeting = greetingEl
      }

      const wrapperBox = wrapper.getBoundingClientRect()
      const greetingBox = greetingEl.getBoundingClientRect()
      const composerBox = composer.getBoundingClientRect()
      const totalHeight =
        greetingBox.height + CENTERED_GREETING_GAP + composerBox.height

      if (totalHeight > wrapper.clientHeight) {
        // useStickToBottom can retain the empty-state scroll position while a
        // greeting grows. Oversized greetings must instead begin at the
        // scroll viewport's origin.
        const scroll = scrollRef.current
        if (!composerPositionRef.current.greetingOverflows) {
          stopScroll()
          if (scroll) scroll.scrollTop = 0
        }
        setPosition({
          centered: false,
          greetingOverflows: true,
          greetingOffset: 0,
          composerOffset: 0,
        })
        return
      }

      const greetingTarget =
        wrapperBox.top + (wrapperBox.height - totalHeight) / 2
      const composerTarget =
        greetingTarget + greetingBox.height + CENTERED_GREETING_GAP
      setPosition({
        centered: true,
        greetingOverflows: false,
        greetingOffset:
          translateY(greetingEl) + greetingTarget - greetingBox.top,
        composerOffset: translateY(composer) + composerTarget - composerBox.top,
      })
    }

    const settleResize = () => {
      setComposerResizing(true)
      if (resizeSettleTimer) window.clearTimeout(resizeSettleTimer)
      resizeSettleTimer = window.setTimeout(
        () => setComposerResizing(false),
        120,
      )
    }

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => {
        update()
        // Observing an element reports its existing dimensions once. That is
        // initialization, not a resize, so retain discrete-state motion.
        if (receivedInitialResize) settleResize()
        receivedInitialResize = true
      })
      resizeObserver.observe(layout)
      resizeObserver.observe(wrapper)
      resizeObserver.observe(composer)
      const footer = layout.querySelector(".shiny-chat-footer")
      if (footer) resizeObserver.observe(footer)
    }

    // History "New" can insert its greeting after this effect has run. Watch
    // the local layout so its first placement is measured immediately.
    const mutationObserver = new MutationObserver(update)
    mutationObserver.observe(layout, { childList: true, subtree: true })
    window.addEventListener("resize", update)
    update()

    return () => {
      if (resizeSettleTimer) window.clearTimeout(resizeSettleTimer)
      setComposerResizing(false)
      resizeObserver?.disconnect()
      mutationObserver.disconnect()
      window.removeEventListener("resize", update)
    }
  }, [elementId, greeting, messages.length, scrollRef, stopScroll])

  const updateDrawerLayoutWidth = useCallback(() => {
    const layout = drawerLayoutRef.current
    if (!layout || !drawer.enabled) return

    const nextWidth = resolveDrawerLayoutWidth(
      drawer.width,
      layout,
      drawerWidthProbeRef.current,
    )
    setArtifactLayoutWidth((currentWidth) =>
      currentWidth === nextWidth ? currentWidth : nextWidth,
    )
  }, [drawer.enabled, drawer.width])

  useLayoutEffect(() => {
    updateDrawerLayoutWidth()

    const layout = drawerLayoutRef.current
    if (!layout || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(updateDrawerLayoutWidth)
    observer.observe(layout)
    if (drawerWidthProbeRef.current) {
      observer.observe(drawerWidthProbeRef.current)
    }
    return () => observer.disconnect()
  }, [drawer.visible, updateDrawerLayoutWidth])

  useEffect(() => {
    const layout = drawerLayoutRef.current
    if (!layout || !drawer.enabled) {
      setDrawerTakeover(false)
      return
    }

    const update = (width: number) => {
      // Preserve the adjacent layout whenever the chat and artifact can both
      // meet their established minimum widths.
      setDrawerTakeover(width < DRAWER_TAKEOVER_WIDTH)
    }
    update(layout.getBoundingClientRect().width)

    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) update(entry.contentRect.width)
    })
    observer.observe(layout)
    return () => observer.disconnect()
  }, [drawer.enabled, drawer.visible])

  useLayoutEffect(() => {
    const wasVisible = priorDrawerVisibleRef.current
    const wasTakeover = priorDrawerTakeoverRef.current
    const isVisible = drawer.enabled && drawer.visible
    const revealedFromControl =
      isVisible && !wasVisible && drawerReturnToRevealRef.current
    const entersTakeover =
      isVisible && drawerTakeover && (!wasVisible || !wasTakeover)

    if (revealedFromControl) {
      drawerReturnFocusRef.current = null
      drawerRestoreFocusRef.current = null
      requestAnimationFrame(() => drawerCloseRef.current?.focus())
      if (historyOpen) setHistoryOpen(false)
    } else if (entersTakeover) {
      drawerRestoreFocusRef.current = null
      const active = document.activeElement
      const chatWrapper = drawerLayoutRef.current?.querySelector(
        ".shiny-chat-wrapper",
      )
      const activeInChat =
        active instanceof HTMLElement && chatWrapper?.contains(active)
      const activeOnHistoryTrigger = active === historyTriggerRef.current
      if (activeInChat || activeOnHistoryTrigger || historyOpen) {
        drawerReturnFocusRef.current =
          activeInChat && active instanceof HTMLElement
            ? active
            : historyTriggerRef.current
        requestAnimationFrame(() => drawerCloseRef.current?.focus())
      } else if (drawerReturnToRevealRef.current) {
        drawerReturnFocusRef.current = null
        requestAnimationFrame(() => drawerCloseRef.current?.focus())
      } else {
        drawerReturnFocusRef.current = null
      }
      if (historyOpen) setHistoryOpen(false)
    } else if (wasVisible && !isVisible) {
      const returnToReveal = drawerReturnToRevealRef.current
      drawerReturnToRevealRef.current = false
      if (returnToReveal) {
        requestAnimationFrame(() => drawerRevealRef.current?.focus())
      } else {
        drawerRestoreFocusRef.current = drawerReturnFocusRef.current
      }
      drawerReturnFocusRef.current = null
    }

    priorDrawerVisibleRef.current = isVisible
    priorDrawerTakeoverRef.current = drawerTakeover
  }, [drawer.enabled, drawer.visible, drawerTakeover, historyOpen])

  useLayoutEffect(() => {
    if (drawer.visible || drawerPresented) return

    const returnFocus = drawerRestoreFocusRef.current
    drawerRestoreFocusRef.current = null
    if (!returnFocus?.isConnected) return

    requestAnimationFrame(() => {
      if (returnFocus.isConnected) returnFocus.focus()
    })
  }, [drawer.visible, drawerPresented])

  useEffect(() => {
    if (drawerTakeover && drawer.visible && historyOpen) {
      setHistoryOpen(false)
    }
  }, [drawer.visible, drawerTakeover, historyOpen])

  const closeDrawer = useCallback(() => {
    dispatch({ type: "drawer_hide" })
  }, [dispatch])

  const revealDrawer = useCallback(() => {
    drawerReturnToRevealRef.current = true
    dispatch({ type: "drawer_toggle" })
  }, [dispatch])

  const setDrawerWidth = useCallback(
    (width: string) => {
      dispatch({ type: "SET_DRAWER_WIDTH", width })
    },
    [dispatch],
  )

  const cancelStream = useCallback((): void => {
    if (!enableCancel || !cancelId || !isStreaming || cancelRequested) return
    dispatch({ type: "CANCEL_REQUESTED" })
    transport.sendCancel(cancelId)
  }, [
    enableCancel,
    cancelId,
    isStreaming,
    cancelRequested,
    dispatch,
    transport,
  ])

  const cancelStreamRef = useRef(cancelStream)
  cancelStreamRef.current = cancelStream

  useEffect(() => {
    if (!enableCancel) return

    const container = scrollRef.current?.closest("shiny-chat-container")
    if (!container) return

    const handleKeyDown = (e: Event): void => {
      if (e.defaultPrevented) return
      if ((e as KeyboardEvent).key !== "Escape") return
      cancelStreamRef.current()
    }

    container.addEventListener("keydown", handleKeyDown)
    return () => container.removeEventListener("keydown", handleKeyDown)
  }, [enableCancel, scrollRef])

  useFillPaddingTransfer(scrollRef)

  // Keep the history trigger clear of other visible UI. It anchors to a corner
  // of the container, where it can collide with e.g. a bslib sidebar reveal
  // button. `shouldSkip` bails while the drawer is open — the trigger sits under
  // the scrim (position moot), and an open drawer over a collapsed same-side
  // sidebar hides the sidebar's collapse-toggle (see _history.scss), so probing
  // would record a false "no overlap"; the drawer's add/remove (watchMutations)
  // re-runs the measure once it closes and the toggle is measurable again.
  useOverlapNudge(historyTriggerRef, {
    enabled: history.enabled,
    boundarySelector: "shiny-chat-container",
    shiftProperty: "--_history-trigger-shift",
    side: (container) =>
      container.getAttribute("data-history-placement") === "right"
        ? "right"
        : "left",
    shouldSkip: (container) =>
      !!container.querySelector(":scope > .shiny-chat-history"),
    watchMutations: { childList: true },
  })

  useImperativeHandle(ref, () => ({
    setInputValue(...args) {
      chatInputRef.current?.setInputValue(...args)
    },
    focus() {
      chatInputRef.current?.focus()
    },
    beginSiblingNavigation() {
      const scroll = scrollRef.current
      if (!scroll) return

      savedScrollTopRef.current = scroll.scrollTop
      contentRef(null)
      stopScroll()
    },
    endSiblingNavigation() {
      const savedScrollTop = savedScrollTopRef.current
      if (savedScrollTop === null) return

      requestAnimationFrame(() => {
        const content = contentElementRef.current
        const scroll = scrollRef.current
        if (!content || !scroll) return

        contentRef(content)
        stopScroll()
        scroll.scrollTop = savedScrollTop
        savedScrollTopRef.current = null
      })
    },
  }))

  const onContainerClick = useCallback((e: React.MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement
    const linkEl = target.closest(
      "a[data-shinychat-link]",
    ) as HTMLAnchorElement | null
    if (!linkEl || !linkEl.href) return

    e.preventDefault()

    const isSameOrigin = linkEl.origin === window.location.origin
    if (isSameOrigin || window.shinychat_always_open_external_links) {
      openLink(linkEl.href)
      return
    }

    if (typeof window.HTMLDialogElement === "undefined") {
      openLink(linkEl.href)
      return
    }

    setPendingUrl(linkEl.href)
  }, [])

  function getSuggestion(target: EventTarget | null): {
    suggestion?: string
    submit?: boolean
  } {
    if (!(target instanceof HTMLElement)) return {}

    const el = target.closest(".suggestion, [data-suggestion]")
    if (!(el instanceof HTMLElement)) return {}

    const isSuggestion =
      el.classList.contains("suggestion") || el.dataset.suggestion !== undefined
    if (!isSuggestion) return {}

    const suggestion = el.dataset.suggestion || el.textContent

    return {
      suggestion: suggestion || undefined,
      submit:
        el.classList.contains("submit") ||
        el.dataset.suggestionSubmit === "" ||
        el.dataset.suggestionSubmit === "true",
    }
  }

  function handleSuggestionEvent(
    e: React.MouseEvent | React.KeyboardEvent,
  ): void {
    const { suggestion, submit } = getSuggestion(e.target)
    if (!suggestion) return

    e.preventDefault()
    // Cmd/Ctrl + event = force submit; Alt/Opt + event = force set without submitting
    const shouldSubmit =
      e.metaKey || e.ctrlKey ? true : e.altKey ? false : submit

    chatInputRef.current?.setInputValue(suggestion, {
      submit: shouldSubmit,
      focus: !shouldSubmit,
    })

    const cardEl = (e.target as HTMLElement).closest<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )
    const grid = cardEl?.closest<HTMLElement>(".shiny-chat-suggestion-list")
    if (cardEl && grid) {
      grid
        .querySelectorAll<HTMLElement>("[data-last-clicked]")
        .forEach((el) => el.removeAttribute("data-last-clicked"))
      cardEl.setAttribute("data-last-clicked", "")
    }
  }

  function onSuggestionClick(e: React.MouseEvent<HTMLElement>): void {
    handleSuggestionEvent(e)
  }

  function onMessagesClick(e: React.MouseEvent<HTMLElement>): void {
    onContainerClick(e)
    onSuggestionClick(e)
  }

  function handleFocusIn(e: React.FocusEvent<HTMLElement>): void {
    const card = (e.target as HTMLElement).closest<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )
    if (!card) return
    const grid = card.closest<HTMLElement>(".shiny-chat-suggestion-list")
    if (!grid || grid.dataset.roved !== undefined) return
    grid.dataset.roved = ""
    grid
      .querySelectorAll<HTMLElement>(".shiny-chat-suggestion-list-item")
      .forEach((el) => {
        if (el !== card) el.tabIndex = -1
      })
  }

  function handleFocusOut(e: React.FocusEvent<HTMLElement>): void {
    const card = (e.target as HTMLElement).closest<HTMLElement>(
      ".shiny-chat-suggestion-list-item",
    )
    if (!card) return
    const grid = card.closest<HTMLElement>(".shiny-chat-suggestion-list")
    if (!grid) return

    const relatedTarget = e.relatedTarget as HTMLElement | null
    const relatedGrid = relatedTarget?.closest<HTMLElement>(
      ".shiny-chat-suggestion-list",
    )

    if (!relatedTarget || relatedGrid !== grid) {
      delete grid.dataset.roved
    }
  }

  function nextCardIndex(idx: number, len: number, key: string): number | null {
    switch (key) {
      case "ArrowDown":
      case "ArrowRight":
        return (idx + 1) % len
      case "ArrowUp":
      case "ArrowLeft":
        return (idx - 1 + len) % len
      case "Home":
        return 0
      case "End":
        return len - 1
      default:
        return null
    }
  }

  function onSuggestionKeydown(e: React.KeyboardEvent<HTMLElement>): void {
    const target = e.target as HTMLElement
    const card = target.closest<HTMLElement>(".shiny-chat-suggestion-list-item")
    const grid = card?.closest<HTMLElement>(".shiny-chat-suggestion-list")

    if (card && grid) {
      const cards = Array.from(
        grid.querySelectorAll<HTMLElement>(".shiny-chat-suggestion-list-item"),
      )
      const idx = cards.indexOf(card)
      const nextIdx = nextCardIndex(idx, cards.length, e.key)
      if (nextIdx !== null) {
        e.preventDefault()
        const current = cards[idx]!
        const next = cards[nextIdx]!
        current.tabIndex = -1
        next.tabIndex = 0
        next.focus()
        return
      }
    }

    const isEnterOrSpace = e.key === "Enter" || e.key === " "
    if (!isEnterOrSpace) return
    handleSuggestionEvent(e)
  }

  const handleDialogProceed = useCallback(() => {
    const url = pendingUrlRef.current
    if (url) openLink(url)
    setPendingUrl(null)
  }, [])

  const handleDialogAlways = useCallback(() => {
    window.shinychat_always_open_external_links = true
    handleDialogProceed()
  }, [handleDialogProceed])

  const handleDialogCancel = useCallback(() => {
    setPendingUrl(null)
  }, [])

  const onSend = useCallback(() => {
    scrollToBottom()
  }, [scrollToBottom])

  const drawerHasContent = drawer.content.trim().length > 0
  const drawerTakeoverActive = drawerTakeover && drawerPresented
  const drawerLayoutOpen = drawer.enabled && (drawer.visible || drawerPresented)

  useLayoutEffect(() => {
    const container = document.getElementById(elementId)
    if (!container) return

    const controls: string[] = []
    if (showHistory && history.enabled && !historyOwnedByPage) {
      controls.push("history")
    }
    if (drawer.enabled && !drawer.visible && drawerHasContent) {
      controls.push("drawer")
    }

    const value = controls.join(" ")
    if (value) {
      container.dataset.inlineControls = value
    } else {
      delete container.dataset.inlineControls
    }

    return () => {
      if (container.dataset.inlineControls === value) {
        delete container.dataset.inlineControls
      }
    }
  }, [
    drawer.enabled,
    drawer.visible,
    drawerHasContent,
    history.enabled,
    historyOwnedByPage,
    elementId,
    showHistory,
  ])

  return (
    <SlashCommandsContext.Provider value={slashCommands}>
      {showHistory && history.enabled && !historyOwnedByPage && (
        <button
          type="button"
          ref={historyTriggerRef}
          className="shiny-chat-history-trigger"
          aria-label="Conversation history"
          aria-expanded={historyOpen}
          aria-hidden={drawerTakeoverActive || undefined}
          disabled={drawerTakeoverActive}
          tabIndex={drawerTakeoverActive ? -1 : undefined}
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <HistoryIcon />
        </button>
      )}
      {drawer.enabled && !drawer.visible && drawerHasContent && (
        <button
          type="button"
          ref={drawerRevealRef}
          className="shiny-chat-drawer-trigger"
          aria-label="Show drawer"
          aria-controls={`${elementId}-drawer`}
          aria-expanded={false}
          title="Show drawer"
          onClick={revealDrawer}
        >
          <DrawerRevealIcon />
        </button>
      )}
      {/* Width-limited, centered content column. The container itself is
          full-width so the history trigger + drawer scrim (siblings of this
          wrapper) can span the whole element. */}
      <div
        ref={drawerLayoutRef}
        className="shiny-chat-layout"
        style={
          drawer.enabled || composerPosition.centered
            ? ({
                ...(drawer.enabled
                  ? {
                      "--_drawer-width": drawerLayoutWidth,
                    }
                  : {}),
                "--_greeting-offset": `${composerPosition.greetingOffset}px`,
                "--_composer-offset": `${composerPosition.composerOffset}px`,
              } as React.CSSProperties)
            : undefined
        }
        data-drawer-open={drawerLayoutOpen ? "" : undefined}
        data-drawer-takeover={
          drawerTakeover && drawerPresented ? "" : undefined
        }
        data-drawer-resizing={drawerResizing ? "" : undefined}
        data-composer-centered={composerPosition.centered ? "" : undefined}
        data-greeting-overflow={
          composerPosition.greetingOverflows ? "" : undefined
        }
        data-composer-motion-ready={composerMotionReady ? "" : undefined}
        data-composer-revealing={composerRevealing ? "" : undefined}
        data-composer-resizing={composerResizing ? "" : undefined}
      >
        <div className="shiny-chat-wrapper">
          <div className="shiny-chat-messages-wrapper">
            <div
              className="shiny-chat-messages"
              ref={scrollRef}
              onClick={onMessagesClick}
              onFocus={handleFocusIn}
              onBlur={handleFocusOut}
              onKeyDown={onSuggestionKeydown}
            >
              <ChatScrollContext.Provider value={stopScroll}>
                {/* Greeting lives outside contentRef so its growth (e.g. while a
                streaming greeting fills in) does not trigger useStickToBottom
                — only message growth does. Suggestion clicks inside the
                greeting still reach the messages-level handlers via bubbling. */}
                {greeting != null && <ChatGreeting greeting={greeting} />}
                <div
                  className="shiny-chat-messages-content"
                  ref={handleContentRef}
                  role="log"
                  aria-live="polite"
                  {...(greeting?.status === "dismissing"
                    ? { "data-greeting-dismissing": "" }
                    : {})}
                >
                  <ChatMessages
                    messages={displayedMessages}
                    iconAssistant={iconAssistant}
                    // Editing/navigating requires the server-side history
                    // controller, which only registers its input listeners
                    // when history is enabled -- without this gate the
                    // buttons would render but silently no-op on click.
                    onEdit={history.enabled ? onEdit : undefined}
                    onNavigate={history.enabled ? onNavigate : undefined}
                    siblingNavigationPending={siblingNavigationPending}
                    disabled={isStreaming}
                    inputId={inputId}
                    submitKey={submitKey}
                    uploadAccept={uploadAccept}
                    maxUploadSize={maxUploadSize}
                    enableUpload={enableUpload}
                  />
                </div>
              </ChatScrollContext.Provider>
            </div>
            <ScrollToBottomButton
              isAtBottom={isAtBottom}
              scrollToBottom={scrollToBottom}
              streaming={!!streamingMessage || !!greeting?.streaming}
            />
          </div>

          <div className="shiny-chat-composer" ref={composerRef}>
            <div
              className={
                inputDisabled ? "shiny-chat-input disabled" : "shiny-chat-input"
              }
              onClick={onContainerClick}
            >
              <ChatInput
                ref={chatInputRef}
                transport={transport}
                inputId={inputId}
                uploadAccept={uploadAccept}
                maxUploadSize={maxUploadSize}
                disabled={inputDisabled}
                hasTopShadow={!isAtBottom}
                placeholder={inputPlaceholder}
                onSend={onSend}
                userMessages={userMessages}
                enableCancel={enableCancel}
                enableUpload={enableUpload}
                cancelRequested={cancelRequested}
                isStreaming={isStreaming}
                onCancel={cancelStream}
                slashCommands={slashCommands}
                slashCommandId={slashCommandId}
                submitKey={submitKey}
              />
            </div>

            {toolbarEl && (
              <RawDOM source={toolbarEl} className="shiny-chat-input-toolbar" />
            )}
          </div>
        </div>

        {footerEl && <RawDOM source={footerEl} className="shiny-chat-footer" />}

        {drawer.enabled && (
          <ChatDrawer
            drawer={drawer}
            source={drawerSource}
            panelId={`${elementId}-drawer`}
            titleId={`${elementId}-drawer-title`}
            takeover={drawerTakeover}
            closeButtonRef={drawerCloseRef}
            onClose={closeDrawer}
            onWidthChange={setDrawerWidth}
            onPresentationChange={setDrawerPresented}
            onResizeStateChange={setDrawerResizing}
          />
        )}
        {drawer.enabled && (
          <div
            ref={drawerWidthProbeRef}
            aria-hidden="true"
            className="shiny-chat-drawer-width-probe"
            style={{ width: drawer.width }}
          />
        )}
      </div>

      {showHistory && history.enabled && !historyOwnedByPage && (
        <ChatHistoryDrawer
          isOpen={historyOpen}
          onClose={() => setHistoryOpen(false)}
          triggerRef={historyTriggerRef}
        >
          <ChatHistoryContent
            conversations={history.conversations}
            activeId={history.activeId}
            busy={history.busy}
            connected={history.connected}
            onSelect={historyStore.actions.select}
            onNew={historyStore.actions.create}
            onRename={historyStore.actions.rename}
            onDelete={historyStore.actions.delete}
            onActionComplete={() => setHistoryOpen(false)}
          />
        </ChatHistoryDrawer>
      )}

      {pendingUrl &&
        createPortal(
          <ExternalLinkDialogComponent
            url={pendingUrl}
            onProceed={handleDialogProceed}
            onAlways={handleDialogAlways}
            onCancel={handleDialogCancel}
          />,
          document.body,
        )}
    </SlashCommandsContext.Provider>
  )
})
