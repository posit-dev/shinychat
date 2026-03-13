import { useMemo, type ReactElement, type ComponentType } from "react"
import type { ContentType } from "../transport/types"
import { parseMarkdown, hastToReact } from "./markdownToReact"
import { assistantProcessor, userProcessor } from "./processors"
import { CopyableCodeBlock } from "./components/CopyableCodeBlock"
import { BootstrapTable } from "./components/BootstrapTable"
import { ToolRequestBridge } from "../chat/ToolRequestBridge"
import { ToolResultBridge } from "../chat/ToolResultBridge"

const assistantComponents: Record<string, ComponentType<unknown>> = {
  pre: CopyableCodeBlock as ComponentType<unknown>,
  table: BootstrapTable as ComponentType<unknown>,
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
}

const userComponents: Record<string, ComponentType<unknown>> = {
  table: BootstrapTable as ComponentType<unknown>,
}

export interface MarkdownContentProps {
  content: string
  contentType: ContentType
  streaming?: boolean
}

/**
 * Pure rendering component: converts markdown/text content to React elements.
 * Has no Shiny side effects. Wrap with ShinyBoundMarkdown to add binding.
 */
export function MarkdownContent({
  content,
  contentType,
  streaming = false,
}: MarkdownContentProps): ReactElement {
  const isUser = contentType === "semi-markdown"
  const isText = contentType === "text"
  const processor = isUser ? userProcessor : assistantProcessor
  const components = isUser ? userComponents : assistantComponents

  // Stage 1 (expensive): parse markdown string → HAST. Cached by content+processor.
  const hast = useMemo(
    () => (isText ? null : parseMarkdown(content, processor)),
    [content, isText, processor],
  )

  // Stage 2 (cheap): convert HAST → React elements. Re-runs when streaming toggles.
  const elements = useMemo(
    () => (hast ? hastToReact(hast, { components, streaming }) : null),
    [hast, streaming, components],
  )

  if (isText) return <>{content}</>
  return <>{elements}</>
}
