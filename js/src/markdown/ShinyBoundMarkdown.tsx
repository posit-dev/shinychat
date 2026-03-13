import { useEffect, useRef } from "react"
import type { ComponentType } from "react"
import type { ContentType } from "../transport/types"
import { useShinyLifecycle } from "../chat/context"
import { useShinyBinding } from "./useShinyBinding"
import { MarkdownContent } from "./MarkdownContent"

export interface ShinyBoundMarkdownProps {
  content: string
  contentType: ContentType
  streaming?: boolean
  onContentChange?: () => void
  onStreamEnd?: () => void
  tagToComponentMap?: Record<string, ComponentType<unknown>>
}

export function ShinyBoundMarkdown({
  content,
  contentType,
  streaming = false,
  onContentChange,
  onStreamEnd,
  tagToComponentMap,
}: ShinyBoundMarkdownProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const shiny = useShinyLifecycle()
  const prevStreamingRef = useRef(streaming)

  useShinyBinding(containerRef, shiny, { content, streaming, contentType })

  useEffect(() => {
    onContentChange?.()
  }, [content, onContentChange])

  useEffect(() => {
    if (prevStreamingRef.current && !streaming) {
      onStreamEnd?.()
    }
    prevStreamingRef.current = streaming
  }, [streaming, onStreamEnd])

  return (
    <div ref={containerRef}>
      <MarkdownContent
        content={content}
        contentType={contentType}
        streaming={streaming}
        tagToComponentMap={tagToComponentMap}
      />
    </div>
  )
}
