import {
  useReducer,
  useEffect,
  useLayoutEffect,
  useRef,
  useMemo,
  useState,
  useCallback,
  useSyncExternalStore,
} from "react"
import {
  ShinyLifecycleContext,
  ChatToolContext,
  ChatDispatchContext,
  ToolGroupingContext,
  AsideFaviconContext,
} from "./context"
import { setCurrentConversationId } from "./currentConversation"
import { uuid } from "../utils/uuid"
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
  type AnyAction,
} from "./state"
import {
  useRequestDefinitionIcons,
  useSupersededRequests,
} from "./useSupersededRequests"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
import {
  acquireHistoryStore,
  getHistoryStore,
  isHistorySubmissionBlocked,
} from "./historyStore"
import { StreamSmoother } from "../streaming/StreamSmoother"
import type {
  ChatTransport,
  ShinyLifecycle,
  GreetingOptions,
  ContentType,
  ChatAction,
} from "../transport/types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"
import type { SubmitKey } from "./tiptap/submitShortcut"
import type { AttachmentPayload } from "./attachments"

interface ChunkMeta {
  content_type?: ContentType
  html_deps?: HtmlDep[]
}

// Actions that start new content or wipe the transcript. Arriving while a
// finished stream's tail is draining, they complete the drain immediately
// (the user or server has moved on). Everything else waits for the drain.
const ENDS_DRAIN = new Set<ChatAction["type"]>([
  "message",
  "chunk_start",
  "chunk",
  "block_insert",
  "chunk_end",
  "clear",
  "greeting",
  "greeting_start",
  "greeting_chunk",
  "greeting_end",
  "greeting_clear",
  "history_navigate",
])

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
  thinkingShowAfter?: number
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
  thinkingShowAfter = 0,
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
  const historySnapshot = useSyncExternalStore(
    historyStore.subscribe,
    historyStore.getSnapshot,
    historyStore.getSnapshot,
  )
  const submissionBlocked = isHistorySubmissionBlocked(historySnapshot)

  useEffect(() => {
    return acquireHistoryStore(elementId, transport).release
  }, [elementId, historyStore, transport])

  const containerRef = useRef<ChatContainerHandle>(null)
  const messagesRef = useRef(state.messages)
  useLayoutEffect(() => {
    messagesRef.current = state.messages
  }, [state.messages])
  const smootherRef = useRef<StreamSmoother<ChunkMeta> | null>(null)
  // Set on CANCEL_REQUESTED: providers can keep sending chunks after a
  // cancel, and those must append raw rather than pace in — stopping should
  // stop the motion. Cleared when the next stream starts.
  const pacingBypassedRef = useRef(false)
  const siblingNavigationPendingRef = useRef(false)
  const [siblingNavigationPending, setSiblingNavigationPending] =
    useState(false)

  // The textarea is fully uncontrolled, so value/focus mutations go through
  // the imperative handle rather than the reducer.
  useEffect(() => {
    const smoother = new StreamSmoother<ChunkMeta>({
      onEmit: (text, meta, isFirstSlice) => {
        dispatch({
          type: "chunk",
          content: text,
          operation: "append",
          content_type: meta.content_type,
          html_deps: isFirstSlice ? meta.html_deps : undefined,
        })
      },
      // A chunk carrying html_deps starts its own entry so its deps are
      // forwarded exactly once.
      canMerge: (queued, incoming) =>
        queued.content_type === incoming.content_type &&
        !incoming.html_deps?.length,
    })
    smootherRef.current = smoother
    pacingBypassedRef.current = false

    // Actions that arrive while the tail of a finished stream is still
    // draining. Most (history_update, update_siblings, ...) must apply after
    // chunk_end lands, so they wait and replay in order rather than cutting
    // the drain short.
    let deferred: ChatAction[] = []

    const handleAction = (action: ChatAction) => {
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
          readOnly: action.active_read_only ?? false,
          readOnlyReason: action.active_read_only_reason,
          canResubmit: action.active_can_resubmit,
          transitionProtocol: action.transition_protocol,
        })
        dispatch({
          type: "greeting_settle",
          restored: action.active_id != null,
        })
        if (action.enabled) {
          setCurrentConversationId(elementId, action.active_id)
        }
        if (
          siblingNavigationPendingRef.current &&
          historyStore.getSnapshot().historyTransitionPending === null
        ) {
          siblingNavigationPendingRef.current = false
          setSiblingNavigationPending(false)
          containerRef.current?.endSiblingNavigation()
        }
        return
      }
      if (action.type === "history_transition_complete") {
        if (historyStore.completeHistoryTransition(action.requestId)) {
          if (siblingNavigationPendingRef.current) {
            siblingNavigationPendingRef.current = false
            setSiblingNavigationPending(false)
            containerRef.current?.endSiblingNavigation()
          }
        }
        return
      }
      if (action.type === "history_edit_projection") {
        // Server-owned edits use the staged exchange identity and never echo
        // the already received submission. Older producers retain their flow.
        if (action.submission_mode === "server" && !action.exchange_id) return
        if (!historyStore.acceptEditProjection(action.requestId)) return
        const client_message_id = action.exchange_id ?? uuid()
        dispatch({ type: "TRUNCATE_MESSAGES", index: action.index })
        dispatch({
          type: "INPUT_SENT",
          id: client_message_id,
          content: action.content,
          role: "user",
          ...(action.attachments.length > 0
            ? { attachments: action.attachments }
            : {}),
        })
        if (action.submission_mode !== "server") {
          transport.sendInput(inputId, {
            text: action.content,
            attachments: action.attachments,
            client_message_id,
          })
        }
        return
      }
      if (action.type === "chunk_start") {
        // A prior stream's tail was already completed on arrival (see
        // ENDS_DRAIN), and a fresh stream has nothing buffered worth keeping.
        smoother.dispose()
        pacingBypassedRef.current = false
        dispatch(action)
        return
      }
      if (pacingBypassedRef.current) {
        // Post-cancel stragglers skip pacing *and* the drain deferral below.
        dispatch(action)
        return
      }
      if (action.type === "chunk") {
        if (action.operation === "replace") {
          // A replace chunk wipes the whole in-flight message, so anything
          // still buffered from before it would just get wiped a moment
          // later — discard rather than flush.
          smoother.dispose()
          dispatch(action)
        } else {
          smoother.push(action.content, {
            content_type: action.content_type,
            html_deps: action.html_deps,
          })
        }
        return
      }
      if (action.type === "block_insert") {
        // Preserve order: a block must render after any text pushed before
        // it, even if that text hasn't paced out yet.
        smoother.flush()
        dispatch(action)
        return
      }
      if (action.type === "chunk_end") {
        // Reveal the buffered tail quickly, then end the stream.
        smoother.finish(() => {
          dispatch(action)
          const pending = deferred
          deferred = []
          pending.forEach(handleAction)
        })
        return
      }
      dispatch(action)
    }

    const unsubscribe = transport.onMessage(elementId, (action) => {
      if (smoother.finishing) {
        if (!ENDS_DRAIN.has(action.type)) {
          deferred.push(action)
          return
        }
        // Runs the deferred chunk_end and replays queued actions first.
        smoother.flush()
      }
      handleAction(action)
    })
    return () => {
      smoother.dispose()
      smootherRef.current = null
      deferred = []
      unsubscribe()
    }
  }, [transport, elementId, historyStore, inputId, state.enableUpload])

  // Stopping should stop the motion: reveal whatever is buffered at once. If
  // the stream already ended and only its tail was draining, there is nothing
  // left to cancel — completing the drain is the whole effect, and recording
  // CANCEL_REQUESTED would leave a stale flag for the next stream.
  const chatDispatch = useCallback((action: AnyAction) => {
    if (action.type === "CANCEL_REQUESTED") {
      const smoother = smootherRef.current
      const wasFinishing = smoother?.finishing ?? false
      smoother?.flush()
      pacingBypassedRef.current = true
      if (wasFinishing) return
    }
    dispatch(action)
  }, [])

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
    historyStore.setBusy(
      state.streamingMessage !== null ||
        (historySnapshot.transitionProtocol === "completion-v2" &&
          state.inputDisabled),
    )
  }, [
    historyStore,
    historySnapshot.transitionProtocol,
    state.inputDisabled,
    state.streamingMessage,
  ])

  const handleEdit = useCallback(
    (index: number, content: string, attachments: AttachmentPayload[]) => {
      if (
        (historyStore.getSnapshot().readOnly &&
          (!historyStore.getSnapshot().canResubmit ||
            !messagesRef.current[index]?.exchange?.preparation_failed)) ||
        isHistorySubmissionBlocked(historyStore.getSnapshot()) ||
        historyStore.isMutationBlocked()
      )
        return
      const requestId = historyStore.beginEditTransition()
      if (requestId === null) {
        transport.sendMessageEdit(elementId, index, content, attachments)
      } else {
        transport.sendMessageEdit(
          elementId,
          index,
          content,
          attachments,
          requestId,
        )
      }
    },
    [transport, elementId, historyStore],
  )

  const handleNavigate = useCallback(
    (index: number, direction: "prev" | "next") => {
      if (
        siblingNavigationPendingRef.current ||
        isHistorySubmissionBlocked(historyStore.getSnapshot()) ||
        historyStore.isMutationBlocked()
      )
        return

      const requestId = historyStore.beginNavigationTransition()
      siblingNavigationPendingRef.current = true
      setSiblingNavigationPending(true)
      containerRef.current?.beginSiblingNavigation()
      if (requestId === null) {
        transport.sendMessageNavigate(elementId, index, direction)
      } else {
        transport.sendMessageNavigate(elementId, index, direction, requestId)
      }
    },
    [transport, elementId, historyStore],
  )

  const handleRetry = useCallback(
    (index: number) => {
      if (
        (historyStore.getSnapshot().readOnly &&
          (!historyStore.getSnapshot().canResubmit ||
            !messagesRef.current[index]?.exchange?.preparation_failed)) ||
        isHistorySubmissionBlocked(historyStore.getSnapshot()) ||
        historyStore.isMutationBlocked()
      )
        return
      const requestId = historyStore.beginEditTransition()
      if (requestId === null) return
      transport.sendMessageResubmit(elementId, index, "retry", requestId)
    },
    [transport, elementId, historyStore],
  )

  const supersededRequests = useSupersededRequests(
    state.messages,
    state.streamingMessage,
  )
  const requestDefinitionIcons = useRequestDefinitionIcons(
    state.messages,
    state.streamingMessage,
  )
  const toolState: ChatToolState = useMemo(
    () => ({ supersededRequests, requestDefinitionIcons }),
    [supersededRequests, requestDefinitionIcons],
  )

  return (
    <ShinyLifecycleContext.Provider value={shinyLifecycle}>
      <ChatToolContext.Provider value={toolState}>
        <ToolGroupingContext.Provider value={state.toolGrouping}>
          <ChatDispatchContext.Provider value={chatDispatch}>
            <AsideFaviconContext.Provider value={asideFavicon}>
              <ChatContainer
                ref={containerRef}
                transport={transport}
                messages={state.messages}
                streamingMessage={state.streamingMessage}
                inputDisabled={state.inputDisabled}
                submissionBlocked={submissionBlocked}
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
                thinkingShowAfter={thinkingShowAfter}
                cancelRequested={state.cancelRequested}
                toolbarEl={toolbarEl}
                footerEl={footerEl}
                slashCommands={state.slashCommands}
                slashCommandId={slashCommandId}
                submitKey={submitKey}
                historyStore={historyStore}
                onEdit={handleEdit}
                onNavigate={handleNavigate}
                onRetry={handleRetry}
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
