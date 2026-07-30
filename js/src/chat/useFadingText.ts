import { useLayoutEffect, useRef, useState } from "react"
import { usePrefersReducedMotion } from "./usePrefersReducedMotion"

// Kept in step with the `transition: opacity` duration on the elements that
// consume this hook (`.shinychat-thinking-label`,
// `.shinychat-tool-group__title`): the swap happens once the fade-out has
// finished, so the reader never sees the text change.
export const FADE_DURATION_MS = 200

/**
 * Crossfade a piece of activity-row text when it changes: fade the current
 * value out, swap it, fade the new one in. Used by the thinking header
 * ("Thinking" → "Thought for 2s") and by a tool group's title
 * ("Inspecting schema" → "Inspected schema").
 *
 * `key` is what identifies the value. `value` must be a pure function of it —
 * the hook never compares values, so a value that changes without its key
 * changing is not picked up until the next real transition. That is what lets
 * callers fade rendered content (which is a fresh object every render) rather
 * than only plain strings.
 *
 * There is no fade on first render, and none at all under
 * `prefers-reduced-motion`.
 */
export function useFadingValue<T>(
  value: T,
  key: string,
): { visible: T; fading: boolean } {
  const reducedMotion = usePrefersReducedMotion()
  const [visible, setVisible] = useState({ key, value })
  const [fading, setFading] = useState(false)
  const pending = useRef({ key, value })

  useLayoutEffect(() => {
    pending.current = { key, value }
    if (key === visible.key) return

    if (reducedMotion) {
      setVisible({ key, value })
      setFading(false)
      return
    }

    setFading(true)
    const timer = setTimeout(() => {
      setVisible(pending.current)
      setFading(false)
    }, FADE_DURATION_MS)

    return () => clearTimeout(timer)
  }, [key, value, visible.key, reducedMotion])

  return { visible: visible.value, fading }
}

/** {@link useFadingValue} for a plain string, which is its own key. */
export function useFadingText(text: string): {
  visible: string
  fading: boolean
} {
  return useFadingValue(text, text)
}
