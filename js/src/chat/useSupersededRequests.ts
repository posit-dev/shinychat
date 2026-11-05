import { useMemo, useRef } from "react"
import {
  requestDefinitions,
  supersededRequestIds,
  type ChatMessageData,
  type RequestDefinition,
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
 * Definition identity (title, icon) keyed by request id, with a stable map
 * identity when the transcript's definition metadata has not changed.
 */
export function useRequestDefinitions(
  messages: ChatMessageData[],
  streamingMessage: ChatMessageData | null,
): ReadonlyMap<string, RequestDefinition> {
  const previous = useRef<Map<string, RequestDefinition>>(new Map())
  return useMemo(() => {
    const next = requestDefinitions(messages, streamingMessage)
    const prev = previous.current
    if (
      next.size === prev.size &&
      [...next].every(([requestId, definition]) => {
        const prevDefinition = prev.get(requestId)
        return (
          prevDefinition !== undefined &&
          prevDefinition.title === definition.title &&
          prevDefinition.icon === definition.icon
        )
      })
    ) {
      return prev
    }
    previous.current = next
    return next
  }, [messages, streamingMessage])
}
