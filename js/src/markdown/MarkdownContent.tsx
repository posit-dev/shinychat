import { useMemo, useEffect, useRef, type ReactElement, type ComponentType } from "react"
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
  const processor = isUser ? userProcessor : assistantProcessor
  const components = isUser ? userComponents : assistantComponents

  // For "text" content type, just render as plain text
  if (contentType === "text") {
    return <div ref={containerRef}>{content}</div>
  }

  // For "html" content type, we still run through the pipeline
  // (sanitization is important for HTML content)

  // Convert markdown → React elements
  const elements = useMemo(
    () =>
      markdownToReact(content, {
        processor: processor as unknown as Processor,
        components,
        streaming,
      }),
    [content, contentType, streaming],
  )

  // Shiny bind/unbind after render
  useEffect(() => {
    if (!containerRef.current) return

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
  }, [content, streaming])

  // Notify parent of content changes
  useEffect(() => {
    onContentChange?.()
  }, [content])

  // Detect streaming → not-streaming transition
  useEffect(() => {
    if (prevStreamingRef.current && !streaming) {
      onStreamEnd?.()
    }
    prevStreamingRef.current = streaming
  }, [streaming])

  return <div ref={containerRef}>{elements}</div>
}
