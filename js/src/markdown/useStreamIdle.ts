import { useEffect, useState } from "react"

/**
 * How long streamed content must sit unchanged before the streaming dot
 * appears. Paced streaming reveals text continuously while the model is
 * producing it, so a gap this long means the source itself has stalled.
 */
export const STREAM_IDLE_MS = 1500

/**
 * True while `active` and `activity` has not changed for `delayMs`. Any
 * change to `activity` (compared by identity) reads as not-idle in the same
 * render, so an indicator gated on this never lingers past new content.
 */
export function useStreamIdle(
  active: boolean,
  activity: unknown,
  delayMs: number = STREAM_IDLE_MS,
): boolean {
  // Boxed so a function-valued `activity` isn't treated as a state updater.
  const [idleOn, setIdleOn] = useState<{ activity: unknown } | null>(null)

  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => setIdleOn({ activity }), delayMs)
    return () => clearTimeout(timer)
  }, [active, activity, delayMs])

  return active && idleOn !== null && idleOn.activity === activity
}
