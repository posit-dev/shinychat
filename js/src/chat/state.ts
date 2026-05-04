import type {
  ContentType,
  ChatAction,
  MessagePayload,
} from "../transport/types"
import { uuid } from "../utils/uuid"

export interface ContentSegment {
  content: string
  contentType: ContentType
}

export interface ChatMessageData {
  id: string
  role: "user" | "assistant" | "thinking"
  content: string
  contentType: ContentType
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
  segments?: ContentSegment[]
  /** Duration in milliseconds, set when thinking_end arrives. */
  durationMs?: number
  /** Current topic label for thinking messages. */
  topic?: string | null
  /** Timestamp (Date.now()) when thinking started, for client-side duration fallback. */
  startedAt?: number
}

export interface ChatInputState {
  inputDisabled: boolean
  inputPlaceholder: string
}

export interface ChatToolState {
  hiddenToolRequests: Set<string>
}

export interface ChatState extends ChatInputState, ChatToolState {
  messages: ChatMessageData[]
  streamingMessage: ChatMessageData | null
}

// Actions that originate from the UI (not from the server)
export type UIAction = {
  type: "INPUT_SENT"
  content: string
  role: "user"
}

export type AnyAction = ChatAction | UIAction

export const initialState: ChatState = {
  messages: [],
  streamingMessage: null,
  inputDisabled: false,
  inputPlaceholder: "Enter a message...",
  hiddenToolRequests: new Set(),
}

function messagePayloadToData(msg: MessagePayload): ChatMessageData {
  return {
    id: msg.id ?? uuid(),
    role: msg.role,
    content: msg.content,
    contentType: msg.content_type,
    streaming: false,
    icon: msg.icon,
    segments: [{ content: msg.content, contentType: msg.content_type }],
  }
}

function removeLoadingMessage(messages: ChatMessageData[]): ChatMessageData[] {
  return messages.filter((m) => !m.isPlaceholder)
}

export function chatReducer(state: ChatState, action: AnyAction): ChatState {
  switch (action.type) {
    case "INPUT_SENT": {
      const userMsg: ChatMessageData = {
        id: uuid(),
        role: "user",
        content: action.content,
        contentType: "markdown",
        streaming: false,
      }
      const loadingMsg: ChatMessageData = {
        id: uuid(),
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      return {
        ...state,
        messages: [...state.messages, userMsg, loadingMsg],
        inputDisabled: true,
      }
    }

    case "message": {
      const messages = removeLoadingMessage(state.messages)
      return {
        ...state,
        messages: [...messages, messagePayloadToData(action.message)],
        streamingMessage: null,
        inputDisabled: false,
      }
    }

    case "chunk_start": {
      const messages = removeLoadingMessage(state.messages)
      const newMsg = messagePayloadToData(action.message)
      newMsg.streaming = true
      return {
        ...state,
        messages,
        streamingMessage: newMsg,
        inputDisabled: true,
      }
    }

    case "chunk": {
      const last = state.streamingMessage
      if (!last || !last.streaming) return state

      const chunkType =
        action.content_type ??
        last.segments![last.segments!.length - 1]!.contentType

      if (action.operation === "replace") {
        const segments = [{ content: action.content, contentType: chunkType }]
        return {
          ...state,
          streamingMessage: {
            ...last,
            content: action.content,
            contentType: chunkType,
            segments,
          },
        }
      }

      const segments = [...last.segments!]
      const current = segments[segments.length - 1]!

      if (chunkType !== current.contentType) {
        segments.push({ content: action.content, contentType: chunkType })
      } else {
        const content = current.content + action.content
        segments[segments.length - 1] = { ...current, content }
      }

      const content = segments.map((s) => s.content).join("")

      return {
        ...state,
        streamingMessage: {
          ...last,
          content,
          contentType: chunkType,
          segments,
        },
      }
    }

    case "chunk_end": {
      const last = state.streamingMessage
      if (!last || !last.streaming) return state

      return {
        ...state,
        messages: [...state.messages, { ...last, streaming: false }],
        streamingMessage: null,
        inputDisabled: false,
      }
    }

    case "clear":
      return {
        ...initialState,
        inputPlaceholder: state.inputPlaceholder,
      }

    case "update_input":
      return {
        ...state,
        inputPlaceholder: action.placeholder ?? state.inputPlaceholder,
      }

    case "remove_loading": {
      return {
        ...state,
        messages: removeLoadingMessage(state.messages),
        streamingMessage: null,
        inputDisabled: false,
      }
    }

    case "hide_tool_request": {
      if (state.hiddenToolRequests.has(action.requestId)) return state
      const newSet = new Set(state.hiddenToolRequests)
      newSet.add(action.requestId)
      return { ...state, hiddenToolRequests: newSet }
    }

    case "thinking_start": {
      const messages = removeLoadingMessage(state.messages)
      const thinkingMsg: ChatMessageData = {
        id: uuid(),
        role: "thinking",
        content: "",
        contentType: "markdown",
        streaming: true,
        startedAt: Date.now(),
      }
      return {
        ...state,
        messages,
        streamingMessage: thinkingMsg,
        inputDisabled: true,
      }
    }

    case "thinking": {
      const last = state.streamingMessage
      if (!last || last.role !== "thinking") return state

      return {
        ...state,
        streamingMessage: {
          ...last,
          content: last.content + action.content,
          ...(action.topic !== undefined ? { topic: action.topic } : {}),
        },
      }
    }

    case "thinking_end": {
      const last = state.streamingMessage
      if (!last || last.role !== "thinking") return state

      return {
        ...state,
        messages: [
          ...state.messages,
          { ...last, streaming: false, durationMs: action.duration_ms },
        ],
        streamingMessage: null,
        inputDisabled: true,
      }
    }

    default: {
      const _exhaustive: never = action
      void _exhaustive
      return state
    }
  }
}
