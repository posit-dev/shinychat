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

export interface ThinkingData {
  content: string
  topic?: string | null
  topicBuffer?: string
  startedAt?: number
  durationMs?: number
  streaming: boolean
}

export interface ChatMessageData {
  id: string
  role: "user" | "assistant"
  content: string
  contentType: ContentType
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
  segments?: ContentSegment[]
  thinking?: ThinkingData
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
  if (msg.content_type === "thinking") {
    return {
      id: msg.id ?? uuid(),
      role: "assistant",
      content: "",
      contentType: "markdown",
      streaming: false,
      icon: msg.icon,
      segments: [],
      thinking: {
        content: msg.content,
        streaming: false,
        startedAt: Date.now(),
      },
    }
  }
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

const TOPIC_TAG_RE = /<topic>(.*?)<\/topic>/g
const PARTIAL_OPEN_RE = /<(?:t(?:o(?:p(?:i(?:c(?:>[^<]*)?)?)?)?)?)?\s*$/

interface TopicResult {
  cleaned: string
  topic: string | null
  buffer: string
}

function extractTopics(text: string, buffer: string): TopicResult {
  let combined = buffer + text
  let topic: string | null = null

  // Replace complete <topic>...</topic> tags with bold markdown labels
  combined = combined.replace(TOPIC_TAG_RE, (_match, captured: string) => {
    topic = captured
    return `\n\n<div class="shinychat-thinking-topic">${captured}</div>\n\n`
  })

  // Check for partial opening tag at the end
  let newBuffer = ""
  const partialMatch = PARTIAL_OPEN_RE.exec(combined)
  if (partialMatch && partialMatch[0]) {
    newBuffer = partialMatch[0]
    combined = combined.slice(0, partialMatch.index)
  }

  return { cleaned: combined, topic, buffer: newBuffer }
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
        (last.thinking?.streaming
          ? "thinking"
          : last.segments![last.segments!.length - 1]!.contentType)

      // Thinking content: accumulate in the thinking field
      if (chunkType === "thinking") {
        const thinking = last.thinking ?? {
          content: "",
          streaming: true,
          startedAt: Date.now(),
        }
        const { cleaned, topic, buffer } = extractTopics(
          action.content,
          thinking.topicBuffer ?? "",
        )
        return {
          ...state,
          streamingMessage: {
            ...last,
            thinking: {
              ...thinking,
              content: thinking.content + cleaned,
              topicBuffer: buffer,
              streaming: true,
              ...(topic !== null ? { topic } : {}),
            },
          },
        }
      }

      // Non-thinking content arriving: finalize thinking if it was streaming
      const thinking = last.thinking?.streaming
        ? {
            ...last.thinking,
            streaming: false,
            durationMs: last.thinking.startedAt
              ? Date.now() - last.thinking.startedAt
              : undefined,
          }
        : last.thinking

      if (action.operation === "replace") {
        const segments = [{ content: action.content, contentType: chunkType }]
        return {
          ...state,
          streamingMessage: {
            ...last,
            content: action.content,
            contentType: chunkType,
            segments,
            thinking,
          },
        }
      }

      const segments = [...(last.segments ?? [])]
      const current = segments[segments.length - 1]

      if (!current || chunkType !== current.contentType) {
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
          thinking,
        },
      }
    }

    case "chunk_end": {
      const last = state.streamingMessage
      if (!last || !last.streaming) return state

      return {
        ...state,
        messages: [...state.messages, finalizeMessage(last)],
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

function finalizeMessage(msg: ChatMessageData): ChatMessageData {
  const finalized: ChatMessageData = { ...msg, streaming: false }
  if (finalized.thinking?.streaming) {
    finalized.thinking = {
      ...finalized.thinking,
      streaming: false,
      durationMs: finalized.thinking.startedAt
        ? Date.now() - finalized.thinking.startedAt
        : undefined,
    }
  }
  return finalized
}
