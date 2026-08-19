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
import { ARTIFACT_TAKEOVER_WIDTH, ChatArtifact } from "./ChatArtifact"
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
import type { ChatArtifactState, ChatMessageData, GreetingData } from "./state"
import type { ChatTransport, SlashCommandDef } from "../transport/types"
import type { SubmitKey } from "./tiptap/submitShortcut"
import type { AttachmentPayload } from "./attachments"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

function openLink(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer")
}

function ArtifactRevealIcon() {
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
  ).some((history) => history.getAttribute("for") === elementId)
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
  footerEl?: Element
  slashCommands: SlashCommandDef[]
  slashCommandId: string
  submitKey?: SubmitKey
  historyStore: HistoryStore
  artifact: ChatArtifactState
  artifactSource?: Element
  onEdit?: (
    index: number,
    content: string,
    attachments: AttachmentPayload[],
  ) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  siblingNavigationPending?: boolean
}

export interface ChatContainerHandle extends ChatInputHandle {
  beginSiblingNavigation(): void
  endSiblingNavigation(): void
}

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
    footerEl,
    slashCommands,
    slashCommandId,
    submitKey,
    historyStore,
    artifact,
    artifactSource,
    onEdit,
    onNavigate,
    siblingNavigationPending,
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
  const artifactCloseRef = useRef<HTMLButtonElement>(null)
  const artifactRevealRef = useRef<HTMLButtonElement>(null)
  const artifactReturnFocusRef = useRef<HTMLElement | null>(null)
  const artifactReturnToRevealRef = useRef(false)
  const priorArtifactVisibleRef = useRef(artifact.visible)
  const priorArtifactTakeoverRef = useRef(false)
  const artifactLayoutRef = useRef<HTMLDivElement>(null)
  const [artifactTakeover, setArtifactTakeover] = useState(false)
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
    const layout = artifactLayoutRef.current
    if (!layout || !artifact.enabled) {
      setArtifactTakeover(false)
      return
    }

    const update = (width: number) => {
      // Keep the message column at its normal 680px reading cap. Below this
      // threshold an adjacent artifact would force that column narrower.
      setArtifactTakeover(width < ARTIFACT_TAKEOVER_WIDTH)
    }
    update(layout.getBoundingClientRect().width)

    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) update(entry.contentRect.width)
    })
    observer.observe(layout)
    return () => observer.disconnect()
  }, [artifact.enabled])

  useLayoutEffect(() => {
    const wasVisible = priorArtifactVisibleRef.current
    const wasTakeover = priorArtifactTakeoverRef.current
    const isVisible = artifact.enabled && artifact.visible
    const revealedFromControl =
      isVisible && !wasVisible && artifactReturnToRevealRef.current
    const entersTakeover =
      isVisible && artifactTakeover && (!wasVisible || !wasTakeover)

    if (revealedFromControl) {
      artifactReturnFocusRef.current = null
      requestAnimationFrame(() => artifactCloseRef.current?.focus())
      if (historyOpen) setHistoryOpen(false)
    } else if (entersTakeover) {
      const active = document.activeElement
      const chatWrapper = artifactLayoutRef.current?.querySelector(
        ".shiny-chat-wrapper",
      )
      const activeInChat =
        active instanceof HTMLElement && chatWrapper?.contains(active)
      const activeOnHistoryTrigger = active === historyTriggerRef.current
      if (activeInChat || activeOnHistoryTrigger || historyOpen) {
        artifactReturnFocusRef.current =
          activeInChat && active instanceof HTMLElement
            ? active
            : historyTriggerRef.current
        requestAnimationFrame(() => artifactCloseRef.current?.focus())
      } else if (artifactReturnToRevealRef.current) {
        artifactReturnFocusRef.current = null
        requestAnimationFrame(() => artifactCloseRef.current?.focus())
      } else {
        artifactReturnFocusRef.current = null
      }
      if (historyOpen) setHistoryOpen(false)
    } else if (wasVisible && !isVisible) {
      const returnToReveal = artifactReturnToRevealRef.current
      artifactReturnToRevealRef.current = false
      if (returnToReveal) {
        requestAnimationFrame(() => artifactRevealRef.current?.focus())
      } else {
        const returnFocus = artifactReturnFocusRef.current
        if (returnFocus?.isConnected) returnFocus.focus()
      }
      artifactReturnFocusRef.current = null
    }

    priorArtifactVisibleRef.current = isVisible
    priorArtifactTakeoverRef.current = artifactTakeover
  }, [artifact.enabled, artifact.visible, artifactTakeover, historyOpen])

  useEffect(() => {
    if (artifactTakeover && artifact.visible && historyOpen) {
      setHistoryOpen(false)
    }
  }, [artifact.visible, artifactTakeover, historyOpen])

  const closeArtifact = useCallback(() => {
    dispatch({ type: "artifact_hide" })
  }, [dispatch])

  const revealArtifact = useCallback(() => {
    artifactReturnToRevealRef.current = true
    dispatch({ type: "artifact_toggle" })
  }, [dispatch])

  const setArtifactWidth = useCallback(
    (width: string) => {
      dispatch({ type: "SET_ARTIFACT_WIDTH", width })
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

  const artifactHasContent = artifact.content.trim().length > 0
  const artifactTakeoverActive = artifactTakeover && artifact.visible

  return (
    <SlashCommandsContext.Provider value={slashCommands}>
      {history.enabled && !historyOwnedByPage && (
        <button
          type="button"
          ref={historyTriggerRef}
          className="shiny-chat-history-trigger"
          aria-label="Conversation history"
          aria-expanded={historyOpen}
          aria-hidden={artifactTakeoverActive || undefined}
          disabled={artifactTakeoverActive}
          tabIndex={artifactTakeoverActive ? -1 : undefined}
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <HistoryIcon />
        </button>
      )}
      {artifact.enabled && !artifact.visible && artifactHasContent && (
        <button
          type="button"
          ref={artifactRevealRef}
          className="shiny-chat-artifact-trigger"
          aria-label="Show artifact"
          aria-controls={`${elementId}-artifact`}
          aria-expanded={false}
          title="Show artifact"
          onClick={revealArtifact}
        >
          <ArtifactRevealIcon />
        </button>
      )}
      {/* Width-limited, centered content column. The container itself is
          full-width so the history trigger + drawer scrim (siblings of this
          wrapper) can span the whole element. */}
      <div
        ref={artifactLayoutRef}
        className="shiny-chat-layout"
        style={
          artifact.enabled
            ? ({
                "--shiny-chat-artifact-width": artifact.width,
              } as React.CSSProperties)
            : undefined
        }
        data-artifact-open={
          artifact.enabled && artifact.visible ? "" : undefined
        }
        data-artifact-takeover={
          artifactTakeover && artifact.visible ? "" : undefined
        }
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

          {footerEl && (
            <RawDOM source={footerEl} className="shiny-chat-footer" />
          )}
        </div>

        {artifact.enabled && (
          <ChatArtifact
            artifact={artifact}
            source={artifactSource}
            panelId={`${elementId}-artifact`}
            titleId={`${elementId}-artifact-title`}
            takeover={artifactTakeover}
            closeButtonRef={artifactCloseRef}
            onClose={closeArtifact}
            onWidthChange={setArtifactWidth}
          />
        )}
      </div>

      {history.enabled && !historyOwnedByPage && (
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
