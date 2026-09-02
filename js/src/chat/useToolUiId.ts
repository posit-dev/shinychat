import { useId } from "react"

/**
 * Element id for tool UI chrome (aria wiring). Not seeded from request-ids or
 * group keys: request-ids are optional in routed content and can repeat across
 * messages, and group keys are only unique within one routed loop — either
 * could produce duplicate or unstable document ids.
 */
export function useToolUiId(prefix: string): string {
  return `${prefix}${useId()}`
}
