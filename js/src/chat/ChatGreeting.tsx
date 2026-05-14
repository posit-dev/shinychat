import {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useContext,
  memo,
  type CSSProperties,
} from "react"
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
  // Captured each layout pass while the greeting is at its natural height, so
  // the dismiss animation can interpolate from a known starting height set
  // inline in the same render that flips data-dismissing.
  const lastHeightRef = useRef<number | null>(null)

  const dismissing = greeting.dismissing

  useLayoutEffect(() => {
    if (!dismissing && outerRef.current) {
      lastHeightRef.current = outerRef.current.offsetHeight
    }
  })

  useEffect(() => {
    if (!dismissing) return
    if (reducedMotion) {
      dispatch?.({ type: "greeting_dismissed" })
      return
    }
    const el = outerRef.current
    if (!el) return

    function onAnimationEnd() {
      dispatch?.({ type: "greeting_dismissed" })
    }

    el.addEventListener("animationend", onAnimationEnd, { once: true })
    return () => el.removeEventListener("animationend", onAnimationEnd)
  }, [dismissing, reducedMotion, dispatch])

  if (!greeting.visible && !dismissing) {
    return null
  }

  const style: CSSProperties | undefined =
    dismissing && lastHeightRef.current != null
      ? ({
          "--_dismiss-height": `${lastHeightRef.current}px`,
        } as CSSProperties)
      : undefined

  const lastBlockIndex = greeting.blocks.length - 1

  return (
    <div
      className="shiny-chat-greeting"
      ref={outerRef}
      style={style}
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
