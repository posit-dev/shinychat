const KEY_PREFIX = "shinychat-current"
const URL_CONV_PARAM = "shinychat_conversation_id"

export function getConversationIdFromUrl(): string | null {
  try {
    return new URLSearchParams(window.location.search).get(URL_CONV_PARAM)
  } catch {
    return null
  }
}

export function getCurrentConversationId(elementId: string): string | null {
  try {
    return localStorage.getItem(`${KEY_PREFIX}:${elementId}`)
  } catch {
    return null
  }
}

export function setCurrentConversationId(
  elementId: string,
  id: string | null,
): void {
  try {
    if (id === null) {
      localStorage.removeItem(`${KEY_PREFIX}:${elementId}`)
    } else {
      localStorage.setItem(`${KEY_PREFIX}:${elementId}`, id)
    }
  } catch {
    // localStorage unavailable (private mode, sandboxed iframe, etc.)
  }
}
