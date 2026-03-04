import {
  useMemo,
  useEffect,
  useRef,
  type ReactElement,
  type ComponentType,
} from "react"
import type { Processor } from "unified"
import type { ContentType } from "../transport/types"
import { markdownToReact } from "./markdownToReact"
import { assistantProcessor, userProcessor } from "./processors"
import { CopyableCodeBlock } from "./components/CopyableCodeBlock"
import { BootstrapTable } from "./components/BootstrapTable"
import { useTransport } from "../chat/context"

const assistantComponents: Record<string, ComponentType<unknown>> = {
  pre: CopyableCodeBlock as ComponentType<unknown>,
  table: BootstrapTable as ComponentType<unknown>,
}

const userComponents: Record<string, ComponentType<unknown>> = {
  table: BootstrapTable as ComponentType<unknown>,
}

export interface MarkdownContentProps {
  content: string
  contentType: ContentType
  streaming?: boolean
  onContentChange?: () => void
  onStreamEnd?: () => void
}

export function MarkdownContent({
  content,
  contentType,
  streaming = false,
  onContentChange,
  onStreamEnd,
}: MarkdownContentProps): ReactElement | null {
  const containerRef = useRef<HTMLDivElement>(null)
  const transport = useTransport()
  const prevStreamingRef = useRef(streaming)

  // Choose processor and components based on content type
  const isUser = contentType === "semi-markdown"
  const isText = contentType === "text"
  const processor = isUser ? userProcessor : assistantProcessor
  const components = isUser ? userComponents : assistantComponents

  // Convert markdown/HTML → React elements (skipped for plain text only)
  const elements = useMemo(
    () =>
      isText
        ? null
        : markdownToReact(content, {
            processor: processor as unknown as Processor,
            components,
            streaming,
          }),
    [content, streaming, isText, processor, components],
  )

  // Shiny bind/unbind after render
  useEffect(() => {
    if (isText || !containerRef.current) return

    const el = containerRef.current

    // Throttle during streaming: only bind every 200ms
    if (streaming) {
      const timeout = setTimeout(() => {
        transport.bindAll(el)
      }, 200)
      return () => clearTimeout(timeout)
    }

    transport.bindAll(el)

    return () => {
      transport.unbindAll(el)
    }
  }, [content, streaming, isText, transport])

  // Notify parent of content changes
  useEffect(() => {
    onContentChange?.()
  }, [content, onContentChange])

  // Detect streaming → not-streaming transition
  useEffect(() => {
    if (prevStreamingRef.current && !streaming) {
      onStreamEnd?.()
    }
    prevStreamingRef.current = streaming
  }, [streaming, onStreamEnd])

  if (isText) {
    return <div ref={containerRef}>{content}</div>
  }

  return <div ref={containerRef}>{elements}</div>
}
