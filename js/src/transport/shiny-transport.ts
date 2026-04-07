import {
  isValidEnvelope,
  type ChatTransport,
  type ShinyLifecycle,
  type ChatAction,
  type ShinyClientMessage,
} from "./types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

// Window-global singleton to ensure only one shinyChatMessage handler is
// registered even if the script is loaded more than once
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
      "shinyChatBookmarkSave",
      (data: { id: string; key: string }) => {
        const callbacks = this.listeners.get(data.id)
        if (!callbacks) return
        for (const cb of callbacks) {
          cb({ type: "_bookmark_save", key: data.key } as never)
        }
      },
    )

    window.Shiny?.addCustomMessageHandler(
      "shinyChatMessage",
      async (envelope: unknown) => {
        if (!isValidEnvelope(envelope)) {
          console.warn(
            "[shinychat] Malformed shinyChatMessage envelope, dropping:",
            JSON.stringify(envelope),
          )
          return
        }

        const { id, action, html_deps } = envelope

        // Render HTML deps before dispatching the action
        if (html_deps && Array.isArray(html_deps)) {
          await this.renderDependencies(html_deps)
        }

        const callbacks = this.listeners.get(id)
        if (!callbacks || callbacks.size === 0) {
          if (!this.pendingMessages.has(id)) {
            this.pendingMessages.set(id, [])
          }
          this.pendingMessages.get(id)!.push(action)
          return
        }

        for (const cb of callbacks) {
          cb(action)
        }
      },
    )
  }

  sendInput(id: string, value: unknown): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(id, value, { priority: "event" })
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
