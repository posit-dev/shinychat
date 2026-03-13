import { useState, useRef, useCallback, useEffect } from "react"
import { createPortal } from "react-dom"
import { fullscreenEnter, xLg } from "../utils/icons"

export { fullscreenEnter }

export function useFullscreen(cardRef: React.RefObject<HTMLElement | null>) {
  const [isActive, setIsActive] = useState(false)
  const activeRef = useRef(false) // sync guard for enter/exit callbacks
  const triggerRef = useRef<HTMLElement | null>(null)
  const closeBtnRef = useRef<HTMLButtonElement | null>(null)

  // trapFocusExitRef and stableKeydownHandler are declared before exitFullscreen
  // so that exitFullscreen can reference stableKeydownHandler.current.
  // trapFocusExitRef.current is updated after trapFocusExit is defined below.
  const trapFocusExitRef = useRef<((e: KeyboardEvent) => void) | null>(null)

  // Stable handler: never changes identity, delegates to the ref for latest logic
  const stableKeydownHandler = useRef((e: KeyboardEvent): void => {
    trapFocusExitRef.current?.(e)
  })

  const exitFullscreen = useCallback(() => {
    if (!activeRef.current) return
    const card = cardRef.current
    if (!card) return

    activeRef.current = false
    setIsActive(false)

    card.removeAttribute("fullscreen")
    card.removeAttribute("tabindex")
    window.dispatchEvent(new Event("resize"))

    document.removeEventListener("keydown", stableKeydownHandler.current, true)

    triggerRef.current?.focus()
    triggerRef.current = null
  }, [cardRef])

  const trapFocusExit = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        const target = e.target as HTMLElement
        if (
          typeof target.matches === "function" &&
          (target.matches("select[open]") ||
            target.matches("input[aria-expanded='true']"))
        ) {
          return
        }
        exitFullscreen()
        e.preventDefault()
        return
      }

      if (e.key !== "Tab") return

      const card = cardRef.current
      if (!card?.hasAttribute("fullscreen") || !activeRef.current) return

      const cardFocusable = [
        ...card.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((el) => el.offsetParent !== null)
      const closeBtn = closeBtnRef.current
      if (!closeBtn) return

      const firstInCard = cardFocusable[0]
      const lastInCard = cardFocusable[cardFocusable.length - 1]
      const active = document.activeElement

      if (!e.shiftKey && (active === lastInCard || active === card)) {
        e.preventDefault()
        closeBtn.focus()
      } else if (!e.shiftKey && active === closeBtn) {
        e.preventDefault()
        ;(firstInCard ?? card).focus()
      } else if (e.shiftKey && (active === firstInCard || active === card)) {
        e.preventDefault()
        closeBtn.focus()
      } else if (e.shiftKey && active === closeBtn) {
        e.preventDefault()
        ;(lastInCard ?? card).focus()
      } else if (!card.contains(active as Node) && active !== closeBtn) {
        e.preventDefault()
        card.focus()
      }
    },
    [cardRef, exitFullscreen],
  )

  // Keep trapFocusExitRef up to date with the latest trapFocusExit
  trapFocusExitRef.current = trapFocusExit

  const enterFullscreen = useCallback(
    (trigger: HTMLElement) => {
      if (activeRef.current) return
      const card = cardRef.current
      if (!card) return

      activeRef.current = true
      setIsActive(true)
      triggerRef.current = trigger

      card.setAttribute("fullscreen", "")
      window.dispatchEvent(new Event("resize"))

      document.addEventListener("keydown", stableKeydownHandler.current, true)
      card.setAttribute("tabindex", "-1")
      card.focus()
    },
    [cardRef],
  )

  // Cleanup on unmount
  useEffect(() => {
    const card = cardRef.current
    const stableHandler = stableKeydownHandler.current
    return () => {
      if (activeRef.current) {
        activeRef.current = false
        if (card) {
          card.removeAttribute("fullscreen")
          card.removeAttribute("tabindex")
        }
        document.removeEventListener("keydown", stableHandler, true)
        triggerRef.current?.focus()
        triggerRef.current = null
      }
    }
  }, [cardRef])

  const overlay = isActive
    ? createPortal(
        <div
          className="shiny-tool-fullscreen-backdrop"
          onClick={exitFullscreen}
        >
          <button
            ref={closeBtnRef}
            type="button"
            className="shiny-tool-fullscreen-exit"
            aria-label="Exit fullscreen"
            onClick={(ev) => {
              ev.stopPropagation()
              exitFullscreen()
            }}
          >
            Close <span dangerouslySetInnerHTML={{ __html: xLg }} />
          </button>
        </div>,
        document.body,
      )
    : null

  return { enterFullscreen, exitFullscreen, overlay }
}
