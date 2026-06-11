import React, {
  useMemo,
  type ReactElement,
  type ReactNode,
  type ComponentType,
} from "react"
import { toHtml } from "hast-util-to-html"
import type { Element } from "hast"
import type { ContentType } from "../transport/types"
import { parseMarkdown, parseHtml, hastToReact } from "./markdownToReact"
import {
  markdownProcessor,
  htmlProcessor,
  userMarkdownProcessor,
} from "./processors"
import { CopyableCodeBlock } from "./components/CopyableCodeBlock"
import { BootstrapTable } from "./components/BootstrapTable"
import { RawHTML } from "../chat/RawHTML"

const baseAssistantComponents: Record<string, ComponentType<unknown>> = {
  pre: CopyableCodeBlock as ComponentType<unknown>,
  table: BootstrapTable as ComponentType<unknown>,
  "shinychat-raw-html": (({ node }: { node?: Element }) => (
    <RawHTML html={node ? toHtml(node.children) : ""} displayContents />
  )) as ComponentType<unknown>,
}

const baseUserComponents: Record<string, ComponentType<unknown>> = {
  table: BootstrapTable as ComponentType<unknown>,
}

export interface MarkdownContentProps {
  content: string
  contentType: ContentType
  role?: "user" | "assistant"
  streaming?: boolean
  tagToComponentMap?: Record<string, ComponentType<unknown>>
  prefix?: ReactNode
}

/** Renders content as React elements. Shiny binding is handled per-island by RawHTML. */
export function MarkdownContent({
  content,
  contentType,
  role,
  streaming = false,
  tagToComponentMap,
  prefix,
}: MarkdownContentProps): ReactElement {
  const isUser = role === "user"
  const isText = contentType === "text"
  const isHtml = contentType === "html"
  const processor = isHtml
    ? htmlProcessor
    : isUser
      ? userMarkdownProcessor
      : markdownProcessor
  const resolvedTagToComponentMap = useMemo(
    () =>
      isUser
        ? { ...baseUserComponents, ...tagToComponentMap }
        : { ...baseAssistantComponents, ...tagToComponentMap },
    [isUser, tagToComponentMap],
  )

  // Stage 1 (expensive): parse markdown string → HAST. Cached by content+processor.
  const hast = useMemo(
    () =>
      isText
        ? null
        : isHtml
          ? parseHtml(content, processor)
          : parseMarkdown(content, processor),
    [content, isText, isHtml, processor],
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

  if (isText) {
    return (
      <>
        {prefix}
        {prefix && " "}
        {content}
      </>
    )
  }
  if (prefix && elements) {
    return <>{injectPrefix(elements, prefix)}</>
  }
  return <>{elements}</>
}

// Injects a React node (e.g. a CommandChip) into the first <p> of the rendered
// markdown output so it flows inline with the paragraph text. We do this via
// React tree manipulation because the remark pipeline doesn't support inline
// span syntax like `[text]{.class}`, and adding a plugin + sanitize whitelist
// isn't worth it for a single use case. If we later need chips or other inline
// elements at arbitrary positions in user messages, consider adding
// remark-bracketed-spans (or remark-directive) and reworking this.
function injectPrefix(elements: ReactElement, prefix: ReactNode): ReactNode {
  const children = React.Children.toArray(
    (elements.props as { children?: ReactNode }).children,
  )
  for (let i = 0; i < children.length; i++) {
    const child = children[i]
    if (React.isValidElement(child) && child.type === "p") {
      const pChildren = React.Children.toArray(
        (child.props as { children?: ReactNode }).children,
      )
      children[i] = React.cloneElement(
        child as ReactElement,
        { key: child.key },
        prefix,
        " ",
        ...pChildren,
      )
      return <>{children}</>
    }
  }
  return (
    <>
      {prefix} {elements}
    </>
  )
}
