import {
  isValidEnvelope,
  type ChatTransport,
  type ShinyLifecycle,
  type ChatAction,
  type ShinyClientMessage,
  type UserInputValue,
} from "./types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"
import type { SnapshotMessage } from "../chat/state"

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
  private inputSeq = 0

  constructor() {
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

        // Register deps with Shiny for immediate rendering, AND attach them to
        // the action so the reducer can retain them on the message (needed for
        // client-authoritative persistence/restore).
        if (html_deps && Array.isArray(html_deps)) {
          await this.renderDependencies(html_deps)
          if (
            action.type === "message" ||
            action.type === "chunk_start" ||
            action.type === "chunk"
          ) {
            ;(action as { html_deps?: HtmlDep[] }).html_deps = html_deps
          }
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

  sendInput(id: string, value: string | UserInputValue): void {
    if (!window.Shiny?.setInputValue) return
    const composite =
      typeof value === "string" ? { text: value, attachments: [] } : value
    this.inputSeq += 1
    // Regular priority so it co-batches with a same-tick messages snapshot.
    // The seq nonce bypasses client-side no-resend dedup so identical
    // resubmissions still fire the server-side reactive.
    window.Shiny.setInputValue(`${id}:shinychat.userInput`, {
      ...composite,
      seq: this.inputSeq,
    })
  }

  sendCancel(id: string): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(id, Date.now(), { priority: "event" })
  }

  sendSlashCommand(
    id: string,
    command: string,
    userText: string,
    echo: boolean,
  ): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(
      id,
      { command, userText, echo },
      { priority: "event" },
    )
  }

  sendMessagesSnapshot(id: string, snapshot: SnapshotMessage[]): void {
    if (!window.Shiny?.setInputValue) return
    // Regular priority (NOT event) so it co-batches in one flush with a
    // same-tick sendInput. See design doc "Ordering guarantee".
    window.Shiny.setInputValue(`${id}_messages:shinychat.messages`, snapshot)
  }

  sendHistorySelect(id: string, convId: string): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(
      `${id}_history_select`,
      { id: convId, ts: Date.now() },
      { priority: "event" },
    )
  }

  sendHistoryNew(id: string): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(`${id}_history_new`, Date.now(), {
      priority: "event",
    })
  }

  sendHistoryRename(id: string, convId: string, title: string): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(
      `${id}_history_rename`,
      { id: convId, title, ts: Date.now() },
      { priority: "event" },
    )
  }

  sendHistoryDelete(id: string, convId: string): void {
    if (!window.Shiny?.setInputValue) return
    window.Shiny.setInputValue(
      `${id}_history_delete`,
      { id: convId, ts: Date.now() },
      { priority: "event" },
    )
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
