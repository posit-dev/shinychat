import { useMemo, useRef } from "react"
import { supersededRequestIds, type ChatMessageData } from "./state"

/**
 * Every superseded request-id: those derived from the transcript (see
 * `supersededRequestIds`) unioned with those the server signalled (see
 * `signalledSupersededRequests`), with a stable object identity.
 *
 * The ids are recomputed whenever the transcript changes, which while a response
 * streams means every chunk. They reach every message through context, so
 * handing back a fresh `Set` each time would re-render the entire transcript on
 * every chunk — finalized messages included, which are `memo`'d precisely so
 * they don't. Only the membership matters, so keep the previous `Set` whenever
 * the ids are unchanged; in practice it changes a handful of times per response.
 */
export function useSupersededRequests(
  messages: ChatMessageData[],
  streamingMessage: ChatMessageData | null,
  signalled: Set<string>,
): Set<string> {
  const previous = useRef<Set<string>>(new Set())
  return useMemo(() => {
    const next = supersededRequestIds(messages, streamingMessage)
    for (const id of signalled) next.add(id)
    const prev = previous.current
    if (next.size === prev.size && [...next].every((id) => prev.has(id))) {
      return prev
    }
    previous.current = next
    return next
  }, [messages, streamingMessage, signalled])
}
