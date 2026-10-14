import { useMemo, useRef } from "react"
import {
  requestDefinitionIcons,
  supersededRequestIds,
  type ChatMessageData,
} from "./state"

/**
 * Every superseded request-id, derived from the transcript (see
 * `supersededRequestIds`), with a stable object identity.
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
): Set<string> {
  const previous = useRef<Set<string>>(new Set())
  return useMemo(() => {
    const next = supersededRequestIds(messages, streamingMessage)
    const prev = previous.current
    if (next.size === prev.size && [...next].every((id) => prev.has(id))) {
      return prev
    }
    previous.current = next
    return next
  }, [messages, streamingMessage])
}

/**
 * Definition icons keyed by request id, with a stable map identity when the
 * transcript's icon metadata has not changed.
 */
export function useRequestDefinitionIcons(
  messages: ChatMessageData[],
  streamingMessage: ChatMessageData | null,
): ReadonlyMap<string, string> {
  const previous = useRef<Map<string, string>>(new Map())
  return useMemo(() => {
    const next = requestDefinitionIcons(messages, streamingMessage)
    const prev = previous.current
    if (
      next.size === prev.size &&
      [...next].every(([requestId, icon]) => prev.get(requestId) === icon)
    ) {
      return prev
    }
    previous.current = next
    return next
  }, [messages, streamingMessage])
}
