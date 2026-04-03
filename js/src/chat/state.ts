import type {
  ContentType,
  ChatAction,
  MessagePayload,
} from "../transport/types"
import { uuid } from "../utils/uuid"

export interface ChatMessageData {
  id: string
  role: "user" | "assistant"
  content: string
  contentType: ContentType
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
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

      const content =
        action.operation === "append"
          ? last.content + action.content
          : action.content

      // Update contentType if the chunk provides one (e.g., transition
      // from "markdown" to "html" when UI elements appear mid-stream)
      const contentType = action.content_type ?? last.contentType

      return { ...state, streamingMessage: { ...last, content, contentType } }
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
