import { createRef } from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChatDrawer } from "../../src/chat/ChatDrawer"
import { ChatApp } from "../../src/chat/ChatApp"
import { ShinyLifecycleContext } from "../../src/chat/context"
import { initialState, type ChatDrawerState } from "../../src/chat/state"
import { RESIZE_HANDLE_EVENTS } from "../../src/resize-handle"
import type { ShinyLifecycle } from "../../src/transport/types"
import { createMockShinyLifecycle, createMockTransport } from "../helpers/mocks"

class ResizeObserverStub {
  static instances: ResizeObserverStub[] = []
  private targets = new Set<Element>()

  constructor(private callback: ResizeObserverCallback) {
    ResizeObserverStub.instances.push(this)
  }

  observe = (target: Element) => {
    this.targets.add(target)
  }

  unobserve = (target: Element) => {
    this.targets.delete(target)
  }

  disconnect = () => {
    this.targets.clear()
  }

  static resize(target: Element, width: number) {
    for (const observer of ResizeObserverStub.instances) {
      if (!observer.targets.has(target)) continue
      observer.callback(
        [{ target, contentRect: { width } } as unknown as ResizeObserverEntry],
        observer as unknown as ResizeObserver,
      )
    }
  }

  static reset() {
    ResizeObserverStub.instances = []
  }
}

function drawer(overrides: Partial<ChatDrawerState> = {}): ChatDrawerState {
  return {
    ...initialState.drawer,
    enabled: true,
    visible: true,
    content: "<p>Initial</p>",
    ...overrides,
  }
}

function lifecycle(): ShinyLifecycle {
  return {
    renderDependencies: vi.fn(async () => {}),
    bindAll: vi.fn(async () => {}),
    unbindAll: vi.fn(),
    showClientMessage: vi.fn(),
  }
}

function renderDrawer(
  currentDrawer: ChatDrawerState,
  options: {
    source?: Element
    shiny?: ShinyLifecycle
    takeover?: boolean
    onClose?: () => void
    onWidthChange?: (width: string) => void
    onResizeStateChange?: (resizing: boolean) => void
  } = {},
) {
  const closeButtonRef = createRef<HTMLButtonElement>()
  const shiny = options.shiny ?? lifecycle()
  const onClose = options.onClose ?? vi.fn()
  const onWidthChange = options.onWidthChange ?? vi.fn()
  const view = render(
    <ShinyLifecycleContext.Provider value={shiny}>
      <ChatDrawer
        drawer={currentDrawer}
        source={options.source}
        titleId="drawer-title"
        takeover={options.takeover ?? false}
        closeButtonRef={closeButtonRef}
        onClose={onClose}
        onWidthChange={onWidthChange}
        onResizeStateChange={options.onResizeStateChange}
      />
    </ShinyLifecycleContext.Provider>,
  )
  return { ...view, closeButtonRef, shiny, onClose, onWidthChange }
}

function armDrawerResizer(
  separator: HTMLElement,
  direction: "ltr" | "rtl" = "ltr",
) {
  Object.defineProperty(separator, "getBoundingClientRect", {
    configurable: true,
    value: () => new DOMRect(100, 0, 8, 400),
  })
  if (direction === "rtl") {
    fireEvent.pointerMove(document, { clientX: 109 })
    fireEvent.pointerMove(document, { clientX: 107 })
  } else {
    fireEvent.pointerMove(document, { clientX: 99 })
    fireEvent.pointerMove(document, { clientX: 101 })
  }
  expect(separator).toHaveAttribute("data-boundary-armed")
}

describe("ChatDrawer", () => {
  it("retains a closing drawer until its consumer motion completes", () => {
    vi.useFakeTimers()
    try {
      const shiny = lifecycle()
      const { rerender } = renderDrawer(drawer(), { shiny })
      const panel = screen.getByRole("complementary")

      rerender(
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatDrawer
            drawer={drawer({ visible: false })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={vi.fn()}
          />
        </ShinyLifecycleContext.Provider>,
      )

      expect(panel.hidden).toBe(false)
      expect(panel).toHaveAttribute("data-motion", "closing")
      expect(panel).toHaveAttribute("aria-hidden", "true")

      act(() => vi.advanceTimersByTime(180))
      expect(panel.hidden).toBe(true)
      expect(panel).toHaveAttribute("data-motion", "closed")
    } finally {
      vi.useRealTimers()
    }
  })

  it("reports resize activity to its layout consumer", async () => {
    const onResizeStateChange = vi.fn()
    renderDrawer(drawer(), { onResizeStateChange })

    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })
    fireEvent(
      separator,
      new CustomEvent("resize-start", { bubbles: true, composed: true }),
    )
    await waitFor(() =>
      expect(onResizeStateChange).toHaveBeenLastCalledWith(true),
    )

    fireEvent(
      separator,
      new CustomEvent("resize-end", { bubbles: true, composed: true }),
    )
    await waitFor(() =>
      expect(onResizeStateChange).toHaveBeenLastCalledWith(false),
    )
  })

  it("clears resize state when an active drawer starts closing", async () => {
    const onResizeStateChange = vi.fn()
    const shiny = lifecycle()
    const { rerender } = renderDrawer(drawer(), {
      shiny,
      onResizeStateChange,
    })
    const panel = screen.getByRole("complementary")
    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })

    fireEvent(
      separator,
      new CustomEvent("resize-start", { bubbles: true, composed: true }),
    )
    await waitFor(() =>
      expect(onResizeStateChange).toHaveBeenLastCalledWith(true),
    )
    expect(panel).toHaveAttribute("data-drawer-resizing")

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatDrawer
          drawer={drawer({ visible: false })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={vi.fn()}
          onResizeStateChange={onResizeStateChange}
        />
      </ShinyLifecycleContext.Provider>,
    )

    await waitFor(() => {
      expect(panel).not.toHaveAttribute("data-drawer-resizing")
      expect(onResizeStateChange).toHaveBeenLastCalledWith(false)
    })
  })

  it("adopts preserved initial DOM content while hidden", async () => {
    const source = document.createElement("shiny-chat-drawer")
    const initialChild = document.createElement("input")
    initialChild.value = "preserved"
    source.append(initialChild)
    const initialMarkup = source.innerHTML

    const { rerender, shiny } = renderDrawer(
      drawer({ visible: false, content: initialMarkup }),
      { source },
    )

    await waitFor(() => {
      expect(
        screen.getByRole("complementary", { hidden: true }),
      ).toHaveAttribute("hidden")
      expect(screen.getByDisplayValue("preserved")).toBe(initialChild)
    })

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatDrawer
          drawer={drawer({ visible: true, content: initialMarkup })}
          source={source}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={vi.fn()}
        />
      </ShinyLifecycleContext.Provider>,
    )

    await waitFor(() => {
      expect(screen.getByRole("complementary")).toContainElement(initialChild)
    })
  })

  it("replaces dynamic content in lifecycle order", async () => {
    const calls: string[] = []
    let resolveSecondDependencies!: () => void
    const shiny: ShinyLifecycle = {
      unbindAll: vi.fn(() => calls.push("unbind")),
      renderDependencies: vi.fn(async (deps) => {
        calls.push("deps")
        if (deps[0]?.name === "second") {
          await new Promise<void>((resolve) => {
            resolveSecondDependencies = resolve
          })
        }
      }),
      bindAll: vi.fn(async () => {
        calls.push("bind")
      }),
      showClientMessage: vi.fn(),
    }
    const first = drawer({
      content: "<p>First</p>",
      htmlDeps: [{ name: "first", version: "1.0.0" }],
    })
    const { rerender } = renderDrawer(first, { shiny })

    await waitFor(() => expect(calls).toEqual(["deps", "bind"]))
    calls.length = 0

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatDrawer
          drawer={drawer({
            content: "<p>Second</p>",
            htmlDeps: [{ name: "second", version: "1.0.0" }],
          })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={vi.fn()}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(calls).toEqual(["unbind", "deps"])
    expect(screen.queryByText("First")).toBeNull()
    expect(screen.queryByText("Second")).toBeNull()

    await act(async () => {
      resolveSecondDependencies()
    })

    await waitFor(() => expect(calls).toEqual(["unbind", "deps", "bind"]))
    expect(screen.getByText("Second")).toBeInTheDocument()
  })

  it("unbinds the current in-flight bind after unmount", async () => {
    let resolveBind!: () => void
    const shiny: ShinyLifecycle = {
      unbindAll: vi.fn(),
      renderDependencies: vi.fn(async () => {}),
      bindAll: vi.fn(
        () =>
          new Promise<void>((resolve) => {
            resolveBind = resolve
          }),
      ),
      showClientMessage: vi.fn(),
    }
    const { unmount } = renderDrawer(drawer(), { shiny })

    await waitFor(() => expect(shiny.bindAll).toHaveBeenCalledTimes(1))
    unmount()
    expect(shiny.unbindAll).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveBind()
    })

    await waitFor(() => expect(shiny.unbindAll).toHaveBeenCalledTimes(2))
  })

  it("ignores stale bind completion after a newer replacement binds", async () => {
    const resolvers: (() => void)[] = []
    const bindings = new Map<string, Set<HTMLElement>>()
    const idsFor = (element: HTMLElement) =>
      Array.from(element.querySelectorAll<HTMLElement>("[id]")).map(
        (child) => child.id,
      )
    const shiny: ShinyLifecycle = {
      unbindAll: vi.fn((element: HTMLElement) => {
        for (const [id, owners] of bindings) {
          owners.delete(element)
          if (owners.size === 0) bindings.delete(id)
        }
      }),
      renderDependencies: vi.fn(async () => {}),
      bindAll: vi.fn(
        (element: HTMLElement) =>
          new Promise<void>((resolve) => {
            resolvers.push(() => {
              for (const id of idsFor(element)) {
                const owners = bindings.get(id) ?? new Set<HTMLElement>()
                owners.add(element)
                bindings.set(id, owners)
              }
              resolve()
            })
          }),
      ),
      showClientMessage: vi.fn(),
    }
    const first = drawer({ content: '<input id="shared-input">' })
    const { rerender, unmount } = renderDrawer(first, { shiny })

    await waitFor(() => expect(shiny.bindAll).toHaveBeenCalledTimes(1))
    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatDrawer
          drawer={drawer({
            content: '<div><input id="shared-input"></div>',
          })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={vi.fn()}
        />
      </ShinyLifecycleContext.Provider>,
    )

    await waitFor(() => expect(shiny.bindAll).toHaveBeenCalledTimes(2))
    const firstWrapper = (shiny.bindAll as ReturnType<typeof vi.fn>).mock
      .calls[0]![0] as HTMLElement
    const secondWrapper = (shiny.bindAll as ReturnType<typeof vi.fn>).mock
      .calls[1]![0] as HTMLElement
    expect(shiny.unbindAll).toHaveBeenLastCalledWith(firstWrapper)

    await act(async () => {
      resolvers[1]!()
    })
    expect([...bindings.keys()]).toEqual(["shared-input"])

    await act(async () => {
      resolvers[0]!()
    })

    expect([...bindings.keys()]).toEqual(["shared-input"])
    expect(shiny.unbindAll).toHaveBeenLastCalledWith(firstWrapper)

    unmount()
    expect(shiny.unbindAll).toHaveBeenLastCalledWith(secondWrapper)
    expect(bindings.size).toBe(0)
  })

  it("exposes a bounded keyboard and pointer resize separator", async () => {
    const shell = document.createElement("shiny-chat-container")
    Object.defineProperty(shell, "getBoundingClientRect", {
      value: () => ({ width: 1200 }),
    })
    document.body.append(shell)
    const onWidthChange = vi.fn()

    const closeButtonRef = createRef<HTMLButtonElement>()
    const shiny = lifecycle()
    render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatDrawer
          drawer={drawer({ width: "400px" })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={closeButtonRef}
          onClose={vi.fn()}
          onWidthChange={onWidthChange}
        />
      </ShinyLifecycleContext.Provider>,
      { container: shell },
    )

    const panel = screen.getByRole("complementary")
    Object.defineProperty(panel, "getBoundingClientRect", {
      value: () => ({ width: 400 }),
    })
    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })
    expect(separator).toHaveAttribute("aria-valuemin", "240")
    expect(separator).toHaveAttribute("aria-valuemax", "816")

    fireEvent.keyDown(separator, { key: "ArrowRight" })
    expect(onWidthChange).toHaveBeenLastCalledWith("390px")

    armDrawerResizer(separator)
    fireEvent.pointerDown(separator, {
      button: 0,
      isPrimary: true,
      pointerId: 1,
      clientX: 100,
    })
    fireEvent.pointerMove(separator, {
      isPrimary: true,
      pointerId: 1,
      clientX: 60,
    })
    expect(onWidthChange).toHaveBeenLastCalledWith("430px")
    fireEvent.pointerUp(separator, { isPrimary: true, pointerId: 1 })
    expect(screen.getByRole("complementary")).not.toHaveAttribute(
      "data-drawer-resizing",
    )
  })

  it("preserves non-pixel widths until the user resizes the drawer", async () => {
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    const shell = document.createElement("shiny-chat-container")
    Object.defineProperty(shell, "getBoundingClientRect", {
      value: () => ({ width: 1200 }),
    })
    document.body.append(shell)
    const panelWidth = 512
    const onWidthChange = vi.fn()

    render(
      <ShinyLifecycleContext.Provider value={lifecycle()}>
        <ChatDrawer
          drawer={drawer({ width: "32rem" })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={onWidthChange}
        />
      </ShinyLifecycleContext.Provider>,
      { container: shell },
    )

    const panel = screen.getByRole("complementary")
    Object.defineProperty(panel, "getBoundingClientRect", {
      value: () => ({ width: panelWidth }),
    })
    expect(panel.style.getPropertyValue("--_drawer-width")).toBe(
      "32rem",
    )
    expect(onWidthChange).not.toHaveBeenCalled()

    await act(async () => {
      ResizeObserverStub.resize(shell, 1200)
    })

    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })
    armDrawerResizer(separator)
    fireEvent.pointerDown(separator, {
      button: 0,
      isPrimary: true,
      pointerId: 1,
      clientX: 100,
    })
    fireEvent.pointerMove(separator, {
      isPrimary: true,
      pointerId: 1,
      clientX: 60,
    })

    expect(onWidthChange).toHaveBeenLastCalledWith("552px")
    expect(panel.style.getPropertyValue("--_drawer-width")).toBe(
      "552px",
    )
  })

  it("bounds a non-pixel layout width before configuring its first separator", async () => {
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    const shell = document.createElement("shiny-chat-container")
    const layout = document.createElement("div")
    layout.className = "shiny-chat-layout"
    shell.append(layout)
    document.body.append(shell)
    Object.defineProperty(shell, "getBoundingClientRect", {
      value: () => ({ width: 1000 }),
    })
    const onWidthChange = vi.fn()

    render(
      <ShinyLifecycleContext.Provider value={lifecycle()}>
        <ChatDrawer
          drawer={drawer({ width: "100%" })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={onWidthChange}
        />
      </ShinyLifecycleContext.Provider>,
      { container: layout },
    )

    const panel = screen.getByRole("complementary")
    Object.defineProperty(panel, "getBoundingClientRect", {
      value: () => ({ width: 1000 }),
    })
    await act(async () => {
      ResizeObserverStub.resize(shell, 1000)
    })

    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })
    expect(panel.style.getPropertyValue("--_drawer-width")).toBe(
      "616px",
    )
    expect(separator).toHaveAttribute("aria-valuenow", "616")
    expect(separator).toHaveAttribute("aria-valuemax", "616")
    expect(onWidthChange).toHaveBeenLastCalledWith("616px")
  })

  it("bounds an oversized percentage grid track without applying it twice", async () => {
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    const shell = document.createElement("shiny-chat-container")
    const layout = document.createElement("div")
    layout.className = "shiny-chat-layout"
    shell.append(layout)
    document.body.append(shell)
    Object.defineProperty(shell, "getBoundingClientRect", {
      value: () => ({ width: 1000 }),
    })
    const onWidthChange = vi.fn()

    render(
      <ShinyLifecycleContext.Provider value={lifecycle()}>
        <ChatDrawer
          drawer={drawer({ width: "70%" })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={onWidthChange}
        />
      </ShinyLifecycleContext.Provider>,
      { container: layout },
    )

    const panel = screen.getByRole("complementary")
    Object.defineProperty(panel, "getBoundingClientRect", {
      value: () => ({ width: 700 }),
    })
    await act(async () => {
      ResizeObserverStub.resize(shell, 1000)
    })

    expect(onWidthChange).toHaveBeenLastCalledWith("616px")
    expect(panel.style.getPropertyValue("--_drawer-width")).toBe(
      "616px",
    )
  })

  it("resolves auto drawer widths to a pixel layout target before reveal", async () => {
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: 1440 }
        }
        return { width: 0 }
      },
    })

    try {
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-auto-width"
          inputId="drawer-auto-width-input"
          initialDrawer={drawer({
            visible: false,
            width: "auto",
            content: "<p>Ready</p>",
          })}
        />,
      )
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      expect(layout.style.getPropertyValue("--_drawer-width")).toBe(
        "400px",
      )
    } finally {
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("clamps percentage drawer layout targets before desktop reveal", async () => {
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: 1440 }
        }
        return { width: 0 }
      },
    })

    try {
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-percent-width"
          inputId="drawer-percent-width-input"
          initialDrawer={drawer({
            visible: false,
            width: "90%",
            content: "<p>Ready</p>",
          })}
        />,
      )
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      expect(layout.style.getPropertyValue("--_drawer-width")).toBe(
        "1056px",
      )
    } finally {
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("refreshes a relative drawer target when its persistent probe changes", async () => {
    let relativeWidth = 512
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: 1440 }
        }
        if (this.classList.contains("shiny-chat-drawer-width-probe")) {
          return { width: relativeWidth }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    try {
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-relative-width"
          inputId="drawer-relative-width-input"
          initialDrawer={drawer({
            visible: false,
            width: "32rem",
            content: "<p>Ready</p>",
          })}
        />,
      )
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement
      const probe = view.container.querySelector(
        ".shiny-chat-drawer-width-probe",
      ) as HTMLElement

      expect(layout.style.getPropertyValue("--_drawer-width")).toBe(
        "512px",
      )

      relativeWidth = 640
      await act(async () => {
        ResizeObserverStub.resize(probe, relativeWidth)
      })

      expect(layout.style.getPropertyValue("--_drawer-width")).toBe(
        "640px",
      )
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("resizes from the logical inline-start edge in RTL", () => {
    const shell = document.createElement("shiny-chat-container")
    Object.defineProperty(shell, "getBoundingClientRect", {
      value: () => ({ width: 1200 }),
    })
    document.body.append(shell)
    const onWidthChange = vi.fn()

    render(
      <ShinyLifecycleContext.Provider value={lifecycle()}>
        <ChatDrawer
          drawer={drawer({ width: "400px" })}
          titleId="drawer-title"
          takeover={false}
          closeButtonRef={createRef<HTMLButtonElement>()}
          onClose={vi.fn()}
          onWidthChange={onWidthChange}
        />
      </ShinyLifecycleContext.Provider>,
      { container: shell },
    )

    const panel = screen.getByRole("complementary")
    panel.style.direction = "rtl"
    Object.defineProperty(panel, "getBoundingClientRect", {
      value: () => ({ width: 400 }),
    })
    const separator = screen.getByRole("separator", {
      name: "Resize drawer panel",
    })

    armDrawerResizer(separator, "rtl")
    fireEvent.pointerDown(separator, {
      button: 0,
      isPrimary: true,
      pointerId: 1,
      clientX: 100,
    })
    fireEvent.pointerMove(separator, {
      isPrimary: true,
      pointerId: 1,
      clientX: 140,
    })

    expect(onWidthChange).toHaveBeenLastCalledWith("440px")
  })

  it("clamps an oversized measured width and reports a matching ARIA value", async () => {
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.matches("shiny-chat-container")) return { width: 1200 }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 1000 }
        }
        return { width: 0 }
      },
    })

    try {
      const shell = document.createElement("shiny-chat-container")
      document.body.append(shell)
      const onWidthChange = vi.fn()
      render(
        <ShinyLifecycleContext.Provider value={lifecycle()}>
          <ChatDrawer
            drawer={drawer({ width: "1000px" })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: shell },
      )

      await waitFor(() => {
        expect(onWidthChange).toHaveBeenCalledWith("816px")
      })
      const separator = screen.getByRole("separator", {
        name: "Resize drawer panel",
      })
      expect(separator).toHaveAttribute("aria-valuemax", "816")
      expect(separator).toHaveAttribute("aria-valuenow", "816")
      expect(separator).toHaveAttribute("aria-valuetext", "816 pixels")
    } finally {
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("re-clamps an open desktop drawer when its container shrinks", async () => {
    let containerWidth = 1500
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.matches("shiny-chat-container")) {
          return { width: containerWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 1000 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    try {
      const shell = document.createElement("shiny-chat-container")
      const layout = document.createElement("div")
      layout.className = "shiny-chat-layout"
      layout.style.columnGap = "24px"
      shell.append(layout)
      document.body.append(shell)
      const onWidthChange = vi.fn()

      render(
        <ShinyLifecycleContext.Provider value={lifecycle()}>
          <ChatDrawer
            drawer={drawer({ width: "1000px" })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: layout },
      )

      expect(onWidthChange).not.toHaveBeenCalled()
      containerWidth = 1300
      await act(async () => {
        ResizeObserverStub.resize(shell, containerWidth)
      })

      await waitFor(() => {
        expect(onWidthChange).toHaveBeenCalledWith("916px")
      })
      const separator = screen.getByRole("separator", {
        name: "Resize drawer panel",
      })
      expect(separator).toHaveAttribute("aria-valuemax", "916")
      expect(separator).toHaveAttribute("aria-valuenow", "916")
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("does not clamp a CSS-takeover measurement before parent state updates", async () => {
    let layoutWidth = 1500
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.matches("shiny-chat-container")) return { width: 1500 }
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 1000 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    try {
      const shell = document.createElement("shiny-chat-container")
      const layout = document.createElement("div")
      layout.className = "shiny-chat-layout"
      shell.append(layout)
      document.body.append(shell)
      const onWidthChange = vi.fn()

      render(
        <ShinyLifecycleContext.Provider value={lifecycle()}>
          <ChatDrawer
            drawer={drawer({ width: "1000px" })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: layout },
      )

      layoutWidth = 639
      await act(async () => {
        // The child observer fires before ChatContainer's layout observer.
        ResizeObserverStub.resize(shell, 1500)
      })

      expect(onWidthChange).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("updates the maximum ARIA value when only container capacity changes", async () => {
    let containerWidth = 1500
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.matches("shiny-chat-container")) {
          return { width: containerWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 400 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    try {
      const shell = document.createElement("shiny-chat-container")
      const layout = document.createElement("div")
      layout.className = "shiny-chat-layout"
      layout.style.columnGap = "24px"
      shell.append(layout)
      document.body.append(shell)
      const onWidthChange = vi.fn()

      render(
        <ShinyLifecycleContext.Provider value={lifecycle()}>
          <ChatDrawer
            drawer={drawer({ width: "400px" })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: layout },
      )

      const separator = screen.getByRole("separator", {
        name: "Resize drawer panel",
      })
      expect(separator).toHaveAttribute("aria-valuemax", "1116")

      containerWidth = 1300
      await act(async () => {
        ResizeObserverStub.resize(shell, containerWidth)
      })

      await waitFor(() =>
        expect(separator).toHaveAttribute("aria-valuemax", "916"),
      )
      expect(separator).toHaveAttribute("aria-valuenow", "400")
      expect(onWidthChange).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("does not render the resizer when server markup disables resizing", () => {
    renderDrawer(drawer({ resizable: false }))
    expect(screen.queryByRole("separator")).toBeNull()
  })

  it.each([false, true])(
    "uses the close icon and semantics in %s takeover mode",
    (takeover) => {
      renderDrawer(drawer(), { takeover })

      const close = screen.getByRole("button", { name: "Close drawer" })
      expect(close.querySelector("svg path")).toHaveAttribute(
        "d",
        "m3 3 10 10M13 3 3 13",
      )
      expect(screen.queryByRole("button", { name: "Back to chat" })).toBeNull()
    },
  )

  it.each([1200, 1000])(
    "moves focus to the close control after reveal at layout width %s",
    async (layoutWidth) => {
      const original = Object.getOwnPropertyDescriptor(
        HTMLElement.prototype,
        "getBoundingClientRect",
      )
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
        configurable: true,
        value: function () {
          if (this.classList.contains("shiny-chat-layout")) {
            return { width: layoutWidth }
          }
          return { width: 0 }
        },
      })

      vi.stubGlobal(
        "requestAnimationFrame",
        (callback: FrameRequestCallback) => {
          callback(0)
          return 1
        },
      )

      try {
        render(
          <ChatApp
            transport={createMockTransport()}
            shinyLifecycle={createMockShinyLifecycle()}
            elementId="drawer-reveal"
            inputId="drawer-reveal-input"
            initialDrawer={drawer({
              visible: false,
              content: "<p>Ready</p>",
            })}
          />,
        )

        const reveal = await screen.findByRole("button", {
          name: "Show drawer",
        })
        expect(
          screen.getByRole("complementary", { hidden: true }),
        ).toHaveAttribute("hidden")
        reveal.focus()
        fireEvent.click(reveal)

        const close = await screen.findByRole("button", {
          name: "Close drawer",
        })
        expect(close).toHaveFocus()
        expect(screen.queryByRole("button", { name: "Show drawer" })).toBeNull()

        fireEvent.click(close)
        const restored = await screen.findByRole("button", {
          name: "Show drawer",
        })
        expect(restored).toHaveFocus()
      } finally {
        vi.unstubAllGlobals()
        if (original) {
          Object.defineProperty(
            HTMLElement.prototype,
            "getBoundingClientRect",
            original,
          )
        } else {
          delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
            .getBoundingClientRect
        }
      }
    },
  )

  it("removes the reveal control when drawer content is cleared", async () => {
    const transport = createMockTransport()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="drawer-clear"
        inputId="drawer-clear-input"
        initialDrawer={drawer({
          visible: false,
          content: "<p>Ready</p>",
        })}
      />,
    )

    await screen.findByRole("button", { name: "Show drawer" })
    act(() => {
      transport.fire("drawer-clear", {
        type: "drawer_update",
        content: "",
      })
    })
    expect(screen.queryByRole("button", { name: "Show drawer" })).toBeNull()
  })

  it("moves focus to the takeover close control and restores it when hidden", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="drawer-focus"
        inputId="drawer-focus-input"
        initialDrawer={drawer({ visible: false, content: "" })}
      />,
    )
    const priorFocus = await screen.findByRole("textbox")
    priorFocus.focus()

    act(() => {
      transport.fire("drawer-focus", {
        type: "drawer_show",
        content: "<p>Ready</p>",
      })
    })

    const close = await screen.findByRole("button", { name: "Close drawer" })
    expect(close).toHaveFocus()

    fireEvent.click(close)
    await waitFor(() => expect(priorFocus).toHaveFocus())
    vi.unstubAllGlobals()
  })

  it("moves focus to Close when a visible drawer transitions to takeover", async () => {
    let layoutWidth = 1200
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 400 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })

    try {
      const transport = createMockTransport()
      const shinyLifecycle = createMockShinyLifecycle()
      const view = render(
        <ChatApp
          transport={transport}
          shinyLifecycle={shinyLifecycle}
          elementId="drawer-resize-focus"
          inputId="drawer-resize-focus-input"
          initialDrawer={drawer()}
        />,
      )

      const chatControl = await screen.findByRole("textbox")
      chatControl.focus()
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      layoutWidth = 639
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })

      const close = await screen.findByRole("button", {
        name: "Close drawer",
      })
      expect(close).toHaveFocus()

      fireEvent.click(close)
      await waitFor(() => expect(chatControl).toHaveFocus())
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("keeps adjacent layout at the viability boundary", async () => {
    let layoutWidth = 640
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 240 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)

    try {
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-layout-boundary"
          inputId="drawer-layout-boundary-input"
          initialDrawer={drawer()}
        />,
      )
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      await waitFor(() =>
        expect(layout).not.toHaveAttribute("data-drawer-takeover"),
      )

      layoutWidth = 639
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      await waitFor(() =>
        expect(layout).toHaveAttribute("data-drawer-takeover", ""),
      )
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("removes the history trigger from takeover interaction", async () => {
    let layoutWidth = 1200
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 400 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })

    try {
      const transport = createMockTransport()
      const view = render(
        <ChatApp
          transport={transport}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-history-takeover"
          inputId="drawer-history-takeover-input"
          initialDrawer={drawer({ visible: false, content: "" })}
        />,
      )
      await act(async () => {
        transport.fire("drawer-history-takeover", {
          type: "history_update",
          enabled: true,
          conversations: [],
          active_id: null,
        })
      })

      const history = await screen.findByRole("button", {
        name: "Conversation history",
      })
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement
      layoutWidth = 639
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })

      await act(async () => {
        transport.fire("drawer-history-takeover", {
          type: "drawer_show",
          content: "<p>Ready</p>",
        })
      })

      await screen.findByRole("button", { name: "Close drawer" })
      expect(layout).toHaveAttribute("data-drawer-takeover", "")
      expect(history).toBeDisabled()
      expect(history).toHaveAttribute("aria-hidden", "true")
      expect(history).toHaveAttribute("tabindex", "-1")

      fireEvent.click(screen.getByRole("button", { name: "Close drawer" }))
      await waitFor(() => expect(history).not.toBeDisabled())
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("keeps non-chat focus outside the drawer during a takeover transition", async () => {
    let layoutWidth = 1200
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 400 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })

    try {
      const outsideControl = document.createElement("button")
      outsideControl.textContent = "Outside chat"
      document.body.append(outsideControl)
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-outside-focus"
          inputId="drawer-outside-focus-input"
          initialDrawer={drawer()}
        />,
      )
      outsideControl.focus()
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      layoutWidth = 1000
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })

      await screen.findByRole("button", { name: "Close drawer" })
      expect(outsideControl).toHaveFocus()
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("clears a stale takeover return target when re-entering from outside chat", async () => {
    let layoutWidth = 1200
    const original = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function () {
        if (this.classList.contains("shiny-chat-layout")) {
          return { width: layoutWidth }
        }
        if (this.classList.contains("shiny-chat-drawer")) {
          return { width: 400 }
        }
        return { width: 0 }
      },
    })
    ResizeObserverStub.reset()
    vi.stubGlobal("ResizeObserver", ResizeObserverStub)
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })

    try {
      const view = render(
        <ChatApp
          transport={createMockTransport()}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="drawer-stale-focus"
          inputId="drawer-stale-focus-input"
          initialDrawer={drawer()}
        />,
      )
      const chatControl = await screen.findByRole("textbox")
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      chatControl.focus()
      layoutWidth = 1000
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      await screen.findByRole("button", { name: "Close drawer" })

      layoutWidth = 1200
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      await screen.findByRole("button", { name: "Close drawer" })

      const outsideControl = document.createElement("button")
      outsideControl.textContent = "Outside chat"
      document.body.append(outsideControl)
      outsideControl.focus()

      layoutWidth = 1000
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      const close = await screen.findByRole("button", {
        name: "Close drawer",
      })
      expect(outsideControl).toHaveFocus()

      fireEvent.click(close)
      await waitFor(() => expect(outsideControl).toHaveFocus())
    } finally {
      vi.unstubAllGlobals()
      if (original) {
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          original,
        )
      } else {
        delete (HTMLElement.prototype as { getBoundingClientRect?: unknown })
          .getBoundingClientRect
      }
    }
  })

  it("keeps its boundary-aware local resize provider when bslib becomes available", () => {
    class ConformingBslibHandle extends HTMLElement {
      static readonly resizeHandleEvents = RESIZE_HANDLE_EVENTS

      configure() {}
    }

    const bslibTagName = "bslib-resize-handle"
    const originalGet = customElements.get.bind(customElements)
    if (!originalGet(bslibTagName)) {
      customElements.define(bslibTagName, ConformingBslibHandle)
    }
    const get = vi
      .spyOn(customElements, "get")
      .mockImplementation((name) =>
        name === bslibTagName ? undefined : originalGet(name),
      )

    try {
      const onWidthChange = vi.fn()
      const { container, rerender, shiny } = renderDrawer(
        drawer({ title: "Before bslib" }),
        { onWidthChange },
      )
      const localHandle = container.querySelector(".shiny-chat-drawer-resizer")
      expect(localHandle?.tagName).toBe("SHINY-CHAT-RESIZE-HANDLE")
      expect(localHandle).toHaveAttribute(
        "data-shiny-chat-resize-handle-provider",
        "local",
      )

      get.mockRestore()
      rerender(
        <ShinyLifecycleContext.Provider value={shiny}>
          <ChatDrawer
            drawer={drawer({ title: "After bslib" })}
            titleId="drawer-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
      )

      const rerenderedHandle = container.querySelector(
        ".shiny-chat-drawer-resizer",
      )
      expect(rerenderedHandle).toBe(localHandle)
      expect(rerenderedHandle?.tagName).toBe("SHINY-CHAT-RESIZE-HANDLE")
      expect(rerenderedHandle).toHaveAttribute(
        "data-shiny-chat-resize-handle-provider",
        "local",
      )
      act(() => {
        rerenderedHandle!.dispatchEvent(
          new CustomEvent("resize-request", {
            detail: { value: 480, source: "pointer" },
          }),
        )
      })
      expect(onWidthChange).toHaveBeenLastCalledWith("480px")
    } finally {
      get.mockRestore()
    }
  })

  it("does not render or activate an drawer when support is disabled", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="drawer-disabled"
        inputId="drawer-disabled-input"
      />,
    )

    act(() => {
      transport.fire("drawer-disabled", {
        type: "drawer_show",
        content: "<p>Ignored</p>",
      })
    })

    expect(screen.queryByRole("complementary")).toBeNull()
  })
})
