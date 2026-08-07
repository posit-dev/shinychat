import {
  useReducer,
  useEffect,
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
  ChatSubmitContext,
} from "./context"
import { setCurrentConversationId } from "./currentConversation"
import { navigateTo } from "../utils/navigate"
import {
  chatReducer,
  initialState,
  routeToolBlocks,
  splitThinkingBlocks,
  contentFromBlocks,
  buildMessagesSnapshot,
  type ChatMessageData,
  type ChatToolState,
  type GreetingData,
  type ToolGrouping,
} from "./state"
import { useSupersededRequests } from "./useSupersededRequests"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
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
  inputId: string
  cancelId?: string
  uploadAccept?: string[]
  maxUploadSize?: number | null
  placeholder?: string
  initialMessages?: ChatMessageData[]
  initialGreeting?: InitialGreeting
  enableCancel?: boolean
  enableUpload?: boolean
  toolGrouping?: ToolGrouping
  footerEl?: Element
  slashCommandId?: string
  submitKey?: SubmitKey
}

function makeInitialGreeting(
  greeting: InitialGreeting,
  messagesLength: number,
): GreetingData {
  const persistent = greeting.options.persistent === true
  const status: GreetingData["status"] =
    !persistent && messagesLength > 0 ? "dismissed" : "visible"
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
  inputId,
  cancelId,
  uploadAccept = [],
  maxUploadSize = null,
  placeholder,
  initialMessages,
  initialGreeting,
  enableCancel,
  enableUpload,
  toolGrouping,
  footerEl,
  slashCommandId = "",
  submitKey,
}: ChatAppProps) {
  const resolvedToolGrouping = toolGrouping ?? initialState.toolGrouping
  // Put preloaded/restored messages through the same block-construction pass as
  // live ones — thinking split first, then the content router — so a restored
  // transcript carries identical ThinkingDisplay and tool_loop grouping.
  const messages = useMemo(
    () =>
      (initialMessages ?? []).map((m) => {
        const split = m.blocks.flatMap((b) =>
          b.type === "content"
            ? splitThinkingBlocks(b.content, b.contentType)
            : [b],
        )
        const blocks = routeToolBlocks(split, resolvedToolGrouping, m.role)
        return { ...m, blocks, content: contentFromBlocks(blocks) }
      }),
    [initialMessages, resolvedToolGrouping],
  )
  const [state, dispatch] = useReducer(chatReducer, {
    ...initialState,
    inputPlaceholder: placeholder ?? initialState.inputPlaceholder,
    messages,
    greeting: initialGreeting
      ? makeInitialGreeting(initialGreeting, messages.length)
      : null,
    enableCancel: enableCancel ?? initialState.enableCancel,
    enableCancelExplicit: enableCancel !== undefined,
    enableUpload: enableUpload ?? initialState.enableUpload,
    enableUploadExplicit: enableUpload !== undefined,
    toolGrouping: resolvedToolGrouping,
  })

  // `tool-grouping` is a live attribute: the custom element re-renders this
  // component when it changes, and the reducer re-routes the settled transcript
  // at the new mode. No-ops on mount, where the prop already seeded the state.
  useEffect(() => {
    dispatch({ type: "SET_TOOL_GROUPING", grouping: resolvedToolGrouping })
  }, [resolvedToolGrouping])

  const stateRef = useRef(state)
  stateRef.current = state

  const reportSnapshot = useCallback(() => {
    // Reports the entire settled transcript (all messages plus retained
    // htmlDeps) on every change, so a session sends ~O(n^2) bytes over its
    // lifetime. Fine for typical conversations; if very long transcripts
    // become common, revisit with a delta/append protocol.
    transport.sendMessagesSnapshot(
      elementId,
      buildMessagesSnapshot(stateRef.current),
    )
  }, [transport, elementId])

  useEffect(() => {
    reportSnapshot()
  }, [state.messages, reportSnapshot])

  const submitUserInput = useCallback(
    (content: string, attachments: AttachmentPayload[]) => {
      // Optimistic UI update (adds user message + loading placeholder).
      dispatch({
        type: "INPUT_SENT",
        content,
        role: "user",
        ...(attachments.length > 0 ? { attachments } : {}),
      })
      // Build the snapshot from CURRENT settled state, then append the just-
      // submitted user turn. Co-send userInput + snapshot in the SAME tick so
      // Shiny batches them into one flush (server sees the turn in
      // on_user_submit).
      const snapshot = buildMessagesSnapshot(stateRef.current)
      snapshot.push({
        role: "user",
        segments: [{ content, content_type: "markdown" }],
        ...(attachments.length > 0 ? { attachments } : {}),
      })
      const uploadOn = stateRef.current.enableUpload
      transport.sendInput(
        inputId,
        uploadOn ? { text: content, attachments } : content,
      )
      // The INPUT_SENT dispatch above also mutates state.messages, so the
      // reportSnapshot effect fires a second, near-identical snapshot on the
      // next render. That's intentional: this manual send is the one that
      // co-batches with userInput in the current flush, and the server's
      // save is idempotent, so the follow-up snapshot is a harmless no-op.
      transport.sendMessagesSnapshot(elementId, snapshot)
    },
    [dispatch, transport, inputId, elementId],
  )

  const containerRef = useRef<ChatContainerHandle>(null)
  const siblingNavigationPendingRef = useRef(false)
  const [siblingNavigationPending, setSiblingNavigationPending] =
    useState(false)

  // The textarea is fully uncontrolled, so value/focus mutations go through
  // the imperative handle rather than the reducer.
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
      if (action.type === "history_navigate") {
        // localStorage is also written below from state.history.activeId
        // (set by the "history_update" reducer case). The server always
        // sends these two messages with the same id, in order, on a single
        // connection, so the two writers never disagree in practice — but
        // that's a server-side invariant, not something enforced here.
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
      dispatch(action)
      if (
        action.type === "history_update" &&
        siblingNavigationPendingRef.current
      ) {
        siblingNavigationPendingRef.current = false
        setSiblingNavigationPending(false)
        containerRef.current?.endSiblingNavigation()
      }
    })
    return unsubscribe
  }, [transport, elementId])

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

  useEffect(() => {
    if (!state.history.enabled) return
    setCurrentConversationId(elementId, state.history.activeId)
  }, [elementId, state.history.enabled, state.history.activeId])

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
            <ChatSubmitContext.Provider value={submitUserInput}>
              <ChatContainer
                ref={containerRef}
                transport={transport}
                messages={state.messages}
                streamingMessage={state.streamingMessage}
                inputDisabled={state.inputDisabled}
                inputPlaceholder={state.inputPlaceholder}
                iconAssistant={iconAssistant}
                inputId={inputId}
                uploadAccept={uploadAccept}
                maxUploadSize={maxUploadSize}
                elementId={elementId}
                greeting={state.greeting}
                cancelId={cancelId}
                enableCancel={state.enableCancel}
                enableUpload={state.enableUpload}
                cancelRequested={state.cancelRequested}
                footerEl={footerEl}
                slashCommands={state.slashCommands}
                slashCommandId={slashCommandId}
                submitKey={submitKey}
                historyEnabled={state.history.enabled}
                historyConversations={state.history.conversations}
                historyActiveId={state.history.activeId}
                onEdit={handleEdit}
                onNavigate={handleNavigate}
                siblingNavigationPending={siblingNavigationPending}
              />
            </ChatSubmitContext.Provider>
          </ChatDispatchContext.Provider>
        </ToolGroupingContext.Provider>
      </ChatToolContext.Provider>
    </ShinyLifecycleContext.Provider>
  )
}
