import type {
  ContentType,
  ChatAction,
  ConversationMeta,
  MessagePayload,
  GreetingOptions,
  SlashCommandDef,
  HtmlDep,
} from "../transport/types"
import type { AttachmentPayload } from "./attachments"
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
  streaming: boolean
  /** True for the empty placeholder message shown while waiting for the assistant to respond. */
  isPlaceholder?: boolean
  icon?: string
  /** Attachments sent with this message. */
  attachments?: AttachmentPayload[]
  /** Opaque serialized Shiny HTML dependencies received with this message; retained so the client can report them back for persistence/restore. */
  htmlDeps?: HtmlDep[]
  blocks: MessageBlock[]
  /** Tracks whether streaming content is inside an unclosed <thinking> tag */
  insideThinkingTag?: boolean
  /** Buffers partial tag text at chunk boundaries (e.g. "<thi" or "</thin") */
  tagBuffer?: string
  /** Tracks whether streaming content is inside a fenced code block */
  insideFence?: boolean
  /** The opening fence marker (e.g. "```" or "~~~") when insideFence is true */
  fenceMarker?: string
  /** True when the stream was cancelled by the user before it completed. */
  cancelled?: boolean
}

export interface GreetingData {
  content: string
  contentType: ContentType
  streaming: boolean
  status: "visible" | "dismissing" | "dismissed"
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

export interface ChatHistoryState {
  enabled: boolean
  conversations: ConversationMeta[]
  activeId: string | null
}

export interface ChatState extends ChatInputState, ChatToolState {
  messages: ChatMessageData[]
  streamingMessage: ChatMessageData | null
  greeting: GreetingData | null
  cancelRequested: boolean
  /** Whether the stop/cancel button is available during streaming. */
  enableCancel: boolean
  /**
   * Whether `enableCancel` was set explicitly via the `enable-cancel`
   * attribute. When true, server `update_cancel` messages are ignored so an
   * explicit user choice always wins over the `client=` auto-default.
   */
  enableCancelExplicit: boolean
  slashCommands: SlashCommandDef[]
  /** Whether the attachment affordance is enabled. */
  enableUpload: boolean
  /**
   * Whether `enableUpload` was set explicitly via the `allow-attachments`
   * attribute. When true, server `update_upload` messages are ignored so an
   * explicit user choice always wins over the `client=` auto-default.
   */
  enableUploadExplicit: boolean
  history: ChatHistoryState
}

// Actions that originate from the UI (not from the server)
export type UIAction =
  | {
      type: "INPUT_SENT"
      content: string
      role: "user"
      /** When false, append the user message only — no loading placeholder, no input disable. Defaults to true. */
      awaitResponse?: boolean
      attachments?: AttachmentPayload[]
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
  enableCancel: false,
  enableCancelExplicit: false,
  enableUpload: false,
  enableUploadExplicit: false,
  hiddenToolRequests: new Set(),
  slashCommands: [],
  history: { enabled: false, conversations: [], activeId: null },
}

function messagePayloadToData(msg: MessagePayload): ChatMessageData {
  const blocks: MessageBlock[] = []
  for (const seg of msg.segments) {
    blocks.push(...splitThinkingBlocks(seg.content, seg.content_type))
  }
  const attachments: AttachmentPayload[] = msg.attachments ?? []
  const contentOnly = blocks
    .filter((b): b is ContentBlock => b.type === "content")
    .map((b) => b.content)
    .join("")

  return {
    id: msg.id ?? uuid(),
    role: msg.role,
    content: contentOnly,
    streaming: false,
    icon: msg.icon,
    ...(attachments.length > 0 ? { attachments } : {}),
    blocks,
  }
}

function removeLoadingMessage(messages: ChatMessageData[]): ChatMessageData[] {
  return messages.filter((m) => !m.isPlaceholder)
}

function mergeHtmlDeps(
  existing: HtmlDep[] | undefined,
  incoming: HtmlDep[] | undefined,
): HtmlDep[] | undefined {
  return incoming ? [...(existing ?? []), ...incoming] : existing
}

function dismissGreeting(greeting: GreetingData | null): GreetingData | null {
  if (greeting?.options.persistent !== true && greeting?.status === "visible") {
    return { ...greeting, status: "dismissing" }
  }
  return greeting
}

function computeGreetingVisibility(
  prior: GreetingData | null,
  persistent: boolean,
  hasMessages: boolean,
): "visible" | "dismissing" | "dismissed" {
  if (prior?.status === "dismissed") return "dismissed"
  if (!persistent && hasMessages) return "dismissed"
  return "visible"
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

  // Find code fence regions and inline code spans to exclude from thinking tag detection
  const fenceRanges: Array<[number, number]> = []
  const fenceRe = /^(`{3,}|~{3,}).*\n([\s\S]*?)^\1\s*$/gm
  for (const m of content.matchAll(fenceRe)) {
    fenceRanges.push([m.index, m.index + m[0].length])
  }
  const inlineCodeRe = /`[^`\n]+`/g
  for (const m of content.matchAll(inlineCodeRe)) {
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
  insideFence: boolean
  fenceMarker: string
}

const THINKING_OPEN = "<thinking>\n"
const THINKING_OPEN_NO_NL = "<thinking>"
const THINKING_CLOSE = "\n</thinking>"
const THINKING_CLOSE_NO_NL = "</thinking>"

// Matches a fenced code block opening at the start of a line (``` or ~~~, with optional info string)
const FENCE_OPEN_RE = /^(`{3,}|~{3,})[^\n]*(\n|$)/m

function buildFenceCloseRe(marker: string): RegExp {
  const ch = marker[0]
  return new RegExp(`^${ch}{${marker.length},}[ \\t]*(?:\\n|$)`, "m")
}

// Returns true if the last content block ends with a newline, or if blocks is empty / ends with
// a thinking block (both are structural boundaries equivalent to a newline).
function lastContentEndsWithNewline(blocks: MessageBlock[]): boolean {
  if (blocks.length === 0) return true
  const last = blocks[blocks.length - 1]!
  if (last.type === "thinking") return true
  return last.content === "" || last.content.endsWith("\n")
}

function processThinkingTags(
  chunk: string,
  state: ThinkingTagState,
  prevContentEndsWithNewline: boolean,
): { segments: ThinkingTagSegment[]; state: ThinkingTagState } {
  let text = state.tagBuffer + chunk

  type Mode = "outside" | "thinking" | "fence"
  let mode: Mode = state.insideThinkingTag
    ? "thinking"
    : state.insideFence
      ? "fence"
      : "outside"
  let fenceMarker = state.fenceMarker

  // If a tagBuffer was set, the content before it was all whitespace (a newline boundary).
  let localPrevEndsWithNewline = state.tagBuffer
    ? true
    : prevContentEndsWithNewline

  const segments: ThinkingTagSegment[] = []
  let tagBuffer = ""

  while (text.length > 0) {
    if (mode === "outside") {
      const fenceMatch = FENCE_OPEN_RE.exec(text)
      // A fence match at index 0 is only a real line-start if the previous content ended with \n
      const fenceIsLineStart =
        fenceMatch !== null &&
        (fenceMatch.index > 0 || localPrevEndsWithNewline)

      const openIdx = text.indexOf(THINKING_OPEN)
      const openIdxNoNl =
        openIdx === -1 ? text.indexOf(THINKING_OPEN_NO_NL) : -1
      const thinkingIdx = openIdx !== -1 ? openIdx : openIdxNoNl
      const thinkingTag = openIdx !== -1 ? THINKING_OPEN : THINKING_OPEN_NO_NL

      const fenceBeforeThinking =
        fenceIsLineStart &&
        (thinkingIdx === -1 || fenceMatch!.index < thinkingIdx)

      if (fenceBeforeThinking) {
        // Emit content up to and including the fence opener line, enter fence mode
        const fenceOpenText = text.slice(
          0,
          fenceMatch!.index + fenceMatch![0].length,
        )
        if (fenceOpenText)
          segments.push({ type: "content", text: fenceOpenText })
        localPrevEndsWithNewline = fenceOpenText.endsWith("\n")
        fenceMarker = fenceMatch![1] ?? ""
        mode = "fence"
        text = text.slice(fenceMatch!.index + fenceMatch![0].length)
      } else if (thinkingIdx !== -1) {
        const before = text.slice(0, thinkingIdx)
        // <thinking> is only a real thinking tag when it starts at a line boundary:
        // no non-whitespace before it in the current text, and preceded by a newline
        // (either within `before` or carried over from the previous chunk).
        const isTopLevel =
          before.trim() === "" &&
          (before.includes("\n") || localPrevEndsWithNewline)

        if (!isTopLevel) {
          segments.push({ type: "content", text })
          localPrevEndsWithNewline = text.endsWith("\n")
          text = ""
        } else {
          if (before) {
            segments.push({ type: "content", text: before })
          }
          mode = "thinking"
          text = text.slice(thinkingIdx + thinkingTag.length)
        }
      } else {
        // No fence or thinking found — check for partial <thinking at end
        const partial = findPartialTag(text, THINKING_OPEN_NO_NL)
        const beforePartial = text.slice(0, text.length - partial)
        if (
          partial > 0 &&
          beforePartial.trim() === "" &&
          (beforePartial.includes("\n") || localPrevEndsWithNewline)
        ) {
          tagBuffer = text.slice(text.length - partial)
          if (beforePartial)
            segments.push({ type: "content", text: beforePartial })
          text = ""
        } else {
          segments.push({ type: "content", text })
          localPrevEndsWithNewline = text.endsWith("\n")
          text = ""
        }
      }
    } else if (mode === "fence") {
      // Inside a fenced code block — emit everything as content until the matching closer
      const closerRe = buildFenceCloseRe(fenceMarker)
      const closerMatch = closerRe.exec(text)

      if (closerMatch !== null) {
        const fenceContent = text.slice(
          0,
          closerMatch.index + closerMatch[0].length,
        )
        if (fenceContent) segments.push({ type: "content", text: fenceContent })
        localPrevEndsWithNewline = fenceContent.endsWith("\n")
        mode = "outside"
        fenceMarker = ""
        text = text.slice(closerMatch.index + closerMatch[0].length)
      } else {
        segments.push({ type: "content", text })
        localPrevEndsWithNewline = text.endsWith("\n")
        text = ""
      }
    } else {
      // mode === "thinking" — look for </thinking> close tag
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
        mode = "outside"
        localPrevEndsWithNewline = true
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
    state: {
      insideThinkingTag: mode === "thinking",
      tagBuffer,
      insideFence: mode === "fence",
      fenceMarker,
    },
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
        streaming: false,
        ...(action.attachments && action.attachments.length > 0
          ? { attachments: action.attachments }
          : {}),
        blocks: [
          { type: "content", content: action.content, contentType: "markdown" },
        ],
      }

      if (action.awaitResponse === false) {
        return {
          ...state,
          messages: [...state.messages, userMsg],
          greeting: dismissGreeting(state.greeting),
        }
      }

      const loadingMsg: ChatMessageData = {
        id: uuid(),
        role: "assistant",
        content: "",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
      }
      return {
        ...state,
        messages: [...state.messages, userMsg, loadingMsg],
        inputDisabled: true,
        greeting: dismissGreeting(state.greeting),
      }
    }

    case "message": {
      const messages = removeLoadingMessage(state.messages)
      const data = messagePayloadToData(action.message)
      if (action.html_deps) data.htmlDeps = action.html_deps
      return {
        ...state,
        messages: [...messages, data],
        streamingMessage: null,
        inputDisabled: false,
        greeting: dismissGreeting(state.greeting),
      }
    }

    case "chunk_start": {
      const messages = removeLoadingMessage(state.messages)
      const newMsg = messagePayloadToData(action.message)
      newMsg.streaming = true
      newMsg.blocks = newMsg.blocks.map((b) =>
        b.type === "thinking" ? { ...b, streaming: true } : b,
      )
      if (action.html_deps) newMsg.htmlDeps = action.html_deps
      return {
        ...state,
        messages,
        streamingMessage: newMsg,
        inputDisabled: true,
        greeting: dismissGreeting(state.greeting),
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
          streamingMessage: {
            ...last,
            blocks,
            htmlDeps: mergeHtmlDeps(last.htmlDeps, action.html_deps),
          },
        }
      }

      // No explicit content_type — detect <thinking> tags in content
      const chunkType = explicitType ?? defaultContentType

      // If we're inside a thinking/fence tag or the chunk might contain one,
      // process through the tag state machine
      if (
        last.insideThinkingTag ||
        last.tagBuffer ||
        last.insideFence ||
        action.content.includes("<") ||
        action.content.includes("```") ||
        action.content.includes("~~~")
      ) {
        const tagState: ThinkingTagState = {
          insideThinkingTag: last.insideThinkingTag ?? false,
          tagBuffer: last.tagBuffer ?? "",
          insideFence: last.insideFence ?? false,
          fenceMarker: last.fenceMarker ?? "",
        }
        const { segments, state: newTagState } = processThinkingTags(
          action.content,
          tagState,
          lastContentEndsWithNewline(last.blocks),
        )

        // If we were tracking tag state, found thinking segments, just entered a thinking tag,
        // or fence state changed (entering or exiting a fenced code block)
        const hadTagState = !!(
          last.insideThinkingTag ||
          last.tagBuffer ||
          last.insideFence
        )
        const hasThinking = segments.some((s) => s.type === "thinking")
        const enteredThinking = newTagState.insideThinkingTag
        const fenceStateChanged =
          newTagState.insideFence !== (last.insideFence ?? false)

        if (
          hadTagState ||
          hasThinking ||
          enteredThinking ||
          fenceStateChanged
        ) {
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
              blocks,
              insideThinkingTag: newTagState.insideThinkingTag,
              tagBuffer: newTagState.tagBuffer,
              insideFence: newTagState.insideFence,
              fenceMarker: newTagState.fenceMarker,
              htmlDeps: mergeHtmlDeps(last.htmlDeps, action.html_deps),
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
              insideFence: newTagState.insideFence,
              fenceMarker: newTagState.fenceMarker,
              htmlDeps: mergeHtmlDeps(last.htmlDeps, action.html_deps),
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
            blocks: newBlocks,
            htmlDeps: mergeHtmlDeps(last.htmlDeps, action.html_deps),
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
          blocks,
          insideThinkingTag: false,
          tagBuffer: "",
          htmlDeps: mergeHtmlDeps(last.htmlDeps, action.html_deps),
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

    case "update_cancel": {
      if (state.enableCancelExplicit) return state
      return { ...state, enableCancel: action.enable_cancel }
    }

    case "update_upload": {
      if (state.enableUploadExplicit) return state
      return { ...state, enableUpload: action.enable_upload }
    }

    case "clear": {
      // action.greeting=true means "also clear the greeting"; otherwise restore it as visible
      const greetingAfterClear = action.greeting
        ? null
        : state.greeting
          ? {
              ...state.greeting,
              status: "visible" as const,
            }
          : null
      return {
        ...initialState,
        inputPlaceholder: state.inputPlaceholder,
        greeting: greetingAfterClear,
        enableCancel: state.enableCancel,
        enableCancelExplicit: state.enableCancelExplicit,
        slashCommands: state.slashCommands,
        enableUpload: state.enableUpload,
        enableUploadExplicit: state.enableUploadExplicit,
        history: state.history,
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
      const persistent = action.options.persistent === true
      // If a greeting was already dismissed, accept the new content silently so
      // it surfaces the next time the message list is cleared. Otherwise apply
      // the standard auto-dismiss rule when initial messages exist.
      const status = computeGreetingVisibility(
        state.greeting,
        persistent,
        state.messages.length > 0,
      )
      return {
        ...state,
        greeting: {
          content: action.content,
          contentType: action.content_type,
          streaming: false,
          status,
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
      const persistent = action.options.persistent === true
      const status = computeGreetingVisibility(
        state.greeting,
        persistent,
        state.messages.length > 0,
      )
      return {
        ...state,
        greeting: {
          content: action.content,
          contentType: action.content_type,
          streaming: true,
          status,
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
      if (!greeting || greeting.status !== "dismissing") return state
      return { ...state, greeting: { ...greeting, status: "dismissed" } }
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
      if (!greeting.content) {
        return { ...state, greeting: null }
      }
      return { ...state, greeting: { ...greeting, streaming: false } }
    }

    case "greeting_clear":
      return { ...state, greeting: null }

    case "update_slash_commands":
      return { ...state, slashCommands: action.commands }

    case "history_update": {
      return {
        ...state,
        history: {
          enabled: action.enabled,
          conversations: action.conversations,
          activeId: action.active_id,
        },
      }
    }

    case "history_navigate": {
      // Side effect handled imperatively in ChatApp; no state change.
      return state
    }

    default: {
      const _exhaustive: never = action
      void _exhaustive
      return state
    }
  }
}

export type SnapshotSegment = { content: string; content_type: ContentType }
export type SnapshotMessage = {
  role: "user" | "assistant"
  segments: SnapshotSegment[]
  attachments?: AttachmentPayload[]
  htmlDeps?: HtmlDep[]
}

function blockToSegment(block: MessageBlock): SnapshotSegment {
  if (block.type === "thinking") {
    return { content: block.content, content_type: "thinking" }
  }
  return { content: block.content, content_type: block.contentType }
}

export function buildMessagesSnapshot(state: ChatState): SnapshotMessage[] {
  return state.messages
    .filter((m) => !m.isPlaceholder && !m.streaming)
    .map((m) => {
      const msg: SnapshotMessage = {
        role: m.role,
        segments: m.blocks.map(blockToSegment),
      }
      if (m.attachments && m.attachments.length > 0)
        msg.attachments = m.attachments
      if (m.htmlDeps && m.htmlDeps.length > 0) msg.htmlDeps = m.htmlDeps
      return msg
    })
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
