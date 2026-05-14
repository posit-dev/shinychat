import { useState, useEffect, useRef, memo } from "react"
import type { GreetingData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { chatTagToComponentMap } from "./chatTagToComponentMap"

interface ChatGreetingProps {
  greeting: GreetingData
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  )
  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)")
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mql.addEventListener("change", handler)
    return () => mql.removeEventListener("change", handler)
  }, [])
  return reduced
}

export const ChatGreeting = memo(function ChatGreeting({
  greeting,
}: ChatGreetingProps) {
  const reducedMotion = usePrefersReducedMotion()
  const [dismissing, setDismissing] = useState(false)
  const [removed, setRemoved] = useState(false)
  const prevVisibleRef = useRef(greeting.visible)
  const outerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const wasVisible = prevVisibleRef.current
    prevVisibleRef.current = greeting.visible

    if (wasVisible && !greeting.visible) {
      if (reducedMotion) {
        setRemoved(true)
      } else {
        const el = outerRef.current
        if (el) {
          el.style.setProperty("--_dismiss-height", `${el.offsetHeight}px`)
        }
        setDismissing(true)
      }
    }

    if (greeting.visible) {
      setDismissing(false)
      setRemoved(false)
    }
  }, [greeting.visible, reducedMotion])

  useEffect(() => {
    if (!dismissing) return
    const el = outerRef.current
    if (!el) return

    function onAnimationEnd() {
      setRemoved(true)
      setDismissing(false)
    }

    el.addEventListener("animationend", onAnimationEnd, { once: true })
    return () => el.removeEventListener("animationend", onAnimationEnd)
  }, [dismissing])

  if (removed || (!greeting.visible && !dismissing)) {
    return null
  }

  const lastBlockIndex = greeting.blocks.length - 1

  return (
    <div
      className="shiny-chat-greeting"
      ref={outerRef}
      {...(dismissing ? { "data-dismissing": "" } : {})}
    >
      <div className="shiny-chat-greeting-content">
        {greeting.blocks.map((block, i) => (
          <MarkdownContent
            key={i}
            content={block.content}
            contentType={block.contentType}
            role="assistant"
            streaming={greeting.streaming && i === lastBlockIndex}
            tagToComponentMap={chatTagToComponentMap}
          />
        ))}
      </div>
    </div>
  )
})
