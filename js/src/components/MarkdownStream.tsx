import { useEffect, useRef, useState, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import ClipboardJS from "clipboard"
import hljs from "highlight.js/lib/common"
import { Renderer, parse } from "marked"
import DOMPurify from "dompurify"
import { sanitizeHTML } from "../utils/_utils"
import "./MarkdownStream.css"

export type ContentType = "markdown" | "semi-markdown" | "html" | "text"

export interface MarkdownStreamProps {
  content: string
  contentType?: ContentType
  streaming?: boolean
  autoScroll?: boolean
  onContentChange?: () => void
  onStreamEnd?: () => void
}

// SVG dot to indicate content is currently streaming
const SVG_DOT_CLASS = "markdown-stream-dot"
const SVG_DOT = `<svg width="12" height="12" xmlns="http://www.w3.org/2000/svg" class="${SVG_DOT_CLASS}" style="margin-left:.25em;margin-top:-.25em"><circle cx="6" cy="6" r="6"/></svg>`

// 'markdown' renderer (for assistant messages)
const markdownRenderer = new Renderer()

// Add some basic Bootstrap styling to markdown tables
markdownRenderer.table = (header: string, body: string) => {
  return `<table class="table table-striped table-bordered">
      <thead>${header}</thead>
      <tbody>${body}</tbody>
    </table>`
}

// 'semi-markdown' renderer (for user messages)
const semiMarkdownRenderer = new Renderer()

// Escape HTML, not for security reasons, but just because it's confusing if the user is
// using tag-like syntax to demarcate parts of their prompt for other reasons (like
// <User>/<Assistant> for providing examples to the model), and those tags vanish.
semiMarkdownRenderer.html = (html: string) =>
  html
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;")

function contentToHTML(content: string, content_type: ContentType): string {
  if (content_type === "markdown") {
    const html = parse(content, { renderer: markdownRenderer })
    return sanitizeHTML(html as string)
  } else if (content_type === "semi-markdown") {
    const html = parse(content, { renderer: semiMarkdownRenderer })
    return sanitizeHTML(html as string)
  } else if (content_type === "html") {
    return sanitizeHTML(content)
  } else if (content_type === "text") {
    // For text content, we need to escape HTML and preserve line breaks
    return content
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;")
      .replaceAll("\n", "<br>")
  } else {
    throw new Error(`Unknown content type: ${content_type}`)
  }
}

// Throttle utility for React
function useThrottle<T extends (...args: unknown[]) => unknown>(
  callback: T,
  delay: number,
): T {
  const timeoutRef = useRef<number>()

  return useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current)
      }

      timeoutRef.current = window.setTimeout(() => {
        callback(...args)
        timeoutRef.current = undefined
      }, delay)
    },
    [callback, delay],
  ) as T
}

// Theme detection and CSS injection for highlight.js
function useHighlightTheme() {
  useEffect(() => {
    const loadHighlightTheme = async () => {
      // Check if we're in dark mode
      const isDarkMode =
        window.matchMedia("(prefers-color-scheme: dark)").matches ||
        document.documentElement.getAttribute("data-bs-theme") === "dark" ||
        document.body.classList.contains("dark-theme")

      // Remove existing highlight.js stylesheets
      document
        .querySelectorAll('link[href*="highlight.js"]')
        .forEach((link) => link.remove())
      document
        .querySelectorAll("style[data-highlight-theme]")
        .forEach((style) => style.remove())

      try {
        // Import the appropriate theme CSS as text
        const themeName = isDarkMode ? "atom-one-dark" : "atom-one-light"

        // For now, we'll inject basic styles. In a full implementation, you might
        // want to dynamically import the CSS files or include them in your build
        const style = document.createElement("style")
        style.setAttribute("data-highlight-theme", themeName)

        if (isDarkMode) {
          style.textContent = `
            .markdown-stream pre code.hljs {
              display: block;
              overflow-x: auto;
              padding: 1em;
              color: #abb2bf;
              background: #282c34;
            }
            .markdown-stream .hljs-comment,
            .markdown-stream .hljs-quote {
              color: #5c6370;
              font-style: italic;
            }
            .markdown-stream .hljs-doctag,
            .markdown-stream .hljs-keyword,
            .markdown-stream .hljs-formula {
              color: #c678dd;
            }
            .markdown-stream .hljs-section,
            .markdown-stream .hljs-name,
            .markdown-stream .hljs-selector-tag,
            .markdown-stream .hljs-deletion,
            .markdown-stream .hljs-subst {
              color: #e06c75;
            }
            .markdown-stream .hljs-literal {
              color: #56b6c2;
            }
            .markdown-stream .hljs-string,
            .markdown-stream .hljs-regexp,
            .markdown-stream .hljs-addition,
            .markdown-stream .hljs-attribute,
            .markdown-stream .hljs-meta-string {
              color: #98c379;
            }
            .markdown-stream .hljs-built_in,
            .markdown-stream .hljs-class .hljs-title {
              color: #e6c07b;
            }
            .markdown-stream .hljs-attr,
            .markdown-stream .hljs-variable,
            .markdown-stream .hljs-template-variable,
            .markdown-stream .hljs-type,
            .markdown-stream .hljs-selector-class,
            .markdown-stream .hljs-selector-attr,
            .markdown-stream .hljs-selector-pseudo,
            .markdown-stream .hljs-number {
              color: #d19a66;
            }
            .markdown-stream .hljs-symbol,
            .markdown-stream .hljs-bullet,
            .markdown-stream .hljs-link,
            .markdown-stream .hljs-meta,
            .markdown-stream .hljs-selector-id,
            .markdown-stream .hljs-title {
              color: #61aeee;
            }
            .markdown-stream .hljs-emphasis {
              font-style: italic;
            }
            .markdown-stream .hljs-strong {
              font-weight: bold;
            }
            .markdown-stream .hljs-link {
              text-decoration: underline;
            }
          `
        } else {
          style.textContent = `
            .markdown-stream pre code.hljs {
              display: block;
              overflow-x: auto;
              padding: 1em;
              color: #383a42;
              background: #fafafa;
            }
            .markdown-stream .hljs-comment,
            .markdown-stream .hljs-quote {
              color: #a0a1a7;
              font-style: italic;
            }
            .markdown-stream .hljs-doctag,
            .markdown-stream .hljs-keyword,
            .markdown-stream .hljs-formula {
              color: #a626a4;
            }
            .markdown-stream .hljs-section,
            .markdown-stream .hljs-name,
            .markdown-stream .hljs-selector-tag,
            .markdown-stream .hljs-deletion,
            .markdown-stream .hljs-subst {
              color: #e45649;
            }
            .markdown-stream .hljs-literal {
              color: #0184bb;
            }
            .markdown-stream .hljs-string,
            .markdown-stream .hljs-regexp,
            .markdown-stream .hljs-addition,
            .markdown-stream .hljs-attribute,
            .markdown-stream .hljs-meta-string {
              color: #50a14f;
            }
            .markdown-stream .hljs-built_in,
            .markdown-stream .hljs-class .hljs-title {
              color: #c18401;
            }
            .markdown-stream .hljs-attr,
            .markdown-stream .hljs-variable,
            .markdown-stream .hljs-template-variable,
            .markdown-stream .hljs-type,
            .markdown-stream .hljs-selector-class,
            .markdown-stream .hljs-selector-attr,
            .markdown-stream .hljs-selector-pseudo,
            .markdown-stream .hljs-number {
              color: #986801;
            }
            .markdown-stream .hljs-symbol,
            .markdown-stream .hljs-bullet,
            .markdown-stream .hljs-link,
            .markdown-stream .hljs-meta,
            .markdown-stream .hljs-selector-id,
            .markdown-stream .hljs-title {
              color: #4078f2;
            }
            .markdown-stream .hljs-emphasis {
              font-style: italic;
            }
            .markdown-stream .hljs-strong {
              font-weight: bold;
            }
            .markdown-stream .hljs-link {
              text-decoration: underline;
            }
          `
        }

        document.head.appendChild(style)
      } catch (error) {
        console.warn("Failed to load highlight.js theme:", error)
      }
    }

    loadHighlightTheme()

    // Listen for theme changes
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
    const handleThemeChange = () => loadHighlightTheme()

    mediaQuery.addEventListener("change", handleThemeChange)

    // Also listen for Bootstrap theme changes if they exist
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (
          mutation.type === "attributes" &&
          (mutation.attributeName === "data-bs-theme" ||
            mutation.attributeName === "class")
        ) {
          loadHighlightTheme()
        }
      })
    })

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-bs-theme", "class"],
    })
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    })

    return () => {
      mediaQuery.removeEventListener("change", handleThemeChange)
      observer.disconnect()
    }
  }, [])
}

export function MarkdownStream({
  content,
  contentType = "markdown",
  streaming = false,
  autoScroll = false,
  onContentChange,
  onStreamEnd,
}: MarkdownStreamProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollableElementRef = useRef<HTMLElement | null>(null)
  const isContentBeingAddedRef = useRef(false)
  const isUserScrolledRef = useRef(false)
  const clipboardInstancesRef = useRef<ClipboardJS[]>([])

  // Set up highlight.js theme handling
  useHighlightTheme()

  // Convert content to HTML
  const htmlContent =
    contentType === "text"
      ? content.replaceAll("\n", "<br>")
      : contentToHTML(content, contentType)

  // Streaming dot HTML - only when streaming
  const streamingDotHTML = streaming ? SVG_DOT : ""
  const finalHTML = htmlContent + streamingDotHTML

  // Scroll handler
  const isNearBottom = useCallback((): boolean => {
    const el = scrollableElementRef.current
    if (!el) return false
    return el.scrollHeight - (el.scrollTop + el.clientHeight) < 50
  }, [])

  const onScroll = useCallback((): void => {
    if (!isContentBeingAddedRef.current) {
      isUserScrolledRef.current = !isNearBottom()
    }
  }, [isNearBottom])

  const findScrollableParent = useCallback((): HTMLElement | null => {
    if (!autoScroll || !containerRef.current) return null

    let el: HTMLElement | null = containerRef.current
    while (el) {
      if (el.scrollHeight > el.clientHeight) return el
      el = el.parentElement
      // Stop at chat container to avoid scrolling parent elements
      if (el?.tagName?.toLowerCase() === "shiny-chat") {
        break
      }
    }
    return null
  }, [autoScroll])

  const updateScrollableElement = useCallback((): void => {
    const el = findScrollableParent()

    if (el !== scrollableElementRef.current) {
      scrollableElementRef.current?.removeEventListener("scroll", onScroll)
      scrollableElementRef.current = el
      scrollableElementRef.current?.addEventListener("scroll", onScroll)
    }
  }, [findScrollableParent, onScroll])

  const maybeScrollToBottom = useCallback((): void => {
    const el = scrollableElementRef.current
    if (!el || isUserScrolledRef.current) return

    el.scroll({
      top: el.scrollHeight - el.clientHeight,
      behavior: streaming ? "instant" : "smooth",
    })
  }, [streaming])

  // Throttled scroll to bottom
  const throttledScrollToBottom = useThrottle(maybeScrollToBottom, 50)

  const highlightAndCodeCopy = useCallback((): void => {
    if (!containerRef.current) return

    // Clean up existing clipboard instances
    clipboardInstancesRef.current.forEach((instance) => instance.destroy())
    clipboardInstancesRef.current = []

    const codeBlocks =
      containerRef.current.querySelectorAll<HTMLElement>("pre code")

    codeBlocks.forEach((el) => {
      if (el.dataset.highlighted === "yes") return

      // Highlight syntax
      hljs.highlightElement(el)

      // Add copy button
      const btn = document.createElement("button")
      btn.className = "code-copy-button"
      btn.title = "Copy to clipboard"
      btn.innerHTML = '<i class="bi"></i>'
      el.prepend(btn)

      // Setup clipboard
      const clipboard = new ClipboardJS(btn, { target: () => el })
      clipboardInstancesRef.current.push(clipboard)

      clipboard.on("success", (e) => {
        btn.classList.add("code-copy-button-checked")
        setTimeout(() => btn.classList.remove("code-copy-button-checked"), 2000)
        e.clearSelection()
      })
    })
  }, [])

  // Effect for content changes
  useEffect(() => {
    isContentBeingAddedRef.current = true

    // Post-process DOM after content has been added
    try {
      highlightAndCodeCopy()
    } catch (error) {
      console.warn("Failed to highlight code:", error)
    }

    // Update scrollable element after content has been added
    updateScrollableElement()

    // Possibly scroll to bottom after content has been added
    isContentBeingAddedRef.current = false
    throttledScrollToBottom()

    if (onContentChange) {
      try {
        onContentChange()
      } catch (error) {
        console.warn("Failed to call onContentChange callback:", error)
      }
    }
  }, [
    content,
    contentType,
    highlightAndCodeCopy,
    updateScrollableElement,
    throttledScrollToBottom,
    onContentChange,
  ])

  // Effect for streaming changes
  useEffect(() => {
    if (!streaming && onStreamEnd) {
      try {
        onStreamEnd()
      } catch (error) {
        console.warn("Failed to call onStreamEnd callback:", error)
      }
    }
  }, [streaming, onStreamEnd])

  // Cleanup effect
  useEffect(() => {
    return () => {
      scrollableElementRef.current?.removeEventListener("scroll", onScroll)
      clipboardInstancesRef.current.forEach((instance) => instance.destroy())
    }
  }, [onScroll])

  return (
    <div
      ref={containerRef}
      className="markdown-stream"
      data-streaming={streaming}
      dangerouslySetInnerHTML={{ __html: finalHTML }}
    />
  )
}
