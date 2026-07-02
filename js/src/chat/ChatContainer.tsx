import {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useMemo,
} from "react"
import { createPortal } from "react-dom"
import { useStickToBottom } from "use-stick-to-bottom"
import { ChatMessages } from "./ChatMessages"
import { ChatMessage } from "./ChatMessage"
import { ChatGreeting } from "./ChatGreeting"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import { ChatInput, type ChatInputHandle } from "./ChatInput"
import { ScrollToBottomButton } from "./ScrollToBottomButton"
import { ExternalLinkDialogComponent } from "./ExternalLinkDialog"
import { RawDOM } from "./RawDOM"
import {
  ChatScrollContext,
  SlashCommandsContext,
  useChatDispatch,
} from "./context"
import { ChatHistoryDrawer, HistoryIcon } from "./ChatHistoryDrawer"
import type { ChatMessageData, GreetingData } from "./state"
import type {
  ChatTransport,
  ConversationMeta,
  SlashCommandDef,
} from "../transport/types"
import type { SubmitKey } from "./tiptap/submitShortcut"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

function openLink(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer")
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
  historyEnabled?: boolean
  historyConversations?: ConversationMeta[]
  historyActiveId?: string | null
}

export type ChatContainerHandle = ChatInputHandle

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
    historyEnabled,
    historyConversations,
    historyActiveId,
  },
  ref,
) {
  const userMessages = useMemo(
    () => messages.filter((m) => m.role === "user").map((m) => m.content),
    [messages],
  )

  const chatInputRef = useRef<ChatInputHandle>(null)

  const [historyOpen, setHistoryOpen] = useState(false)
  const historyTriggerRef = useRef<HTMLButtonElement>(null)

  const [pendingUrl, setPendingUrl] = useState<string | null>(null)
  const pendingUrlRef = useRef<string | null>(null)
  pendingUrlRef.current = pendingUrl

  const { scrollRef, contentRef, scrollToBottom, stopScroll } =
    useStickToBottom({ resize: "smooth" })

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

  // When a fill-enabled chat is the sole child of a padded bslib fillable
  // container (sidebar main, card body, page_fillable, …), the parent's padding
  // insets the whole chat — including the full-width history trigger and drawer,
  // which anchor to shiny-chat-container. Move that padding onto the centered
  // content column instead: zero the parent's padding and hand the captured
  // value to --shiny-chat-fill-padding, so the trigger/drawer sit flush with the
  // parent edge while the messages + input keep equivalent breathing room.
  // Setting the parent's inline padding directly beats a card_body(padding=)
  // inline style, which a stylesheet rule could not.
  useEffect(() => {
    const container = scrollRef.current?.closest<HTMLElement>(
      "shiny-chat-container",
    )
    if (!container?.hasAttribute("fill")) return
    if (!container.classList.contains("html-fill-item")) return

    // Walk up the chain of fillable containers the chat solely occupies (each an
    // .html-fill-container whose only element child is the node below it) to the
    // FIRST one that actually carries padding, and stop there. The chat is a fill
    // item inside its fillable parent, but bslib can insert zero-padding wrapper
    // layers — e.g. page_sidebar(fillable=TRUE) nests a .bslib-page-main inside
    // the padded sidebar .main — so the padded box may sit a level or two up.
    // Stopping at the first padded ancestor keeps us inside the chat's own visual
    // container: in a card the .card-body padding transfers, but we must NOT climb
    // past the card to also strip the surrounding sidebar-main padding (that would
    // pull the whole card flush to the layout edge).
    let target: HTMLElement | null = null
    let targetPadding = ""
    let node: HTMLElement = container
    while (
      node.parentElement instanceof HTMLElement &&
      node.parentElement.classList.contains("html-fill-container") &&
      node.parentElement.children.length === 1
    ) {
      node = node.parentElement
      const pad = getComputedStyle(node).paddingLeft
      if (parseFloat(pad) > 0) {
        target = node
        targetPadding = pad
        break
      }
    }
    if (!target) return

    // Zeroing the padded ancestor's inline padding beats a card_body(padding=)
    // inline style, which a stylesheet rule could not. --_chat-container-padding
    // is a single-value token (used in calc() and padding-inline), so hand it the
    // horizontal inset; fillable paddings are uniform.
    const prevInlinePadding = target.style.padding
    target.style.padding = "0"
    container.style.setProperty("--shiny-chat-fill-padding", targetPadding)

    return () => {
      target.style.padding = prevInlinePadding
      container.style.removeProperty("--shiny-chat-fill-padding")
    }
  }, [scrollRef])

  // Keep the history trigger clear of other visible UI. It anchors to a corner
  // of the container, where it can collide with e.g. a bslib sidebar reveal
  // button. When the trigger's home position overlaps another element that
  // isn't part of the chat, nudge it inward (toward the chat column) via the
  // --_history-trigger-shift var until it clears, capped so it never travels
  // too far into the content.
  useEffect(() => {
    if (!historyEnabled) return
    const trigger = historyTriggerRef.current
    if (!trigger) return
    const container = trigger.closest(
      "shiny-chat-container",
    ) as HTMLElement | null
    if (!container) return

    const update = (): void => {
      // While the drawer is open the trigger sits under the scrim, so its
      // position is moot — and an open drawer over a collapsed same-side sidebar
      // hides the sidebar's collapse-toggle (see _history.scss), which would make
      // the probe below record a false "no overlap" (shift 0). Skip so the last
      // closed-state shift is preserved; the MutationObserver below re-runs this
      // once the drawer closes and the toggle is measurable again.
      if (container.querySelector(":scope > .shiny-chat-history")) return

      const placeRight =
        container.getAttribute("data-history-placement") === "right"

      // Measure from the home position each time so the shift never compounds.
      trigger.style.setProperty("--_history-trigger-shift", "0px")
      const rect = trigger.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return

      // Probe the trigger's leading (outer) edge at three heights. An obstacle
      // is any hit-tested element that is neither inside the chat container nor
      // an ancestor of it (which filters out the chat's own content and its
      // backdrops/layout parents, leaving genuine siblings like a sidebar toggle).
      const edgeX = placeRight ? rect.right - 1 : rect.left + 1
      const ys = [rect.top + 2, rect.top + rect.height / 2, rect.bottom - 2]

      let obstacleEdge: number | null = null
      for (const y of ys) {
        const obstacle = document
          .elementsFromPoint(edgeX, y)
          .find((el) => !container.contains(el) && !el.contains(container))
        if (!obstacle) continue
        const obRect = obstacle.getBoundingClientRect()
        const edge = placeRight ? obRect.left : obRect.right
        obstacleEdge =
          obstacleEdge === null
            ? edge
            : placeRight
              ? Math.min(obstacleEdge, edge)
              : Math.max(obstacleEdge, edge)
      }

      if (obstacleEdge === null) return

      const gap = 8
      const shift = placeRight
        ? rect.right - obstacleEdge + gap
        : obstacleEdge - rect.left + gap
      if (shift <= 0) return

      const maxShift = container.clientWidth / 3
      trigger.style.setProperty(
        "--_history-trigger-shift",
        `${Math.min(shift, maxShift)}px`,
      )
    }

    update()

    const ro = new ResizeObserver(update)
    ro.observe(container)
    window.addEventListener("resize", update)

    // A sidebar collapse/expand shifts the container without resizing it; the
    // layout toggles a class and animates, so re-measure on both.
    const layout = container.closest(".bslib-sidebar-layout")
    layout?.addEventListener("transitionend", update)
    const mo = layout ? new MutationObserver(update) : null
    mo?.observe(layout!, { attributes: true, attributeFilter: ["class"] })

    // The drawer opening/closing isn't a resize or a layout-class change, but
    // update() bails while it's open (see above), so re-run when it's added or
    // removed — closing it is what makes the toggle measurable again.
    const drawerMo = new MutationObserver(update)
    drawerMo.observe(container, { childList: true })

    return () => {
      ro.disconnect()
      window.removeEventListener("resize", update)
      layout?.removeEventListener("transitionend", update)
      mo?.disconnect()
      drawerMo.disconnect()
    }
  }, [historyEnabled])

  useImperativeHandle(ref, () => ({
    setInputValue(...args) {
      chatInputRef.current?.setInputValue(...args)
    },
    focus() {
      chatInputRef.current?.focus()
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

  return (
    <SlashCommandsContext.Provider value={slashCommands}>
      {historyEnabled && (
        <button
          type="button"
          ref={historyTriggerRef}
          className="shiny-chat-history-trigger"
          aria-label="Conversation history"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <HistoryIcon />
        </button>
      )}
      {/* Width-limited, centered content column. The container itself is
          full-width so the history trigger + drawer scrim (siblings of this
          wrapper) can span the whole element. */}
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
                ref={contentRef}
                role="log"
                aria-live="polite"
                {...(greeting?.status === "dismissing"
                  ? { "data-greeting-dismissing": "" }
                  : {})}
              >
                <ChatMessages
                  messages={messages}
                  iconAssistant={iconAssistant}
                />
                {streamingMessage && (
                  <MessageErrorBoundary key={streamingMessage.id}>
                    <ChatMessage
                      message={streamingMessage}
                      iconAssistant={iconAssistant}
                    />
                  </MessageErrorBoundary>
                )}
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

        {footerEl && <RawDOM source={footerEl} className="shiny-chat-footer" />}
      </div>

      {historyEnabled && (
        <ChatHistoryDrawer
          isOpen={historyOpen}
          onClose={() => setHistoryOpen(false)}
          triggerRef={historyTriggerRef}
          conversations={historyConversations ?? []}
          activeId={historyActiveId ?? null}
          busy={isStreaming}
          onSelect={(convId) => {
            transport.sendHistorySelect(elementId, convId)
          }}
          onNew={() => transport.sendHistoryNew(elementId)}
          onRename={(convId, title) =>
            transport.sendHistoryRename(elementId, convId, title)
          }
          onDelete={(convId) => transport.sendHistoryDelete(elementId, convId)}
        />
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
