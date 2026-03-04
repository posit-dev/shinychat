import type {
  ChatTransport,
  ChatAction,
  ShinyChatEnvelope,
  ShinyClientMessage,
} from "./types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

export class ShinyTransport implements ChatTransport {
  private listeners = new Map<string, Set<(action: ChatAction) => void>>()

  constructor() {
    window.Shiny?.addCustomMessageHandler(
      "shinyChatMessage",
      async (envelope: ShinyChatEnvelope) => {
        const { id, action } = envelope

        // Render HTML deps before dispatching
        if ("message" in action && action.message?.html_deps) {
          await this.renderDependencies(action.message.html_deps)
        }

        const callbacks = this.listeners.get(id)
        if (!callbacks || callbacks.size === 0) {
          this.showClientMessage({
            status: "error",
            message: `Unable to handle Chat() message since no listener registered for id "${id}".`,
          })
          return
        }

        for (const cb of callbacks) {
          cb(action)
        }
      },
    )
  }

  sendInput(id: string, value: string): void {
    window.Shiny.setInputValue!(id, value, { priority: "event" })
  }

  onMessage(
    id: string,
    callback: (action: ChatAction) => void,
  ): () => void {
    if (!this.listeners.has(id)) {
      this.listeners.set(id, new Set())
    }
    this.listeners.get(id)!.add(callback)

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
