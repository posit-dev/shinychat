export const RESIZE_HANDLE_EVENTS = [
  "resize-request",
  "resize-start",
  "resize-end",
] as const

export type ResizeSource = "pointer" | "keyboard"
export type ResizeHandleEventName = (typeof RESIZE_HANDLE_EVENTS)[number]

export interface ResizeHandleOptions {
  value: number
  min: number
  max: number
  panelSide: "inline-start" | "inline-end"
  disabled: boolean
  label: string
  step?: number
  largeStep?: number
}

export interface ResizeRequestDetail {
  value: number
  source: ResizeSource
}

export interface ResizeLifecycleDetail {
  source: ResizeSource
}

export interface ResizeHandleElement extends HTMLElement {
  configure(options: ResizeHandleOptions): void
}

interface ResizeHandleConstructor extends CustomElementConstructor {
  readonly resizeHandleEvents?: readonly string[]
}

interface ResizeHandleRegistry {
  get(name: string): CustomElementConstructor | undefined
}

export interface ResizeHandleProvider {
  name: "local" | "bslib"
  tagName: "shiny-chat-resize-handle" | "bslib-resize-handle"
}

const LOCAL_TAG_NAME = "shiny-chat-resize-handle"
const BSLIB_TAG_NAME = "bslib-resize-handle"
const DEFAULT_OPTIONS: ResizeHandleOptions = {
  value: 0,
  min: 0,
  max: 0,
  panelSide: "inline-end",
  disabled: true,
  label: "Resize panel",
  step: 10,
  largeStep: 50,
}

function clamp(value: number, min: number, max: number): number {
  return Math.round(Math.min(Math.max(value, min), max))
}

function hasResizeHandleContract(
  constructor: CustomElementConstructor | undefined,
): constructor is ResizeHandleConstructor {
  if (!constructor) return false

  const candidate = constructor as ResizeHandleConstructor
  return (
    typeof candidate.prototype.configure === "function" &&
    RESIZE_HANDLE_EVENTS.every((event) =>
      candidate.resizeHandleEvents?.includes(event),
    )
  )
}

export function getResizeHandleProvider(
  registry: ResizeHandleRegistry = customElements,
): ResizeHandleProvider {
  return hasResizeHandleContract(registry.get(BSLIB_TAG_NAME))
    ? { name: "bslib", tagName: BSLIB_TAG_NAME }
    : { name: "local", tagName: LOCAL_TAG_NAME }
}

export function createResizeHandle(): ResizeHandleElement {
  const provider = getResizeHandleProvider()
  const handle = document.createElement(provider.tagName) as ResizeHandleElement
  handle.dataset.shinyChatResizeHandleProvider = provider.name
  return handle
}

class ShinyChatResizeHandleElement
  extends HTMLElement
  implements ResizeHandleElement
{
  static readonly resizeHandleEvents = RESIZE_HANDLE_EVENTS

  private options = DEFAULT_OPTIONS
  private listenerAbort: AbortController | null = null
  private pointer:
    | {
        id: number
        startX: number
        startValue: number
      }
    | undefined

  connectedCallback() {
    if (this.listenerAbort) return

    const controller = new AbortController()
    this.listenerAbort = controller
    const signal = { signal: controller.signal }
    this.addEventListener("pointerdown", this.onPointerDown, signal)
    this.addEventListener("pointermove", this.onPointerMove, signal)
    this.addEventListener("pointerup", this.onPointerEnd, signal)
    this.addEventListener("pointercancel", this.onPointerEnd, signal)
    this.addEventListener("lostpointercapture", this.onPointerEnd, signal)
    this.addEventListener("keydown", this.onKeyDown, signal)
  }

  disconnectedCallback() {
    this.finishPointer()
    this.listenerAbort?.abort()
    this.listenerAbort = null
  }

  configure(options: ResizeHandleOptions) {
    const min = Math.round(options.min)
    const max = Math.max(min, Math.round(options.max))
    this.options = {
      ...options,
      min,
      max,
      value: clamp(options.value, min, max),
      step: options.step ?? DEFAULT_OPTIONS.step,
      largeStep: options.largeStep ?? DEFAULT_OPTIONS.largeStep,
    }

    this.setAttribute("role", "separator")
    this.setAttribute("aria-orientation", "vertical")
    this.setAttribute("aria-label", this.options.label)
    this.setAttribute("aria-keyshortcuts", "ArrowLeft ArrowRight Home End")
    this.setAttribute("aria-valuemin", min.toString())
    this.setAttribute("aria-valuemax", max.toString())
    this.setAttribute("aria-valuenow", this.options.value.toString())
    this.setAttribute("aria-valuetext", `${this.options.value} pixels`)
    this.setAttribute("aria-disabled", this.options.disabled ? "true" : "false")
    this.tabIndex = this.options.disabled ? -1 : 0
    this.toggleAttribute("data-disabled", this.options.disabled)
    this.title = this.options.label

    if (this.options.disabled) this.finishPointer()
  }

  private readonly onPointerDown = (event: Event) => {
    const pointerEvent = event as PointerEvent
    if (
      this.options.disabled ||
      this.pointer ||
      pointerEvent.button !== 0 ||
      pointerEvent.isPrimary === false
    ) {
      return
    }

    pointerEvent.preventDefault()
    this.pointer = {
      id: pointerEvent.pointerId,
      startX: pointerEvent.clientX,
      startValue: this.options.value,
    }
    this.setPointerCapture?.(pointerEvent.pointerId)
    this.toggleAttribute("data-resizing", true)
    this.emit("resize-start", { source: "pointer" })
  }

  private readonly onPointerMove = (event: Event) => {
    const pointerEvent = event as PointerEvent
    const pointer = this.pointer
    if (!pointer || pointerEvent.pointerId !== pointer.id) return

    pointerEvent.preventDefault()
    const direction = window.getComputedStyle(
      this.parentElement ?? this,
    ).direction
    const horizontalDirection =
      (this.options.panelSide === "inline-end") === (direction !== "rtl")
        ? 1
        : -1
    const value =
      pointer.startValue +
      horizontalDirection * (pointerEvent.clientX - pointer.startX)
    this.request(value, "pointer")
  }

  private readonly onPointerEnd = (event: Event) => {
    const pointerEvent = event as PointerEvent
    if (this.pointer?.id !== pointerEvent.pointerId) return
    this.finishPointer()
  }

  private readonly onKeyDown = (event: Event) => {
    const keyEvent = event as KeyboardEvent
    if (this.options.disabled) return

    const step = keyEvent.shiftKey
      ? this.options.largeStep!
      : this.options.step!
    let value = this.options.value
    switch (keyEvent.key) {
      case "ArrowLeft":
        value -= step
        break
      case "ArrowRight":
        value += step
        break
      case "Home":
        value = this.options.min
        break
      case "End":
        value = this.options.max
        break
      default:
        return
    }

    keyEvent.preventDefault()
    this.emit("resize-start", { source: "keyboard" })
    this.request(value, "keyboard")
    this.emit("resize-end", { source: "keyboard" })
  }

  private request(value: number, source: ResizeSource) {
    const requested = clamp(value, this.options.min, this.options.max)
    this.options = { ...this.options, value: requested }
    this.setAttribute("aria-valuenow", requested.toString())
    this.setAttribute("aria-valuetext", `${requested} pixels`)
    this.emit("resize-request", { value: requested, source })
  }

  private finishPointer() {
    const pointer = this.pointer
    if (!pointer) return

    this.pointer = undefined
    if (this.hasPointerCapture?.(pointer.id)) {
      this.releasePointerCapture(pointer.id)
    }
    this.removeAttribute("data-resizing")
    this.emit("resize-end", { source: "pointer" })
  }

  private emit(
    type: ResizeHandleEventName,
    detail: ResizeRequestDetail | ResizeLifecycleDetail,
  ) {
    this.dispatchEvent(
      new CustomEvent(type, {
        bubbles: true,
        composed: true,
        detail,
      }),
    )
  }
}

if (!customElements.get(LOCAL_TAG_NAME)) {
  customElements.define(LOCAL_TAG_NAME, ShinyChatResizeHandleElement)
}
