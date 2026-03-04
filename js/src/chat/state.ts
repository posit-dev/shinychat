import type { ContentType, ChatAction, MessagePayload } from "../transport/types"

export interface ChatMessageData {
  id: string
  role: "user" | "assistant"
  content: string
  contentType: ContentType
  streaming: boolean
  icon?: string
}

export interface ChatState {
  messages: ChatMessageData[]
  inputDisabled: boolean
  inputValue: string
  inputPlaceholder: string
  hiddenToolRequests: Set<string>
}

// Actions that originate from the UI (not from the server)
export type UIAction =
  | { type: "INPUT_SENT"; content: string; role: "user" }
  | { type: "HIDE_TOOL_REQUEST"; requestId: string }

export type AnyAction = ChatAction | UIAction

export const initialState: ChatState = {
  messages: [],
  inputDisabled: false,
  inputValue: "",
  inputPlaceholder: "Enter a message...",
  hiddenToolRequests: new Set(),
}

function messagePayloadToData(msg: MessagePayload): ChatMessageData {
  return {
    id: msg.id ?? crypto.randomUUID(),
    role: msg.role,
    content: msg.content,
    contentType: msg.content_type,
    streaming: false,
    icon: msg.icon,
  }
}

function removeLoadingMessage(messages: ChatMessageData[]): ChatMessageData[] {
  const last = messages[messages.length - 1]
  if (last && last.role === "assistant" && last.content.trim() === "") {
    return messages.slice(0, -1)
  }
  return messages
}

export function chatReducer(state: ChatState, action: AnyAction): ChatState {
  switch (action.type) {
    case "INPUT_SENT": {
      const userMsg: ChatMessageData = {
        id: crypto.randomUUID(),
        role: "user",
        content: action.content,
        contentType: "semi-markdown",
        streaming: false,
      }
      const loadingMsg: ChatMessageData = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
      }
      return {
        ...state,
        messages: [...state.messages, userMsg, loadingMsg],
        inputDisabled: true,
        inputValue: "",
      }
    }

    case "message": {
      const messages = removeLoadingMessage(state.messages)
      return {
        ...state,
        messages: [...messages, messagePayloadToData(action.message)],
        inputDisabled: false,
      }
    }

    case "chunk_start": {
      const messages = removeLoadingMessage(state.messages)
      const newMsg = messagePayloadToData(action.message)
      newMsg.streaming = true
      return {
        ...state,
        messages: [...messages, newMsg],
        inputDisabled: true,
      }
    }

    case "chunk": {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (!last) return state

      const content =
        action.operation === "append"
          ? last.content + action.content
          : action.content

      messages[messages.length - 1] = { ...last, content }
      return { ...state, messages }
    }

    case "chunk_end": {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (!last) return state

      messages[messages.length - 1] = { ...last, streaming: false }
      return { ...state, messages, inputDisabled: false }
    }

    case "clear":
      return { ...state, messages: [] }

    case "update_input":
      return {
        ...state,
        inputValue: action.value ?? state.inputValue,
        inputPlaceholder: action.placeholder ?? state.inputPlaceholder,
      }

    case "remove_loading": {
      return {
        ...state,
        messages: removeLoadingMessage(state.messages),
        inputDisabled: false,
      }
    }

    case "HIDE_TOOL_REQUEST": {
      const newSet = new Set(state.hiddenToolRequests)
      newSet.add(action.requestId)
      return { ...state, hiddenToolRequests: newSet }
    }

    default:
      return state
  }
}
