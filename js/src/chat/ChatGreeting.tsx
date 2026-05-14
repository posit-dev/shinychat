import {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  memo,
  type CSSProperties,
} from "react"
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

// Time the new user / assistant messages settle into the DOM before the
// greeting starts its collapse animation — without this the eye has to track
// too much movement at once.
const DISMISS_DELAY_MS = 350

export const ChatGreeting = memo(function ChatGreeting({
  greeting,
}: ChatGreetingProps) {
  const reducedMotion = usePrefersReducedMotion()
  const [dismissing, setDismissing] = useState(false)
  const [pendingDismiss, setPendingDismiss] = useState(false)
  const [removed, setRemoved] = useState(false)
  const [prevVisible, setPrevVisible] = useState(greeting.visible)
  const outerRef = useRef<HTMLDivElement>(null)
  // Captured each layout pass while the greeting is at its natural height, so
  // the dismiss animation can interpolate from a known starting height set
  // inline in the same render that flips data-dismissing.
  const lastHeightRef = useRef<number | null>(null)

  // Detect visible:true → visible:false (and the inverse) synchronously during
  // render. Without this, the next commit returns null briefly before
  // dismissing flips, and the greeting visually disappears then re-appears.
  if (prevVisible !== greeting.visible) {
    setPrevVisible(greeting.visible)
    if (prevVisible && !greeting.visible) {
      if (reducedMotion) {
        setRemoved(true)
      } else {
        setPendingDismiss(true)
      }
    } else if (greeting.visible) {
      setDismissing(false)
      setPendingDismiss(false)
      setRemoved(false)
    }
  }

  useLayoutEffect(() => {
    if (!dismissing && outerRef.current) {
      lastHeightRef.current = outerRef.current.offsetHeight
    }
  })

  useEffect(() => {
    if (!pendingDismiss) return
    const timer = window.setTimeout(() => {
      setPendingDismiss(false)
      setDismissing(true)
    }, DISMISS_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [pendingDismiss])

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

  if (removed || (!greeting.visible && !pendingDismiss && !dismissing)) {
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
