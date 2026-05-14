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

export const ChatGreeting = memo(function ChatGreeting({
  greeting,
}: ChatGreetingProps) {
  const reducedMotion = usePrefersReducedMotion()
  const [dismissing, setDismissing] = useState(false)
  const [removed, setRemoved] = useState(false)
  const [prevVisible, setPrevVisible] = useState(greeting.visible)
  const outerRef = useRef<HTMLDivElement>(null)
  // Captured during the last render where the greeting was still visible, so
  // the dismiss animation can interpolate from the real rendered height
  // without a layout-effect detour that would let a no-greeting frame paint.
  const lastHeightRef = useRef<number | null>(null)

  // Detect visible:true → visible:false (and the inverse) synchronously during
  // render so `dismissing` flips in the same commit that sets visible=false.
  // Without this, there's a one-frame gap where the component renders nothing
  // before the useEffect for the prop change runs, causing the greeting to
  // briefly disappear and then re-appear to animate out.
  if (prevVisible !== greeting.visible) {
    setPrevVisible(greeting.visible)
    if (prevVisible && !greeting.visible) {
      if (reducedMotion) {
        setRemoved(true)
      } else {
        setDismissing(true)
      }
    } else if (greeting.visible) {
      setDismissing(false)
      setRemoved(false)
    }
  }

  useLayoutEffect(() => {
    if (greeting.visible && !dismissing && outerRef.current) {
      lastHeightRef.current = outerRef.current.offsetHeight
    }
  })

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
