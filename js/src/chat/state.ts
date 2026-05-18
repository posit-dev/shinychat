import type {
  ContentType,
  ChatAction,
  MessagePayload,
  GreetingOptions,
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
  /** Tracks whether streaming content is inside an unclosed <thinking> tag */
  insideThinkingTag?: boolean
  /** Buffers partial tag text at chunk boundaries (e.g. "<thi" or "</thin") */
  tagBuffer?: string
  /** True when the stream was cancelled by the user before it completed. */
  cancelled?: boolean
}

export interface GreetingData {
  content: string
  contentType: ContentType
  streaming: boolean
  visible: boolean
  dismissed: boolean
  dismissing: boolean
  options: GreetingOptions
  blocks: ContentBlock[]
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
  greeting: GreetingData | null
  cancelRequested: boolean
}

// Actions that originate from the UI (not from the server)
export type UIAction =
  | {
      type: "INPUT_SENT"
      content: string
      role: "user"
    }
  | { type: "greeting_dismissed" }
  | { type: "CANCEL_REQUESTED" }

export type AnyAction = ChatAction | UIAction

export const initialState: ChatState = {
  messages: [],
  streamingMessage: null,
  greeting: null,
  inputDisabled: false,
  inputPlaceholder: "Enter a message...",
  cancelRequested: false,
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

  const blocks = splitThinkingBlocks(msg.content, msg.content_type)
  const contentOnly = blocks
    .filter((b): b is ContentBlock => b.type === "content")
    .map((b) => b.content)
    .join("")

  return {
    id: msg.id ?? uuid(),
    role: msg.role,
    content: contentOnly,
    contentType: msg.content_type,
    streaming: false,
    icon: msg.icon,
    blocks,
  }
}

function removeLoadingMessage(messages: ChatMessageData[]): ChatMessageData[] {
  return messages.filter((m) => !m.isPlaceholder)
}

const THINKING_TAG_RE = /<thinking>\n?([\s\S]*?)\n?<\/thinking>\n*/g

function splitThinkingBlocks(
  content: string,
  contentType: ContentType,
): MessageBlock[] {
  if (contentType === "thinking") {
    return [{ type: "thinking", content, streaming: false }]
  }

  // Skip splitting for non-markdown content types where <thinking> tags
  // are likely literal content rather than thinking markers
  if (contentType !== "markdown") {
    return [{ type: "content", content, contentType }]
  }

  // Find code fence regions to exclude from thinking tag detection
  const fenceRanges: Array<[number, number]> = []
  const fenceRe = /^(`{3,}|~{3,}).*\n([\s\S]*?)^\1\s*$/gm
  for (const m of content.matchAll(fenceRe)) {
    fenceRanges.push([m.index, m.index + m[0].length])
  }

  function isInsideFence(idx: number): boolean {
    return fenceRanges.some(([start, end]) => idx >= start && idx < end)
  }

  const blocks: MessageBlock[] = []
  let lastIndex = 0

  for (const match of content.matchAll(THINKING_TAG_RE)) {
    if (isInsideFence(match.index)) continue

    const before = content.slice(lastIndex, match.index)
    if (before) {
      blocks.push({ type: "content", content: before, contentType })
    }
    const thinkingContent = match[1] ?? ""
    const { cleaned, topic } = extractTopicsComplete(thinkingContent)
    blocks.push({
      type: "thinking",
      content: cleaned,
      streaming: false,
      ...(topic !== null ? { topic } : {}),
    })
    lastIndex = match.index + match[0].length
  }

  const remaining = content.slice(lastIndex)
  if (remaining) {
    blocks.push({ type: "content", content: remaining, contentType })
  }

  return blocks
}

function extractTopicsComplete(text: string): {
  cleaned: string
  topic: string | null
} {
  let topic: string | null = null
  const cleaned = text.replace(TOPIC_TAG_RE, (_match, captured: string) => {
    topic = captured
    return `\n\n<div class="shinychat-thinking-topic">${captured}</div>\n\n`
  })
  return { cleaned, topic }
}

interface ThinkingTagSegment {
  type: "thinking" | "content"
  text: string
}

interface ThinkingTagState {
  insideThinkingTag: boolean
  tagBuffer: string
}

const THINKING_OPEN = "<thinking>\n"
const THINKING_OPEN_NO_NL = "<thinking>"
const THINKING_CLOSE = "\n</thinking>"
const THINKING_CLOSE_NO_NL = "</thinking>"

function processThinkingTags(
  chunk: string,
  state: ThinkingTagState,
): { segments: ThinkingTagSegment[]; state: ThinkingTagState } {
  let text = state.tagBuffer + chunk
  let inside = state.insideThinkingTag
  const segments: ThinkingTagSegment[] = []
  let tagBuffer = ""

  while (text.length > 0) {
    if (!inside) {
      // Look for <thinking> open tag
      const openIdx = text.indexOf(THINKING_OPEN)
      const openIdxNoNl =
        openIdx === -1 ? text.indexOf(THINKING_OPEN_NO_NL) : -1
      const idx = openIdx !== -1 ? openIdx : openIdxNoNl
      const tag = openIdx !== -1 ? THINKING_OPEN : THINKING_OPEN_NO_NL

      if (idx !== -1) {
        // Only treat as thinking if it's at the start of content (top-level)
        const before = text.slice(0, idx)
        if (before.trim()) {
          // There's non-whitespace before the tag — not top-level
          segments.push({ type: "content", text })
          text = ""
        } else {
          if (before) {
            segments.push({ type: "content", text: before })
          }
          inside = true
          text = text.slice(idx + tag.length)
        }
      } else {
        // Check for partial <thinking at end
        const partial = findPartialTag(text, THINKING_OPEN_NO_NL)
        if (partial > 0 && text.slice(0, text.length - partial).trim() === "") {
          // Could be start of a top-level <thinking> tag
          tagBuffer = text.slice(text.length - partial)
          const before = text.slice(0, text.length - partial)
          if (before) {
            segments.push({ type: "content", text: before })
          }
          text = ""
        } else {
          segments.push({ type: "content", text })
          text = ""
        }
      }
    } else {
      // Inside thinking — look for </thinking> close tag
      const closeIdx = text.indexOf(THINKING_CLOSE)
      const closeIdxNoNl =
        closeIdx === -1 ? text.indexOf(THINKING_CLOSE_NO_NL) : -1
      const idx = closeIdx !== -1 ? closeIdx : closeIdxNoNl
      const tag = closeIdx !== -1 ? THINKING_CLOSE : THINKING_CLOSE_NO_NL

      if (idx !== -1) {
        const thinkingText = text.slice(0, idx)
        if (thinkingText) {
          segments.push({ type: "thinking", text: thinkingText })
        }
        inside = false
        text = text.slice(idx + tag.length)
        // Skip optional trailing newlines after </thinking>
        if (text.startsWith("\n")) text = text.slice(1)
        if (text.startsWith("\n")) text = text.slice(1)
      } else {
        // Check for partial </thinking at end
        const partial = findPartialTag(text, THINKING_CLOSE_NO_NL)
        if (partial > 0) {
          tagBuffer = text.slice(text.length - partial)
          const thinkingText = text.slice(0, text.length - partial)
          if (thinkingText) {
            segments.push({ type: "thinking", text: thinkingText })
          }
          text = ""
        } else {
          segments.push({ type: "thinking", text })
          text = ""
        }
      }
    }
  }

  return {
    segments,
    state: { insideThinkingTag: inside, tagBuffer },
  }
}

function findPartialTag(text: string, tag: string): number {
  // Check if the end of text matches a prefix of the tag
  for (let len = Math.min(tag.length - 1, text.length); len > 0; len--) {
    if (text.endsWith(tag.slice(0, len))) {
      return len
    }
  }
  return 0
}

const TOPIC_TAG_RE = /<topic>(.*?)<\/topic>/g
const PARTIAL_OPEN_RE = /<(?:t(?:o(?:p(?:i(?:c(?:>[^<]*)?)?)?)?)?)?\s*$/
const PARTIAL_CLOSE_RE = /<(?:\/(?:t(?:o(?:p(?:i(?:c(?:>)?)?)?)?)?)?)?\s*$/

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

  // Check for partial opening or closing tag at the end
  let newBuffer = ""
  const partialOpen = PARTIAL_OPEN_RE.exec(combined)
  const partialClose = PARTIAL_CLOSE_RE.exec(combined)
  const partialMatch =
    partialOpen && partialClose
      ? partialOpen.index > partialClose.index
        ? partialOpen
        : partialClose
      : partialOpen || partialClose
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
      const greetingDismissedByInput =
        state.greeting?.options.dismissible !== false && state.greeting?.visible
          ? {
              ...state.greeting,
              visible: false,
              dismissed: true,
              dismissing: true,
            }
          : state.greeting
      return {
        ...state,
        messages: [...state.messages, userMsg, loadingMsg],
        inputDisabled: true,
        greeting: greetingDismissedByInput ?? null,
      }
    }

    case "message": {
      const messages = removeLoadingMessage(state.messages)
      const greetingDismissedByMessage =
        state.greeting?.options.dismissible !== false && state.greeting?.visible
          ? {
              ...state.greeting,
              visible: false,
              dismissed: true,
              dismissing: true,
            }
          : state.greeting
      return {
        ...state,
        messages: [...messages, messagePayloadToData(action.message)],
        streamingMessage: null,
        inputDisabled: false,
        greeting: greetingDismissedByMessage ?? null,
      }
    }

    case "chunk_start": {
      const messages = removeLoadingMessage(state.messages)
      const newMsg = messagePayloadToData(action.message)
      newMsg.streaming = true
      newMsg.blocks = newMsg.blocks.map((b) =>
        b.type === "thinking" ? { ...b, streaming: true } : b,
      )
      const greetingDismissedByChunkStart =
        state.greeting?.options.dismissible !== false && state.greeting?.visible
          ? {
              ...state.greeting,
              visible: false,
              dismissed: true,
              dismissing: true,
            }
          : state.greeting
      return {
        ...state,
        messages,
        streamingMessage: newMsg,
        inputDisabled: true,
        greeting: greetingDismissedByChunkStart ?? null,
      }
    }

    case "chunk": {
      const last = state.streamingMessage
      if (!last || !last.streaming) return state

      const explicitType = action.content_type
      const lastBlock = last.blocks[last.blocks.length - 1]
      const defaultContentType =
        (lastBlock?.type === "content"
          ? (lastBlock as ContentBlock).contentType
          : undefined) ?? "markdown"

      // If server explicitly says "thinking", use the direct thinking path
      if (explicitType === "thinking") {
        const blocks = [...last.blocks]
        const tail =
          lastBlock?.type === "thinking" && lastBlock.streaming
            ? lastBlock
            : null
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

      // No explicit content_type — detect <thinking> tags in content
      const chunkType = explicitType ?? defaultContentType

      // If we're inside a thinking tag or the chunk might contain one,
      // process through the tag state machine
      if (
        last.insideThinkingTag ||
        last.tagBuffer ||
        action.content.includes("<")
      ) {
        const tagState: ThinkingTagState = {
          insideThinkingTag: last.insideThinkingTag ?? false,
          tagBuffer: last.tagBuffer ?? "",
        }
        const { segments, state: newTagState } = processThinkingTags(
          action.content,
          tagState,
        )

        // If we were tracking tag state, found thinking segments, or just entered a thinking tag
        const hadTagState = !!(last.insideThinkingTag || last.tagBuffer)
        const hasThinking = segments.some((s) => s.type === "thinking")
        const enteredThinking = newTagState.insideThinkingTag

        if (hadTagState || hasThinking || enteredThinking) {
          const blocks = [...last.blocks]

          for (const seg of segments) {
            if (seg.type === "thinking") {
              const tail = blocks[blocks.length - 1]
              if (tail?.type === "thinking" && tail.streaming) {
                const { cleaned, topic, buffer } = extractTopics(
                  seg.text,
                  tail.topicBuffer ?? "",
                )
                blocks[blocks.length - 1] = {
                  ...tail,
                  content: tail.content + cleaned,
                  topicBuffer: buffer,
                  ...(topic !== null ? { topic } : {}),
                }
              } else {
                const { cleaned, topic, buffer } = extractTopics(seg.text, "")
                blocks.push({
                  type: "thinking",
                  content: cleaned,
                  topicBuffer: buffer,
                  streaming: true,
                  startedAt: Date.now(),
                  ...(topic !== null ? { topic } : {}),
                })
              }
            } else {
              // Content segment — finalize any trailing streaming thinking block
              const tail = blocks[blocks.length - 1]
              if (tail?.type === "thinking" && tail.streaming) {
                blocks[blocks.length - 1] = {
                  ...tail,
                  content: tail.content + (tail.topicBuffer ?? ""),
                  topicBuffer: "",
                  streaming: false,
                  durationMs: tail.startedAt
                    ? Date.now() - tail.startedAt
                    : undefined,
                }
              }
              // Append to existing content block or create new
              const lastContent = blocks[blocks.length - 1]
              if (
                lastContent?.type === "content" &&
                lastContent.contentType === chunkType
              ) {
                blocks[blocks.length - 1] = {
                  ...lastContent,
                  content: lastContent.content + seg.text,
                }
              } else if (seg.text) {
                blocks.push({
                  type: "content",
                  content: seg.text,
                  contentType: chunkType,
                })
              }
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
              insideThinkingTag: newTagState.insideThinkingTag,
              tagBuffer: newTagState.tagBuffer,
            },
          }
        }

        // Tag detection ran but found nothing — update tag buffer state if needed
        if (newTagState.tagBuffer) {
          return {
            ...state,
            streamingMessage: {
              ...last,
              insideThinkingTag: newTagState.insideThinkingTag,
              tagBuffer: newTagState.tagBuffer,
            },
          }
        }
      }

      // Standard non-thinking content path
      const blocks = [...last.blocks]

      // Finalize any trailing thinking block
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
          insideThinkingTag: false,
          tagBuffer: "",
        },
      }
    }

    case "chunk_end": {
      const last = state.streamingMessage
      if (!last || !last.streaming) {
        if (state.cancelRequested) {
          const messages = removeLoadingMessage(state.messages)
          const cancelledMsg: ChatMessageData = {
            id: uuid(),
            role: "assistant",
            content: "",
            contentType: "markdown",
            streaming: false,
            cancelled: true,
            blocks: [],
          }
          return {
            ...state,
            messages: [...messages, cancelledMsg],
            streamingMessage: null,
            inputDisabled: false,
            cancelRequested: false,
          }
        }
        return state
      }

      const finalized = finalizeMessage(last)
      const withCancel = state.cancelRequested
        ? { ...finalized, cancelled: true }
        : finalized

      return {
        ...state,
        messages: [...state.messages, withCancel],
        streamingMessage: null,
        inputDisabled: false,
        cancelRequested: false,
      }
    }

    case "CANCEL_REQUESTED": {
      return { ...state, cancelRequested: true }
    }

    case "clear": {
      const greetingAfterClear = action.greeting
        ? null
        : state.greeting
          ? {
              ...state.greeting,
              visible: true,
              dismissed: false,
              dismissing: false,
            }
          : null
      return {
        ...initialState,
        inputPlaceholder: state.inputPlaceholder,
        greeting: greetingAfterClear,
      }
    }

    case "update_input":
      return {
        ...state,
        inputPlaceholder: action.placeholder ?? state.inputPlaceholder,
      }

    case "remove_loading": {
      const messages = removeLoadingMessage(state.messages)
      if (state.streamingMessage) {
        const finalized = finalizeMessage(state.streamingMessage)
        const withCancel = state.cancelRequested
          ? { ...finalized, cancelled: true }
          : finalized
        messages.push(withCancel)
      }
      return {
        ...state,
        messages,
        streamingMessage: null,
        inputDisabled: false,
        cancelRequested: false,
      }
    }

    case "hide_tool_request": {
      if (state.hiddenToolRequests.has(action.requestId)) return state
      const newSet = new Set(state.hiddenToolRequests)
      newSet.add(action.requestId)
      return { ...state, hiddenToolRequests: newSet }
    }

    case "greeting": {
      const prior = state.greeting
      const dismissible = action.options.dismissible !== false
      // If a greeting was already dismissed, accept the new content silently so
      // it surfaces the next time the message list is cleared. Otherwise apply
      // the standard auto-dismiss rule when initial messages exist.
      const autoDismiss = prior?.dismissed
        ? true
        : dismissible && state.messages.length > 0
      const visible = prior?.dismissed ? false : !autoDismiss
      return {
        ...state,
        greeting: {
          content: action.content,
          contentType: action.content_type,
          streaming: false,
          visible,
          dismissed: autoDismiss,
          dismissing: false,
          options: action.options,
          blocks: [
            {
              type: "content",
              content: action.content,
              contentType: action.content_type,
            },
          ],
        },
      }
    }

    case "greeting_start": {
      const prior = state.greeting
      const dismissible = action.options.dismissible !== false
      const autoDismiss = prior?.dismissed
        ? true
        : dismissible && state.messages.length > 0
      const visible = prior?.dismissed ? false : !autoDismiss
      return {
        ...state,
        greeting: {
          content: action.content,
          contentType: action.content_type,
          streaming: true,
          visible,
          dismissed: autoDismiss,
          dismissing: false,
          options: action.options,
          blocks: action.content
            ? [
                {
                  type: "content",
                  content: action.content,
                  contentType: action.content_type,
                },
              ]
            : [],
        },
      }
    }

    case "greeting_dismissed": {
      const greeting = state.greeting
      if (!greeting || !greeting.dismissing) return state
      return { ...state, greeting: { ...greeting, dismissing: false } }
    }

    case "greeting_chunk": {
      const greeting = state.greeting
      if (!greeting || !greeting.streaming) return state

      const chunkType = action.content_type ?? greeting.contentType
      let blocks: ContentBlock[]

      if (action.operation === "replace") {
        blocks = [
          { type: "content", content: action.content, contentType: chunkType },
        ]
      } else {
        const existing = [...greeting.blocks]
        const last = existing[existing.length - 1]
        if (last && last.contentType === chunkType) {
          existing[existing.length - 1] = {
            ...last,
            content: last.content + action.content,
          }
          blocks = existing
        } else {
          blocks = [
            ...existing,
            {
              type: "content",
              content: action.content,
              contentType: chunkType,
            },
          ]
        }
      }

      const content = blocks.map((b) => b.content).join("")
      return {
        ...state,
        greeting: { ...greeting, content, contentType: chunkType, blocks },
      }
    }

    case "greeting_end": {
      const greeting = state.greeting
      if (!greeting?.streaming) return state
      return { ...state, greeting: { ...greeting, streaming: false } }
    }

    case "greeting_clear":
      return { ...state, greeting: null }

    default: {
      const _exhaustive: never = action
      void _exhaustive
      return state
    }
  }
}

function finalizeMessage(msg: ChatMessageData): ChatMessageData {
  const blocks: MessageBlock[] = []
  for (const block of msg.blocks) {
    if (block.type === "thinking" && block.streaming) {
      blocks.push({
        ...block,
        content: block.content + (block.topicBuffer ?? ""),
        topicBuffer: "",
        streaming: false,
        durationMs: block.startedAt ? Date.now() - block.startedAt : undefined,
      })
    } else if (
      block.type === "content" &&
      THINKING_TAG_RE.test(block.content)
    ) {
      THINKING_TAG_RE.lastIndex = 0
      blocks.push(...splitThinkingBlocks(block.content, block.contentType))
    } else {
      blocks.push(block)
    }
  }

  const content = blocks
    .filter((b): b is ContentBlock => b.type === "content")
    .map((b) => b.content)
    .join("")

  return { ...msg, content, streaming: false, blocks }
}
