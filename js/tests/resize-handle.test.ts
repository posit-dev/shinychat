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

  it.each([
    ["LTR inline-end", "ltr", "inline-end", 310],
    ["LTR inline-start", "ltr", "inline-start", 290],
    ["RTL inline-end", "rtl", "inline-end", 290],
    ["RTL inline-start", "rtl", "inline-start", 310],
  ] as const)(
    "matches pointer direction for %s",
    (_name, direction, panelSide, expectedValue) => {
      document.body.style.direction = direction
      const handle = configuredHandle({ panelSide })
      const requests: number[] = []
      handle.addEventListener("resize-request", (event) => {
        requests.push((event as CustomEvent<{ value: number }>).detail.value)
      })

      handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }))
      handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }))

      expect(requests).toEqual([expectedValue, 300])
    },
  )

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

  it("installs non-passive touch movement handling only during a touch resize", () => {
    const addEventListener = vi.spyOn(document, "addEventListener")
    const handle = configuredHandle({ boundaryActivation: true })
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 26, 400),
    })

    expect(addEventListener).not.toHaveBeenCalledWith(
      "touchmove",
      expect.any(Function),
      expect.anything(),
    )

    document.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
        pointerType: "touch",
        clientX: 320,
        clientY: 300,
      }),
    )

    expect(addEventListener).toHaveBeenCalledWith(
      "touchmove",
      expect.any(Function),
      expect.objectContaining({ passive: false }),
    )
    handle.dispatchEvent(
      new PointerEvent("pointerup", { bubbles: true, pointerId: 1 }),
    )
    addEventListener.mockRestore()
  })

  it("arms fine pointers near the configured pane boundary from either side", () => {
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
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 307 }))
    expect(handle).not.toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 318 }))
    expect(handle).toHaveAttribute("data-boundary-armed")
    handle.remove()
    expect(handle).not.toHaveAttribute("data-boundary-armed")
    document.body.append(handle)
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

  it("keeps the shared 24-pixel active target after a five-pixel boundary trip", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 8, 400),
    })

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 317, clientY: 300 }),
    )
    expect(handle).not.toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 318, clientY: 300 }),
    )
    expect(handle).toHaveAttribute("data-boundary-armed")

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 308, clientY: 300 }),
    )
    expect(handle).toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 307, clientY: 300 }),
    )
    expect(handle).not.toHaveAttribute("data-boundary-armed")
  })

  it("arms when a fine pointer jumps across the LTR activation zone", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 8, 400),
    })

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 317, clientY: 300 }),
    )
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 323, clientY: 300 }),
    )

    expect(handle).toHaveAttribute("data-boundary-armed")
  })

  it("arms when a fine pointer jumps across the RTL activation zone", () => {
    const handle = configuredHandle({
      panelSide: "inline-start",
      boundaryActivation: true,
    })
    document.body.style.direction = "rtl"
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(320, 100, 8, 400),
    })

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 325, clientY: 300 }),
    )
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 331, clientY: 300 }),
    )

    expect(handle).toHaveAttribute("data-boundary-armed")
  })

  it("does not arm when a fine pointer stays outside the activation zone", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 8, 400),
    })

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 313, clientY: 300 }),
    )
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 317, clientY: 300 }),
    )

    expect(handle).not.toHaveAttribute("data-boundary-armed")
  })

  it("reseeds boundary tracking after a disabled transition", () => {
    const options = {
      value: 300,
      min: 150,
      max: 640,
      panelSide: "inline-end" as const,
      label: "Resize sidebar",
      boundaryActivation: true,
    }
    const handle = configuredHandle(options)
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 8, 400),
    })

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 317, clientY: 300 }),
    )
    handle.configure({ ...options, disabled: true })
    handle.configure({ ...options, disabled: false })
    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 323, clientY: 300 }),
    )

    expect(handle).not.toHaveAttribute("data-boundary-armed")

    document.dispatchEvent(
      new PointerEvent("pointermove", { clientX: 317, clientY: 300 }),
    )
    expect(handle).toHaveAttribute("data-boundary-armed")
  })

  it("allows direct grabs from a boundary indicator before arming", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    const indicator = handle.querySelector(
      ":scope > [data-shiny-chat-resize-indicator]",
    )
    const starts = vi.fn()
    handle.addEventListener("resize-start", starts)

    indicator!.dispatchEvent(
      new PointerEvent("pointerdown", {
        bubbles: true,
        button: 0,
        isPrimary: true,
        pointerId: 1,
      }),
    )

    expect(starts).toHaveBeenCalledTimes(1)
    expect(handle).toHaveAttribute("data-boundary-armed")
    expect(handle).toHaveAttribute("data-panel-side", "inline-end")
  })

  it("tracks boundary activation before nested controls can stop propagation", () => {
    const handle = configuredHandle({ boundaryActivation: true })
    const control = document.createElement("button")
    control.addEventListener("pointermove", (event) => event.stopPropagation())
    handle.append(control)
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(312, 100, 8, 400),
    })

    control.dispatchEvent(
      new PointerEvent("pointermove", {
        bubbles: true,
        clientX: 318,
        clientY: 300,
      }),
    )

    expect(handle).toHaveAttribute("data-boundary-armed")
  })

  it("uses the mirrored boundary in RTL and allows coarse pointers", () => {
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

    document.body.style.direction = "rtl"
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 330 }))
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 327 }))
    expect(handle).toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 315 }))
    expect(handle).not.toHaveAttribute("data-boundary-armed")
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 322 }))
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 327 }))
    expect(handle).toHaveAttribute("data-boundary-armed")

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

  it("can start another fine-pointer drag after a maximum-width resize", () => {
    const handle = configuredHandle({
      value: 400,
      min: 240,
      max: 840,
      panelSide: "inline-start",
      boundaryActivation: true,
    })
    const requests: number[] = []
    handle.addEventListener("resize-request", (event) => {
      requests.push((event as CustomEvent<{ value: number }>).detail.value)
    })
    let left = 700
    Object.defineProperty(handle, "getBoundingClientRect", {
      configurable: true,
      value: () => new DOMRect(left, 0, 8, 400),
    })

    const arm = () => {
      document.dispatchEvent(
        new PointerEvent("pointermove", { clientX: left - 1 }),
      )
      document.dispatchEvent(
        new PointerEvent("pointermove", { clientX: left + 1 }),
      )
      expect(handle).toHaveAttribute("data-boundary-armed")
    }
    const drag = (pointerId: number, endX: number) => {
      handle.dispatchEvent(
        new PointerEvent("pointerdown", {
          bubbles: true,
          button: 0,
          isPrimary: true,
          pointerId,
          clientX: left + 1,
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
        new PointerEvent("pointerup", { bubbles: true, pointerId }),
      )
    }

    arm()
    drag(1, left - 1000)
    expect(requests).toEqual([840])
    expect(handle).not.toHaveAttribute("data-boundary-armed")

    // The panel's inline-start edge moves when its width reaches the clamp.
    left = 260
    arm()
    drag(2, left + 101)
    expect(requests).toEqual([840, 740])
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
    expect(
      getResizeHandleProvider(registry, { boundaryActivation: true }),
    ).toEqual({
      name: "local",
      tagName: "shiny-chat-resize-handle",
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
