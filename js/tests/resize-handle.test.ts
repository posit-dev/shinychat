import { afterEach, describe, expect, it, vi } from "vitest"
import {
  RESIZE_HANDLE_EVENTS,
  createResizeHandle,
  getResizeHandleProvider,
  type ResizeHandleElement,
} from "../src/resize-handle"

function configuredHandle(
  options: Partial<Parameters<ResizeHandleElement["configure"]>[0]> = {},
) {
  const handle = createResizeHandle()
  handle.configure({
    value: 300,
    min: 150,
    max: 640,
    panelSide: "inline-end",
    disabled: false,
    label: "Resize sidebar",
    ...options,
  })
  document.body.append(handle)
  return handle
}

afterEach(() => {
  document.body.replaceChildren()
  document.body.style.removeProperty("direction")
})

describe("shiny-chat-resize-handle", () => {
  it("clamps pointer requests and rejects non-primary pointers", () => {
    const handle = configuredHandle()
    const requests: unknown[] = []
    const starts = vi.fn()
    const ends = vi.fn()
    handle.addEventListener("resize-request", (event) =>
      requests.push((event as CustomEvent).detail),
    )
    handle.addEventListener("resize-start", starts)
    handle.addEventListener("resize-end", ends)

    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 2,
        isPrimary: true,
        pointerId: 1,
        clientX: 300,
      }),
    )
    handle.dispatchEvent(
      new PointerEvent("pointermove", {
        bubbles: true,
        pointerId: 1,
        clientX: 640,
      }),
    )
    expect(requests).toEqual([])

    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 2,
        clientX: 300,
      }),
    )
    handle.dispatchEvent(
      new PointerEvent("pointermove", {
        bubbles: true,
        pointerId: 2,
        clientX: 1000,
      }),
    )
    handle.dispatchEvent(
      new PointerEvent("lostpointercapture", {
        bubbles: true,
        pointerId: 2,
      }),
    )

    expect(starts).toHaveBeenCalledTimes(1)
    expect(ends).toHaveBeenCalledTimes(1)
    expect(requests).toEqual([{ value: 640, source: "pointer" }])
    expect(handle).not.toHaveAttribute("data-resizing")
  })

  it("uses logical panel sides in LTR and RTL", () => {
    const handle = configuredHandle({ panelSide: "inline-start" })
    document.body.style.direction = "ltr"
    const requests: number[] = []
    handle.addEventListener("resize-request", (event) => {
      requests.push((event as CustomEvent<{ value: number }>).detail.value)
    })

    const drag = (pointerId: number, startX: number, endX: number) => {
      handle.dispatchEvent(
        new PointerEvent("pointerdown", {
          bubbles: true,
          button: 0,
          isPrimary: true,
          pointerId,
          clientX: startX,
        }),
      )
      handle.dispatchEvent(
        new PointerEvent("pointermove", {
          bubbles: true,
          pointerId,
          clientX: endX,
        }),
      )
      handle.dispatchEvent(
        new PointerEvent("pointerup", {
          bubbles: true,
          pointerId,
        }),
      )
    }

    drag(1, 300, 260)
    document.body.style.direction = "rtl"
    handle.configure({
      value: 300,
      min: 150,
      max: 640,
      panelSide: "inline-start",
      disabled: false,
      label: "Resize artifact panel",
    })
    drag(2, 300, 340)

    expect(requests).toEqual([340, 340])
  })

  it("supports keyboard requests, ARIA updates, disablement, and reconnecting", () => {
    const handle = configuredHandle()
    const events: Array<{ type: string; detail: unknown }> = []
    RESIZE_HANDLE_EVENTS.forEach((type) =>
      handle.addEventListener(type, (event) =>
        events.push({ type, detail: (event as CustomEvent).detail }),
      ),
    )

    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }))
    handle.dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", shiftKey: true }),
    )
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "Home" }))
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "End" }))

    expect(handle).toHaveAttribute("aria-valuemin", "150")
    expect(handle).toHaveAttribute("aria-valuemax", "640")
    expect(handle).toHaveAttribute("aria-valuenow", "640")
    expect(handle).toHaveAttribute("aria-valuetext", "640 pixels")
    expect(handle).toHaveAttribute(
      "aria-keyshortcuts",
      "ArrowLeft ArrowRight Home End",
    )
    expect(events.filter((event) => event.type === "resize-request")).toEqual([
      { type: "resize-request", detail: { value: 310, source: "keyboard" } },
      { type: "resize-request", detail: { value: 360, source: "keyboard" } },
      { type: "resize-request", detail: { value: 150, source: "keyboard" } },
      { type: "resize-request", detail: { value: 640, source: "keyboard" } },
    ])

    handle.configure({
      value: 640,
      min: 150,
      max: 640,
      panelSide: "inline-end",
      disabled: true,
      label: "Resize sidebar",
    })
    expect(handle.tabIndex).toBe(-1)
    expect(handle).toHaveAttribute("aria-disabled", "true")
    handle.remove()
    document.body.append(handle)
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }))
    expect(handle).toHaveAttribute("aria-valuenow", "640")
  })

  it("ends a pointer interaction exactly once on cancellation and disconnect", () => {
    const handle = configuredHandle()
    const ends = vi.fn()
    handle.addEventListener("resize-end", ends)

    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
      }),
    )
    handle.dispatchEvent(
      new PointerEvent("pointercancel", {
        bubbles: true,
        pointerId: 1,
      }),
    )
    handle.remove()
    expect(ends).toHaveBeenCalledTimes(1)

    document.body.append(handle)
    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 2,
      }),
    )
    handle.remove()
    expect(ends).toHaveBeenCalledTimes(2)
  })

  it("arms fine pointers only after crossing into the configured pane boundary", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    const starts = vi.fn()
    handle.addEventListener("resize-start", starts)
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 0, 8, 400),
    })

    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
        clientX: 320,
      }),
    )
    expect(starts).not.toHaveBeenCalled()

    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 324 }))
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 319 }))
    expect(handle).toHaveAttribute("data-boundary-armed")
    handle.remove()
    expect(handle).not.toHaveAttribute("data-boundary-armed")
    document.body.append(handle)
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 324 }))
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 319 }))
    expect(handle).toHaveAttribute("data-boundary-armed")

    handle.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 2,
        clientX: 319,
      }),
    )
    expect(starts).toHaveBeenCalledTimes(1)

    handle.dispatchEvent(
      new PointerEvent("pointerup", { bubbles: true, pointerId: 2 }),
    )
    expect(handle).not.toHaveAttribute("data-boundary-armed")
  })

  it("uses the opposite crossing direction for inline-end and allows coarse pointers", () => {
    const handle = configuredHandle({
      panelSide: "inline-start",
      boundaryActivation: true,
    })
    const starts = vi.fn()
    handle.addEventListener("resize-start", starts)
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(320, 0, 8, 400),
    })

    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 316 }))
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 321 }))
    expect(handle).toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 329 }))
    expect(handle).not.toHaveAttribute("data-boundary-armed")

    document.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: false,
        pointerId: 1,
        pointerType: "touch",
        clientX: 324,
        clientY: 200,
      }),
    )
    expect(starts).not.toHaveBeenCalled()

    document.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
        pointerType: "touch",
        clientX: 324,
        clientY: 500,
      }),
    )
    expect(starts).not.toHaveBeenCalled()

    document.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
        pointerType: "touch",
        clientX: 324,
        clientY: 200,
      }),
    )
    expect(starts).toHaveBeenCalledTimes(1)
  })

  it("uses bslib only when the complete public contract is available", () => {
    class ConformingBslibHandle extends HTMLElement {
      static readonly resizeHandleEvents = RESIZE_HANDLE_EVENTS

      configure() {}
    }
    class IncompleteBslibHandle extends HTMLElement {
      configure() {}
    }
    let registered: CustomElementConstructor | undefined = ConformingBslibHandle
    const registry = {
      get: vi.fn(() => registered),
    }
    expect(getResizeHandleProvider(registry)).toEqual({
      name: "bslib",
      tagName: "bslib-resize-handle",
    })
    expect(createResizeHandle({ boundaryActivation: true }).tagName).toBe(
      "SHINY-CHAT-RESIZE-HANDLE",
    )

    registered = IncompleteBslibHandle
    expect(getResizeHandleProvider(registry)).toEqual({
      name: "local",
      tagName: "shiny-chat-resize-handle",
    })
  })
})
