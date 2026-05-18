import { useRef, useCallback } from "react"

export function useInputHistory(userMessages: string[]): {
  recall: (direction: "up" | "down", currentValue: string) => string | undefined
  reset: () => void
  isActive: () => boolean
} {
  const indexRef = useRef<number>(-1)
  const draftsRef = useRef(new Map<number, string>())
  const activatedRef = useRef(false)
  const prevMessagesRef = useRef(userMessages)
  if (prevMessagesRef.current !== userMessages) {
    prevMessagesRef.current = userMessages
    indexRef.current = -1
    draftsRef.current.clear()
    activatedRef.current = false
  }

  const recall = useCallback(
    (direction: "up" | "down", currentValue: string): string | undefined => {
      const maxIdx = userMessages.length - 1

      draftsRef.current.set(indexRef.current, currentValue)

      if (direction === "up") {
        if (userMessages.length === 0) return undefined
        activatedRef.current = true
        if (indexRef.current > maxIdx) indexRef.current = -1
        const next =
          indexRef.current === -1 ? maxIdx : Math.max(0, indexRef.current - 1)
        indexRef.current = next
        return draftsRef.current.get(next) ?? userMessages[next]
      } else {
        const current = indexRef.current
        if (current === -1) return undefined
        if (current > maxIdx) {
          indexRef.current = -1
          return undefined
        }
        if (current >= maxIdx) {
          indexRef.current = -1
          return draftsRef.current.get(-1) ?? ""
        }
        const next = current + 1
        indexRef.current = next
        return draftsRef.current.get(next) ?? userMessages[next]
      }
    },
    [userMessages],
  )

  const reset = useCallback(() => {
    indexRef.current = -1
    draftsRef.current.clear()
    activatedRef.current = false
  }, [])

  const isActive = useCallback(() => activatedRef.current, [])

  return { recall, reset, isActive }
}
