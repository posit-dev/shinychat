import {
  useReducer,
  useEffect,
  useLayoutEffect,
  useRef,
  useMemo,
  useState,
  useCallback,
} from "react"
import {
  ShinyLifecycleContext,
  ChatToolContext,
  ChatDispatchContext,
  ToolGroupingContext,
  AsideFaviconContext,
} from "./context"
import { setCurrentConversationId } from "./currentConversation"
import { navigateTo } from "../utils/navigate"
import {
  chatReducer,
  initialState,
  splitThinkingBlocks,
  contentFromBlocks,
  type ChatMessageData,
  type ChatToolState,
  type ChatDrawerState,
  type GreetingData,
  type ToolGrouping,
} from "./state"
import { useSupersededRequests } from "./useSupersededRequests"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
import { acquireHistoryStore, getHistoryStore } from "./historyStore"
import type {
  ChatTransport,
  ShinyLifecycle,
  GreetingOptions,
} from "../transport/types"
import type { SubmitKey } from "./tiptap/submitShortcut"
import type { AttachmentPayload } from "./attachments"

export interface InitialGreeting {
  content: string
  contentType: import("../transport/types").ContentType
  options: GreetingOptions
}

export interface ChatAppProps {
  transport: ChatTransport
  shinyLifecycle: ShinyLifecycle
  elementId: string
  iconAssistant?: string
  iconSend?: string
  inputId: string
  cancelId?: string
  uploadAccept?: string[]
  maxUploadSize?: number | null
  placeholder?: string
  initialMessages?: ChatMessageData[]
  initialGreeting?: InitialGreeting
  /** True when a stored/URL conversation ID suggests a history restore is pending. */
  restorePending?: boolean
  initialDrawer?: ChatDrawerState
  drawerSource?: Element
  enableCancel?: boolean
  enableUpload?: boolean
  asideFavicon?: boolean
  showHistory?: boolean
  toolGrouping?: ToolGrouping
  toolbarEl?: Element
  footerEl?: Element
  slashCommandId?: string
  submitKey?: SubmitKey
}

function makeInitialGreeting(
  greeting: InitialGreeting,
  messagesLength: number,
  held = false,
): GreetingData {
  const persistent = greeting.options.persistent === true
  const status: GreetingData["status"] = held
    ? "held"
    : !persistent && messagesLength > 0
      ? "dismissed"
      : "visible"
  return {
    content: greeting.content,
    contentType: greeting.contentType,
    streaming: false,
    status,
    options: greeting.options,
    blocks: [
      {
        type: "content",
        content: greeting.content,
        contentType: greeting.contentType,
      },
    ],
  }
}

export function ChatApp({
  transport,
  shinyLifecycle,
  elementId,
  iconAssistant,
  iconSend,
  inputId,
  cancelId,
  uploadAccept = [],
  maxUploadSize = null,
  placeholder,
  initialMessages,
  initialGreeting,
  restorePending = false,
  initialDrawer,
  drawerSource,
  enableCancel,
  enableUpload,
  asideFavicon = true,
  showHistory = true,
  toolGrouping,
  toolbarEl,
  footerEl,
  slashCommandId = "",
  submitKey,
}: ChatAppProps) {
  const resolvedToolGrouping = toolGrouping ?? initialState.toolGrouping
  // Put preloaded/restored messages through the same block-construction pass
  // as live ones — thinking split first — so a restored transcript carries
  // identical ThinkingDisplay blocks.
  const messages = useMemo(
    () =>
      (initialMessages ?? []).map((m) => {
        const blocks = m.blocks.flatMap((b) =>
          b.type === "content"
            ? splitThinkingBlocks(b.content, b.contentType)
            : [b],
        )
        return { ...m, blocks, content: contentFromBlocks(blocks) }
      }),
    [initialMessages],
  )
  const [state, dispatch] = useReducer(chatReducer, {
    ...initialState,
    inputPlaceholder: placeholder ?? initialState.inputPlaceholder,
    messages,
    greeting: initialGreeting
      ? makeInitialGreeting(initialGreeting, messages.length, restorePending)
      : null,
    enableCancel: enableCancel ?? initialState.enableCancel,
    enableCancelExplicit: enableCancel !== undefined,
    enableUpload: enableUpload ?? initialState.enableUpload,
    enableUploadExplicit: enableUpload !== undefined,
    toolGrouping: resolvedToolGrouping,
    drawer: initialDrawer ?? initialState.drawer,
  })

  // `tool-grouping` is a live attribute: the custom element re-renders this
  // component when it changes, and the reducer re-routes the settled transcript
  // at the new mode. No-ops on mount, where the prop already seeded the state.
  useEffect(() => {
    dispatch({ type: "SET_TOOL_GROUPING", grouping: resolvedToolGrouping })
  }, [resolvedToolGrouping])

  const historyStore = useMemo(() => getHistoryStore(elementId), [elementId])

  useEffect(() => {
    return acquireHistoryStore(elementId, transport).release
  }, [elementId, historyStore, transport])

  const containerRef = useRef<ChatContainerHandle>(null)
  const siblingNavigationPendingRef = useRef(false)
  const [siblingNavigationPending, setSiblingNavigationPending] =
    useState(false)

  // The textarea is fully uncontrolled, so value/focus mutations go through
  // the imperative handle rather than the reducer.
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
      if (action.type === "history_navigate") {
        setCurrentConversationId(elementId, action.active_id)
        navigateTo(action.url, action.reload === true)
        return
      }
      if (action.type === "update_input") {
        // Placeholder updates go through the reducer (it's the only
        // remaining field the reducer tracks for update_input).
        if (action.placeholder !== undefined) {
          dispatch({ type: "update_input", placeholder: action.placeholder })
        }

        // Value and focus are always imperative — the textarea is
        // fully uncontrolled, so the reducer never touches its value.
        if (action.value !== undefined || action.attachments !== undefined) {
          containerRef.current?.setInputValue(action.value, {
            submit: action.submit,
            focus: action.focus,
            attachments: action.attachments,
            attachmentMode: action.attachment_mode,
          })
        } else if (action.focus) {
          containerRef.current?.focus()
        }
        return
      }
      if (action.type === "history_update") {
        historyStore.updateHistory({
          enabled: action.enabled,
          conversations: action.conversations,
          activeId: action.active_id,
        })
        dispatch({
          type: "greeting_settle",
          restored: action.active_id != null,
        })
        if (action.enabled) {
          setCurrentConversationId(elementId, action.active_id)
        }
        if (siblingNavigationPendingRef.current) {
          siblingNavigationPendingRef.current = false
          setSiblingNavigationPending(false)
          containerRef.current?.endSiblingNavigation()
        }
        return
      }
      dispatch(action)
    })
    return unsubscribe
  }, [transport, elementId, historyStore])

  // State-driven `<inputId>_greeting_requested` input.
  //
  // Fires when all three conditions hold: the chat container is visible
  // (IntersectionObserver), no messages exist, and no greeting is set.
  // Visibility gating covers hidden tabs and scrolled-out-of-view cases.
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!elementId) return
    const el = document.getElementById(elementId)
    if (!el) return
    if (typeof IntersectionObserver === "undefined") {
      setIsVisible(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => setIsVisible(entries[0]?.isIntersecting ?? false),
      { threshold: 0 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [elementId])

  const shouldRequestGreeting =
    isVisible && state.messages.length === 0 && state.greeting === null

  const greetingRequestSentRef = useRef(false)

  useEffect(() => {
    if (!shouldRequestGreeting) {
      greetingRequestSentRef.current = false
      return
    }
    if (greetingRequestSentRef.current) return
    if (!window.Shiny?.setInputValue) return

    greetingRequestSentRef.current = true
    window.Shiny.setInputValue(`${elementId}_greeting_requested`, Date.now(), {
      priority: "event",
    })
  }, [shouldRequestGreeting, elementId])

  // Safety net: a held greeting is normally released by the first
  // history_update. If history is server-disabled (or init fails) despite a
  // stale stored conversation ID, no history_update ever arrives — release
  // the greeting after a generous timeout rather than hiding it forever.
  const greetingIsHeld = state.greeting?.status === "held"
  useEffect(() => {
    if (!greetingIsHeld) return
    const timer = setTimeout(
      () => dispatch({ type: "greeting_settle", restored: false }),
      15000,
    )
    return () => clearTimeout(timer)
  }, [greetingIsHeld])

  // "Restoring conversation…" indicator, shown only when the hold outlasts
  // a short delay so fast restores don't flicker it.
  const [showRestoring, setShowRestoring] = useState(false)
  useEffect(() => {
    if (!greetingIsHeld) {
      setShowRestoring(false)
      return
    }
    const timer = setTimeout(() => setShowRestoring(true), 500)
    return () => clearTimeout(timer)
  }, [greetingIsHeld])

  const greetingIsDismissed = state.greeting?.status === "dismissed"
  // Note: greetingDismissedSentRef resets on remount. If the greeting reaches
  // "dismissed" again after a remount, the effect re-fires setInputValue. In
  // practice, the server replays the greeting as "visible" on reconnect, so
  // dismissed state is only reached via real user interaction.
  const greetingDismissedSentRef = useRef(false)

  useEffect(() => {
    if (!window.Shiny?.setInputValue) return
    if (greetingIsDismissed && !greetingDismissedSentRef.current) {
      greetingDismissedSentRef.current = true
      window.Shiny.setInputValue(
        `${elementId}_greeting_dismissed`,
        Date.now(),
        { priority: "event" },
      )
    } else if (!greetingIsDismissed && greetingDismissedSentRef.current) {
      greetingDismissedSentRef.current = false
      window.Shiny.setInputValue(`${elementId}_greeting_dismissed`, null)
    }
  }, [greetingIsDismissed, elementId])

  useLayoutEffect(() => {
    historyStore.setBusy(state.streamingMessage !== null)
  }, [historyStore, state.streamingMessage])

  const handleEdit = useCallback(
    (index: number, content: string, attachments: AttachmentPayload[]) => {
      transport.sendMessageEdit(elementId, index, content, attachments)
    },
    [transport, elementId],
  )

  const handleNavigate = useCallback(
    (index: number, direction: "prev" | "next") => {
      if (siblingNavigationPendingRef.current) return

      siblingNavigationPendingRef.current = true
      setSiblingNavigationPending(true)
      containerRef.current?.beginSiblingNavigation()
      transport.sendMessageNavigate(elementId, index, direction)
    },
    [transport, elementId],
  )

  const supersededRequests = useSupersededRequests(
    state.messages,
    state.streamingMessage,
  )
  const toolState: ChatToolState = useMemo(
    () => ({ supersededRequests }),
    [supersededRequests],
  )

  return (
    <ShinyLifecycleContext.Provider value={shinyLifecycle}>
      <ChatToolContext.Provider value={toolState}>
        <ToolGroupingContext.Provider value={state.toolGrouping}>
          <ChatDispatchContext.Provider value={dispatch}>
            <AsideFaviconContext.Provider value={asideFavicon}>
              <ChatContainer
                ref={containerRef}
                transport={transport}
                messages={state.messages}
                streamingMessage={state.streamingMessage}
                inputDisabled={state.inputDisabled}
                inputPlaceholder={state.inputPlaceholder}
                iconAssistant={iconAssistant}
                iconSend={iconSend}
                inputId={inputId}
                uploadAccept={uploadAccept}
                maxUploadSize={maxUploadSize}
                elementId={elementId}
                greeting={state.greeting}
                restoring={greetingIsHeld && showRestoring}
                cancelId={cancelId}
                enableCancel={state.enableCancel}
                enableUpload={state.enableUpload}
                cancelRequested={state.cancelRequested}
                toolbarEl={toolbarEl}
                footerEl={footerEl}
                slashCommands={state.slashCommands}
                slashCommandId={slashCommandId}
                submitKey={submitKey}
                historyStore={historyStore}
                onEdit={handleEdit}
                onNavigate={handleNavigate}
                siblingNavigationPending={siblingNavigationPending}
                showHistory={showHistory}
                drawer={state.drawer}
                drawerSource={drawerSource}
              />
            </AsideFaviconContext.Provider>
          </ChatDispatchContext.Provider>
        </ToolGroupingContext.Provider>
      </ChatToolContext.Provider>
    </ShinyLifecycleContext.Provider>
  )
}
