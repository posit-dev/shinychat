import { useRef, useCallback } from "react"

export function useInputHistory(userMessages: string[]): {
  recall: (direction: "up" | "down") => string | undefined
  reset: () => void
} {
  const indexRef = useRef<number>(-1)

  const recall = useCallback(
    (direction: "up" | "down"): string | undefined => {
      const maxIdx = userMessages.length - 1
      const current = indexRef.current

      if (direction === "up") {
        if (userMessages.length === 0) return undefined
        if (current > maxIdx) indexRef.current = -1
        const next =
          indexRef.current === -1 ? maxIdx : Math.max(0, indexRef.current - 1)
        indexRef.current = next
        return userMessages[next]
      } else {
        if (current === -1) return undefined
        if (current > maxIdx) {
          indexRef.current = -1
          return undefined
        }
        if (current >= maxIdx) {
          indexRef.current = -1
          return ""
        }
        const next = current + 1
        indexRef.current = next
        return userMessages[next]
      }
    },
    [userMessages],
  )

  const reset = useCallback(() => {
    indexRef.current = -1
  }, [])

  return { recall, reset }
}
