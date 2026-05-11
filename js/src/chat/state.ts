import type {
  ChatAction,
  ContentType,
  MessagePayload,
} from "../transport/types"
import { uuid } from "../utils/uuid"

export interface ContentSegment {
  content: string
  contentType: ContentType
}

export interface ChatMessageData {
  id: string
  role: "user" | "assistant"
  content: string
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
  segments: ContentSegment[]
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
  const segments: ContentSegment[] = msg.segments.map((s) => ({
    content: s.content,
    contentType: s.content_type,
  }))

  return {
    id: msg.id ?? uuid(),
    role: msg.role,
    content: segments.map((s) => s.content).join(""),
    streaming: false,
    icon: msg.icon,
    segments,
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
        streaming: false,
        segments: [{ content: action.content, contentType: "markdown" }],
      }
      const loadingMsg: ChatMessageData = {
        id: uuid(),
        role: "assistant",
        content: "",
        streaming: false,
        isPlaceholder: true,
        segments: [{ content: "", contentType: "markdown" }],
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

      // segments is always non-empty: initialized with at least one segment on chunk_start
      const chunkType =
        action.content_type ??
        last.segments[last.segments.length - 1]!.contentType

      if (action.operation === "replace") {
        const segments = [{ content: action.content, contentType: chunkType }]
        return {
          ...state,
          streamingMessage: {
            ...last,
            content: action.content,
            segments,
          },
        }
      }

      const segments = [...last.segments]
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

    default: {
      const _exhaustive: never = action
      void _exhaustive
      return state
    }
  }
}
