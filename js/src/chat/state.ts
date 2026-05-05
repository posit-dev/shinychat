import type {
  ContentType,
  ChatAction,
  MessagePayload,
} from "../transport/types"
import { uuid } from "../utils/uuid"

export interface ContentBlock {
  type: "content"
  content: string
  contentType: ContentType
}

export interface ThinkingBlock {
  type: "thinking"
  content: string
  topic?: string | null
  topicBuffer?: string
  startedAt?: number
  durationMs?: number
  streaming: boolean
}

export type MessageBlock = ContentBlock | ThinkingBlock

export interface ChatMessageData {
  id: string
  role: "user" | "assistant"
  content: string
  contentType: ContentType
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
  blocks: MessageBlock[]
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
      blocks: [
        {
          type: "thinking",
          content: msg.content,
          streaming: false,
          startedAt: Date.now(),
        },
      ],
    }
  }
  return {
    id: msg.id ?? uuid(),
    role: msg.role,
    content: msg.content,
    contentType: msg.content_type,
    streaming: false,
    icon: msg.icon,
    blocks: [
      { type: "content", content: msg.content, contentType: msg.content_type },
    ],
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
        blocks: [
          { type: "content", content: action.content, contentType: "markdown" },
        ],
      }
      const loadingMsg: ChatMessageData = {
        id: uuid(),
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
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

      const lastBlock = last.blocks[last.blocks.length - 1]
      const chunkType =
        action.content_type ??
        (lastBlock?.type === "thinking"
          ? "thinking"
          : ((lastBlock as ContentBlock | undefined)?.contentType ??
            "markdown"))

      const blocks = [...last.blocks]

      if (chunkType === "thinking") {
        const tail = lastBlock?.type === "thinking" ? lastBlock : null
        if (tail) {
          const { cleaned, topic, buffer } = extractTopics(
            action.content,
            tail.topicBuffer ?? "",
          )
          blocks[blocks.length - 1] = {
            ...tail,
            content: tail.content + cleaned,
            topicBuffer: buffer,
            ...(topic !== null ? { topic } : {}),
          }
        } else {
          // Start a new thinking block
          const { cleaned, topic, buffer } = extractTopics(action.content, "")
          blocks.push({
            type: "thinking",
            content: cleaned,
            topicBuffer: buffer,
            streaming: true,
            startedAt: Date.now(),
            ...(topic !== null ? { topic } : {}),
          })
        }
        return {
          ...state,
          streamingMessage: { ...last, blocks },
        }
      }

      // Non-thinking content: finalize any trailing thinking block
      if (lastBlock?.type === "thinking" && lastBlock.streaming) {
        blocks[blocks.length - 1] = {
          ...lastBlock,
          content: lastBlock.content + (lastBlock.topicBuffer ?? ""),
          topicBuffer: "",
          streaming: false,
          durationMs: lastBlock.startedAt
            ? Date.now() - lastBlock.startedAt
            : undefined,
        }
      }

      if (action.operation === "replace") {
        // Replace removes all content blocks and adds a single new one
        const newBlocks: MessageBlock[] = blocks.filter(
          (b) => b.type === "thinking",
        )
        newBlocks.push({
          type: "content",
          content: action.content,
          contentType: chunkType,
        })
        return {
          ...state,
          streamingMessage: {
            ...last,
            content: action.content,
            contentType: chunkType,
            blocks: newBlocks,
          },
        }
      } else {
        // Append: extend matching content block or start a new one
        const tail = blocks[blocks.length - 1]
        if (tail?.type === "content" && tail.contentType === chunkType) {
          blocks[blocks.length - 1] = {
            ...tail,
            content: tail.content + action.content,
          }
        } else {
          blocks.push({
            type: "content",
            content: action.content,
            contentType: chunkType,
          })
        }
      }

      const content = blocks
        .filter((b): b is ContentBlock => b.type === "content")
        .map((b) => b.content)
        .join("")

      return {
        ...state,
        streamingMessage: {
          ...last,
          content,
          contentType: chunkType,
          blocks,
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
  const blocks = msg.blocks.map((block) => {
    if (block.type === "thinking" && block.streaming) {
      return {
        ...block,
        content: block.content + (block.topicBuffer ?? ""),
        topicBuffer: "",
        streaming: false,
        durationMs: block.startedAt ? Date.now() - block.startedAt : undefined,
      }
    }
    return block
  })
  return { ...msg, streaming: false, blocks }
}
