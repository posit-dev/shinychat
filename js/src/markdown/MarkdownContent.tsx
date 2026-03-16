import { useMemo, type ReactElement, type ComponentType } from "react"
import type { ContentType } from "../transport/types"
import { parseMarkdown, hastToReact } from "./markdownToReact"
import { assistantProcessor, userProcessor } from "./processors"
import { CopyableCodeBlock } from "./components/CopyableCodeBlock"
import { BootstrapTable } from "./components/BootstrapTable"
import { HtmlIsland } from "./components/HtmlIsland"

const baseAssistantComponents: Record<string, ComponentType<unknown>> = {
  pre: CopyableCodeBlock as ComponentType<unknown>,
  table: BootstrapTable as ComponentType<unknown>,
  "shinychat-html": HtmlIsland as ComponentType<unknown>,
}

const baseUserComponents: Record<string, ComponentType<unknown>> = {
  table: BootstrapTable as ComponentType<unknown>,
}

export interface MarkdownContentProps {
  content: string
  contentType: ContentType
  streaming?: boolean
  tagToComponentMap?: Record<string, ComponentType<unknown>>
}

/** Pure rendering — no Shiny side effects. Wrap with ShinyBoundMarkdown to add binding. */
export function MarkdownContent({
  content,
  contentType,
  streaming = false,
  tagToComponentMap,
}: MarkdownContentProps): ReactElement {
  const isUser = contentType === "semi-markdown"
  const isText = contentType === "text"
  const processor = isUser ? userProcessor : assistantProcessor
  const resolvedTagToComponentMap = useMemo(
    () =>
      isUser
        ? { ...baseUserComponents, ...tagToComponentMap }
        : { ...baseAssistantComponents, ...tagToComponentMap },
    [isUser, tagToComponentMap],
  )

  // Stage 1 (expensive): parse markdown string → HAST. Cached by content+processor.
  const hast = useMemo(
    () => (isText ? null : parseMarkdown(content, processor)),
    [content, isText, processor],
  )

  // Stage 2 (cheap): convert HAST → React elements. Re-runs when streaming toggles.
  const elements = useMemo(
    () =>
      hast
        ? hastToReact(hast, {
            tagToComponentMap: resolvedTagToComponentMap,
            streaming,
          })
        : null,
    [hast, streaming, resolvedTagToComponentMap],
  )

  if (isText) return <>{content}</>
  return <>{elements}</>
}
