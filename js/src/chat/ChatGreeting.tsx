import { useState, useEffect, useRef, useContext, memo } from "react"
import type { GreetingData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { ChatDispatchContext } from "./context"

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
  const dispatch = useContext(ChatDispatchContext)
  const outerRef = useRef<HTMLDivElement>(null)
  // Reveal animation runs once per component instance. Replacements that keep
  // the wrapper mounted (chat_set_greeting on a visible greeting) skip it;
  // unmount+remount (clear → re-show, regenerate pattern) re-runs it.
  const [entering, setEntering] = useState(true)

  const dismissing = greeting.dismissing

  useEffect(() => {
    if (!entering) return
    if (reducedMotion) {
      setEntering(false)
      return
    }
    const el = outerRef.current
    if (!el) return
    function onAnimationEnd(e: AnimationEvent) {
      if (e.animationName === "shiny-chat-greeting-reveal") {
        setEntering(false)
      }
    }
    el.addEventListener("animationend", onAnimationEnd)
    return () => el.removeEventListener("animationend", onAnimationEnd)
  }, [entering, reducedMotion])

  useEffect(() => {
    if (!dismissing) return
    if (reducedMotion) {
      dispatch?.({ type: "greeting_dismissed" })
      return
    }
    const el = outerRef.current
    if (!el) return

    function onAnimationEnd(e: AnimationEvent) {
      if (e.animationName === "shiny-chat-greeting-dismiss") {
        dispatch?.({ type: "greeting_dismissed" })
      }
    }

    el.addEventListener("animationend", onAnimationEnd, { once: true })
    return () => el.removeEventListener("animationend", onAnimationEnd)
  }, [dismissing, reducedMotion, dispatch])

  if (!greeting.visible && !dismissing) {
    return null
  }

  const lastBlockIndex = greeting.blocks.length - 1

  const className = entering
    ? "shiny-chat-greeting shiny-chat-greeting--enter"
    : "shiny-chat-greeting"

  return (
    <div
      className={className}
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
