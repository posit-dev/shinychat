import type {
  ChatTransport,
  ShinyLifecycle,
  ChatAction,
  MessagePayload,
  ShinyClientMessage,
} from "./types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

/**
 * Legacy envelope format sent by current Python/R backends.
 * Maps to: { id, handler: string, obj: ... }
 */
type LegacyEnvelope = {
  id: string
  handler: string
  obj: LegacyMessageObj | LegacyUpdateInputObj | null
}

type LegacyMessageObj = {
  content: string
  role: "user" | "assistant"
  content_type: "markdown" | "html" | "text" | "semi-markdown"
  chunk_type: "message_start" | "message_end" | null
  operation: "append" | "replace" | null
  icon?: string
  html_deps?: HtmlDep[]
}

type LegacyUpdateInputObj = {
  value?: string
  placeholder?: string
  submit?: boolean
  focus?: boolean
}

/**
 * Translate a legacy backend envelope into one or more ChatActions.
 * This shim can be removed once the backend sends the new unified format.
 */
function legacyToActions(envelope: LegacyEnvelope): ChatAction[] {
  const { handler, obj } = envelope

  switch (handler) {
    case "shiny-chat-append-message": {
      const msg = obj as LegacyMessageObj
      const payload: MessagePayload = {
        role: msg.role,
        content: msg.content,
        content_type: msg.content_type,
        icon: msg.icon,
        html_deps: msg.html_deps,
      }
      return [{ type: "message", message: payload }]
    }

    case "shiny-chat-append-message-chunk": {
      const msg = obj as LegacyMessageObj

      if (msg.chunk_type === "message_start") {
        const payload: MessagePayload = {
          role: msg.role,
          content: msg.content,
          content_type: msg.content_type,
          icon: msg.icon,
          html_deps: msg.html_deps,
        }
        return [{ type: "chunk_start", message: payload }]
      }

      if (msg.chunk_type === "message_end") {
        // The message_end chunk may carry final content (e.g., from
        // transform_assistant_response). Apply it before ending the stream.
        const actions: ChatAction[] = []
        if (msg.content) {
          actions.push({
            type: "chunk",
            content: msg.content,
            operation: msg.operation === "append" ? "append" : "replace",
            content_type: msg.content_type,
          })
        }
        actions.push({ type: "chunk_end" })
        return actions
      }

      // Intermediate chunk
      return [
        {
          type: "chunk",
          content: msg.content,
          operation: msg.operation === "append" ? "append" : "replace",
          content_type: msg.content_type,
        },
      ]
    }

    case "shiny-chat-clear-messages":
      return [{ type: "clear" }]

    case "shiny-chat-update-user-input": {
      const input = obj as LegacyUpdateInputObj
      return [
        {
          type: "update_input",
          value: input.value,
          placeholder: input.placeholder,
          submit: input.submit,
          focus: input.focus,
        },
      ]
    }

    case "shiny-chat-remove-loading-message":
      return [{ type: "remove_loading" }]

    default:
      return []
  }
}

// Window-global singleton to ensure only one shinyChatMessage handler is
// registered even when multiple bundles (chat + markdown-stream) load this module
declare global {
  interface Window {
    __shinyChatTransport?: ShinyTransport
  }
}

/**
 * Get the shared ShinyTransport singleton.
 * Stored on `window` so it survives across separate esbuild entry points.
 */
export function getShinyTransport(): ShinyTransport {
  if (!window.__shinyChatTransport) {
    window.__shinyChatTransport = new ShinyTransport()
  }
  return window.__shinyChatTransport
}

export class ShinyTransport implements ChatTransport, ShinyLifecycle {
  private listeners = new Map<string, Set<(action: ChatAction) => void>>()
  private pendingMessages = new Map<string, ChatAction[]>()

  constructor() {
    window.Shiny?.addCustomMessageHandler(
      "shinyChatMessage",
      async (envelope: LegacyEnvelope) => {
        const { id } = envelope

        // Translate legacy format to ChatAction(s)
        const actions = legacyToActions(envelope)
        if (actions.length === 0) {
          this.showClientMessage({
            status: "warning",
            message: `Unknown chat handler: "${envelope.handler}"`,
          })
          return
        }

        // Render HTML deps before dispatching
        for (const action of actions) {
          if ("message" in action && action.message?.html_deps) {
            await this.renderDependencies(action.message.html_deps)
          }
        }

        const callbacks = this.listeners.get(id)
        if (!callbacks || callbacks.size === 0) {
          // Queue messages that arrive before listeners are registered
          if (!this.pendingMessages.has(id)) {
            this.pendingMessages.set(id, [])
          }
          this.pendingMessages.get(id)!.push(...actions)
          return
        }

        for (const action of actions) {
          for (const cb of callbacks) {
            cb(action)
          }
        }
      },
    )
  }

  sendInput(id: string, value: string): void {
    window.Shiny.setInputValue!(id, value, { priority: "event" })
  }

  onMessage(id: string, callback: (action: ChatAction) => void): () => void {
    if (!this.listeners.has(id)) {
      this.listeners.set(id, new Set())
    }
    this.listeners.get(id)!.add(callback)

    // Flush any messages that arrived before this listener was registered
    const pending = this.pendingMessages.get(id)
    if (pending && pending.length > 0) {
      this.pendingMessages.delete(id)
      for (const action of pending) {
        callback(action)
      }
    }

    return () => {
      this.listeners.get(id)?.delete(callback)
    }
  }

  async renderDependencies(deps: HtmlDep[]): Promise<void> {
    if (!window.Shiny) return
    if (!deps) return

    try {
      await window.Shiny.renderDependenciesAsync(deps)
    } catch (error) {
      this.showClientMessage({
        status: "error",
        message: `Failed to render HTML dependencies: ${error}`,
      })
    }
  }

  async bindAll(el: HTMLElement): Promise<void> {
    if (!window?.Shiny?.initializeInputs) return
    if (!window?.Shiny?.bindAll) return

    try {
      window.Shiny.initializeInputs(el)
    } catch (err) {
      this.showClientMessage({
        status: "error",
        message: `Failed to initialize Shiny inputs: ${err}`,
      })
    }

    try {
      await window.Shiny.bindAll(el)
    } catch (err) {
      this.showClientMessage({
        status: "error",
        message: `Failed to bind Shiny inputs/outputs: ${err}`,
      })
    }
  }

  unbindAll(el: HTMLElement): void {
    if (!window?.Shiny?.unbindAll) return

    try {
      window.Shiny.unbindAll(el)
    } catch (err) {
      this.showClientMessage({
        status: "error",
        message: `Failed to unbind Shiny inputs/outputs: ${err}`,
      })
    }
  }

  showClientMessage(msg: ShinyClientMessage): void {
    document.dispatchEvent(
      new CustomEvent("shiny:client-message", {
        detail: {
          headline: msg.headline ?? "",
          message: msg.message,
          status: msg.status ?? "warning",
        },
      }),
    )
  }
}
