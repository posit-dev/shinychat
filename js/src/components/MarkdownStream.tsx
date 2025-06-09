import { useEffect, useRef, useState, useCallback, useMemo } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import ClipboardJS from "clipboard"
import ReactMarkdown, { Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import rehypeRaw from "rehype-raw"
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
  // Theme configuration
  codeThemeLight?: string
  codeThemeDark?: string
}

// SVG dot to indicate content is currently streaming
const SVG_DOT_CLASS = "markdown-stream-dot"

// Default theme configuration
const CODE_THEME_LIGHT_DEFAULT = "atom-one-light"
const CODE_THEME_DARK_DEFAULT = "atom-one-dark"
const HIGHLIGHT_JS_CDN_BASE =
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles"

// Streaming dot component
function StreamingDot(): JSX.Element {
  return (
    <svg
      width="12"
      height="12"
      xmlns="http://www.w3.org/2000/svg"
      className={SVG_DOT_CLASS}
      style={{ marginLeft: ".25em", marginTop: "-.25em" }}
    >
      <circle cx="6" cy="6" r="6" />
    </svg>
  )
}

// Custom code block component with copy button
function CodeBlock(props: JSX.HTMLAttributes<HTMLElement>): JSX.Element {
  const { children, className, ...restProps } = props
  const codeRef = useRef<HTMLElement>(null)
  const clipboardRef = useRef<ClipboardJS | null>(null)

  useEffect(() => {
    if (!codeRef.current) return

    // Clean up existing clipboard instance
    if (clipboardRef.current) {
      clipboardRef.current.destroy()
    }

    // Find the copy button
    const copyButton = codeRef.current.querySelector(
      ".code-copy-button",
    ) as HTMLButtonElement
    if (!copyButton) return

    // Setup clipboard
    clipboardRef.current = new ClipboardJS(copyButton, {
      text: () => {
        // Get text content of the code element, excluding the button
        const codeText = Array.from(codeRef.current!.childNodes)
          .filter(
            (node) =>
              !node.nodeType ||
              (node as Element).className !== "code-copy-button",
          )
          .map((node) => node.textContent || "")
          .join("")
        return codeText
      },
    })

    clipboardRef.current.on("success", (e) => {
      copyButton.classList.add("code-copy-button-checked")
      setTimeout(
        () => copyButton.classList.remove("code-copy-button-checked"),
        2000,
      )
      e.clearSelection()
    })

    clipboardRef.current.on("error", (e) => {
      console.warn("Failed to copy to clipboard:", e)
    })

    return () => {
      if (clipboardRef.current) {
        clipboardRef.current.destroy()
        clipboardRef.current = null
      }
    }
  }, [children])

  return (
    <code
      ref={codeRef}
      className={className}
      {...(restProps as JSX.HTMLAttributes<HTMLElement>)}
    >
      <button
        className="code-copy-button"
        title="Copy to clipboard"
        onClick={(e) => e.preventDefault()}
      >
        <i className="bi"></i>
      </button>
      {children}
    </code>
  )
}

// Custom pre component to ensure proper styling
function PreBlock(props: JSX.HTMLAttributes<HTMLPreElement>): JSX.Element {
  const { children, ...restProps } = props
  return (
    <pre {...(restProps as JSX.HTMLAttributes<HTMLPreElement>)}>{children}</pre>
  )
}

// Custom table component with Bootstrap classes
function Table(props: JSX.HTMLAttributes<HTMLTableElement>): JSX.Element {
  const { children, ...restProps } = props
  return (
    <table
      className="table table-striped table-bordered"
      {...(restProps as JSX.HTMLAttributes<HTMLTableElement>)}
    >
      {children}
    </table>
  )
}

// Theme loading utility functions
function getThemeUrl(themeName: string): string {
  if (
    themeName === CODE_THEME_LIGHT_DEFAULT ||
    themeName === CODE_THEME_DARK_DEFAULT
  ) {
    // For local themes, we'll use embedded CSS
    return ""
  }
  return `${HIGHLIGHT_JS_CDN_BASE}/${themeName}.min.css`
}

function createStyleElement(themeName: string, css: string): HTMLStyleElement {
  const style = document.createElement("style")
  style.setAttribute("data-highlight-theme", themeName)
  style.setAttribute("data-markdown-stream", "true")
  style.textContent = css
  return style
}

function loadThemeStylesheet(themeName: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // Remove existing theme stylesheets
    document
      .querySelectorAll(
        'link[data-markdown-stream="true"], style[data-markdown-stream="true"]',
      )
      .forEach((el) => el.remove())

    // Handle local embedded themes
    if (
      themeName === CODE_THEME_LIGHT_DEFAULT ||
      themeName === CODE_THEME_DARK_DEFAULT
    ) {
      const css = getEmbeddedThemeCSS(themeName)
      const style = createStyleElement(themeName, css)
      document.head.appendChild(style)
      resolve()
      return
    }

    // Load theme from CDN
    const themeUrl = getThemeUrl(themeName)
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.type = "text/css"
    link.href = themeUrl
    link.setAttribute("data-highlight-theme", themeName)
    link.setAttribute("data-markdown-stream", "true")

    link.onload = () => resolve()
    link.onerror = () => {
      // Fallback to embedded theme if CDN fails
      console.warn(
        `Failed to load theme from CDN: ${themeUrl}. Falling back to embedded theme.`,
      )
      link.remove()
      const fallbackTheme = themeName.includes("dark")
        ? CODE_THEME_DARK_DEFAULT
        : CODE_THEME_LIGHT_DEFAULT
      const css = getEmbeddedThemeCSS(fallbackTheme)
      const style = createStyleElement(fallbackTheme, css)
      document.head.appendChild(style)
      resolve()
    }

    document.head.appendChild(link)
  })
}

function getEmbeddedThemeCSS(themeName: string): string {
  if (themeName === CODE_THEME_DARK_DEFAULT) {
    return `.markdown-stream {
  pre code.hljs {
    display: block;
    overflow-x: auto;
    padding: 1em;
  }
  code.hljs {
    padding: 3px 5px;
  }
  .hljs {
    color: #abb2bf;
    background: #282c34;
  }
  .hljs-comment,
  .hljs-quote {
    color: #5c6370;
    font-style: italic;
  }
  .hljs-doctag,
  .hljs-formula,
  .hljs-keyword {
    color: #c678dd;
  }
  .hljs-deletion,
  .hljs-name,
  .hljs-section,
  .hljs-selector-tag,
  .hljs-subst {
    color: #e06c75;
  }
  .hljs-literal {
    color: #56b6c2;
  }
  .hljs-addition,
  .hljs-attribute,
  .hljs-meta .hljs-string,
  .hljs-regexp,
  .hljs-string {
    color: #98c379;
  }
  .hljs-attr,
  .hljs-number,
  .hljs-selector-attr,
  .hljs-selector-class,
  .hljs-selector-pseudo,
  .hljs-template-variable,
  .hljs-type,
  .hljs-variable {
    color: #d19a66;
  }
  .hljs-bullet,
  .hljs-link,
  .hljs-meta,
  .hljs-selector-id,
  .hljs-symbol,
  .hljs-title {
    color: #61aeee;
  }
  .hljs-built_in,
  .hljs-class .hljs-title,
  .hljs-title.class_ {
    color: #e6c07b;
  }
  .hljs-emphasis {
    font-style: italic;
  }
  .hljs-strong {
    font-weight: 700;
  }
  .hljs-link {
    text-decoration: underline;
  }
}`
  } else {
    // atom-one-light theme
    return `.markdown-stream {
  pre code.hljs {
    display: block;
    overflow-x: auto;
    padding: 1em;
  }
  code.hljs {
    padding: 3px 5px;
  }
  .hljs {
    color: #383a42;
    background: #fafafa;
  }
  .hljs-comment,
  .hljs-quote {
    color: #a0a1a7;
    font-style: italic;
  }
  .hljs-doctag,
  .hljs-formula,
  .hljs-keyword {
    color: #a626a4;
  }
  .hljs-deletion,
  .hljs-name,
  .hljs-section,
  .hljs-selector-tag,
  .hljs-subst {
    color: #e45649;
  }
  .hljs-literal {
    color: #0184bb;
  }
  .hljs-addition,
  .hljs-attribute,
  .hljs-meta .hljs-string,
  .hljs-regexp,
  .hljs-string {
    color: #50a14f;
  }
  .hljs-attr,
  .hljs-number,
  .hljs-selector-attr,
  .hljs-selector-class,
  .hljs-selector-pseudo,
  .hljs-template-variable,
  .hljs-type,
  .hljs-variable {
    color: #986801;
  }
  .hljs-bullet,
  .hljs-link,
  .hljs-meta,
  .hljs-selector-id,
  .hljs-symbol,
  .hljs-title {
    color: #4078f2;
  }
  .hljs-built_in,
  .hljs-class .hljs-title,
  .hljs-title.class_ {
    color: #c18401;
  }
  .hljs-emphasis {
    font-style: italic;
  }
  .hljs-strong {
    font-weight: 700;
  }
  .hljs-link {
    text-decoration: underline;
  }
}

    `
  }
}

// Theme detection and CSS injection for highlight.js
function useHighlightTheme(
  lightTheme: string = CODE_THEME_LIGHT_DEFAULT,
  darkTheme: string = CODE_THEME_DARK_DEFAULT,
) {
  const [currentTheme, setCurrentTheme] = useState<string>("")

  useEffect(() => {
    const loadHighlightTheme = async () => {
      // Check if we're in dark mode
      const isDarkMode =
        window.matchMedia("(prefers-color-scheme: dark)").matches ||
        document.documentElement.getAttribute("data-bs-theme") === "dark" ||
        document.body.classList.contains("dark-theme")

      const selectedTheme = isDarkMode ? darkTheme : lightTheme

      // Don't reload if it's the same theme
      if (currentTheme === selectedTheme) {
        return
      }

      try {
        await loadThemeStylesheet(selectedTheme)
        setCurrentTheme(selectedTheme)
      } catch (error) {
        console.warn("Failed to load highlight.js theme:", error)
        // Fallback to default embedded theme
        const fallbackTheme = isDarkMode
          ? CODE_THEME_DARK_DEFAULT
          : CODE_THEME_LIGHT_DEFAULT
        try {
          await loadThemeStylesheet(fallbackTheme)
          setCurrentTheme(fallbackTheme)
        } catch (fallbackError) {
          console.error("Failed to load fallback theme:", fallbackError)
        }
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
  }, [lightTheme, darkTheme, currentTheme])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      document
        .querySelectorAll(
          'link[data-markdown-stream="true"], style[data-markdown-stream="true"]',
        )
        .forEach((el) => el.remove())
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
  codeThemeLight = CODE_THEME_LIGHT_DEFAULT,
  codeThemeDark = CODE_THEME_DARK_DEFAULT,
}: MarkdownStreamProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollableElementRef = useRef<HTMLElement | null>(null)
  const isContentBeingAddedRef = useRef(false)
  const isUserScrolledRef = useRef(false)

  // Set up highlight.js theme handling
  useHighlightTheme(codeThemeLight, codeThemeDark)

  // Process content based on type
  const processedContent = useMemo(() => {
    if (contentType === "text") {
      // For text content, escape HTML and preserve line breaks
      return content
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;")
        .replaceAll("\n", "<br>")
    } else if (contentType === "html") {
      return sanitizeHTML(content)
    } else {
      // For markdown and semi-markdown, return as-is for react-markdown to process
      return content
    }
  }, [content, contentType])

  // Custom components for react-markdown
  const components = useMemo(() => {
    const baseComponents = {
      code: CodeBlock,
      pre: PreBlock,
      table: Table,
    }

    // For semi-markdown, we want to escape HTML
    if (contentType === "semi-markdown") {
      return {
        ...baseComponents,
        // Override HTML rendering to escape it
        html: ({
          children,
        }: {
          children: string | number | undefined | null
        }) => (
          <span>
            {String(children).replaceAll("<", "&lt;").replaceAll(">", "&gt;")}
          </span>
        ),
      }
    }

    return baseComponents
  }, [contentType])

  // Remark/Rehype plugins
  const remarkPlugins = useMemo(() => [remarkGfm], [])
  const rehypePlugins = useMemo(() => {
    const plugins = [rehypeHighlight, rehypeRaw]
    // Only allow raw HTML for markdown and html content types
    if (contentType === "markdown" || contentType === "html") {
      plugins.slice(1, 1) // Remove rehypeRaw if not needed
    }
    return plugins
  }, [contentType])

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

    // Start from the parent of our container div, not the container div itself
    let el: HTMLElement | null = containerRef.current.parentElement
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

  // Effect for content changes
  useEffect(() => {
    isContentBeingAddedRef.current = true

    // Update scrollable element after content has been added
    updateScrollableElement()

    // Possibly scroll to bottom after content has been added
    isContentBeingAddedRef.current = false
    maybeScrollToBottom()

    if (onContentChange) {
      try {
        onContentChange()
      } catch (error) {
        console.warn("Failed to call onContentChange callback:", error)
      }
    }
  }, [content, contentType, updateScrollableElement, onContentChange])

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
    }
  }, [onScroll])

  // Render content based on type
  const renderContent = () => {
    if (contentType === "text") {
      return <div dangerouslySetInnerHTML={{ __html: processedContent }} />
    } else if (contentType === "html") {
      return <div dangerouslySetInnerHTML={{ __html: processedContent }} />
    } else {
      // Use ReactMarkdown for markdown and semi-markdown
      return (
        <ReactMarkdown
          remarkPlugins={remarkPlugins}
          rehypePlugins={rehypePlugins}
          components={components as Components}
        >
          {processedContent}
        </ReactMarkdown>
      )
    }
  }

  return (
    <div
      ref={containerRef}
      className="markdown-stream"
      data-streaming={streaming}
    >
      {renderContent()}
      {streaming && <StreamingDot />}
    </div>
  )
}
