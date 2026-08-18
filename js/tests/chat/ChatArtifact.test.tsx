import { createRef } from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChatArtifact } from "../../src/chat/ChatArtifact"
import { ChatApp } from "../../src/chat/ChatApp"
import { ShinyLifecycleContext } from "../../src/chat/context"
import { initialState, type ChatArtifactState } from "../../src/chat/state"
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

function artifact(
  overrides: Partial<ChatArtifactState> = {},
): ChatArtifactState {
  return {
    ...initialState.artifact,
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

function renderArtifact(
  currentArtifact: ChatArtifactState,
  options: {
    source?: Element
    shiny?: ShinyLifecycle
    takeover?: boolean
    onClose?: () => void
    onWidthChange?: (width: string) => void
  } = {},
) {
  const closeButtonRef = createRef<HTMLButtonElement>()
  const shiny = options.shiny ?? lifecycle()
  const onClose = options.onClose ?? vi.fn()
  const onWidthChange = options.onWidthChange ?? vi.fn()
  const view = render(
    <ShinyLifecycleContext.Provider value={shiny}>
      <ChatArtifact
        artifact={currentArtifact}
        source={options.source}
        titleId="artifact-title"
        takeover={options.takeover ?? false}
        closeButtonRef={closeButtonRef}
        onClose={onClose}
        onWidthChange={onWidthChange}
      />
    </ShinyLifecycleContext.Provider>,
  )
  return { ...view, closeButtonRef, shiny, onClose, onWidthChange }
}

describe("ChatArtifact", () => {
  it("adopts preserved initial DOM content while hidden", async () => {
    const source = document.createElement("shiny-chat-artifact")
    const initialChild = document.createElement("input")
    initialChild.value = "preserved"
    source.append(initialChild)
    const initialMarkup = source.innerHTML

    const { rerender, shiny } = renderArtifact(
      artifact({ visible: false, content: initialMarkup }),
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
        <ChatArtifact
          artifact={artifact({ visible: true, content: initialMarkup })}
          source={source}
          titleId="artifact-title"
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
    const first = artifact({
      content: "<p>First</p>",
      htmlDeps: [{ name: "first", version: "1.0.0" }],
    })
    const { rerender } = renderArtifact(first, { shiny })

    await waitFor(() => expect(calls).toEqual(["deps", "bind"]))
    calls.length = 0

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatArtifact
          artifact={artifact({
            content: "<p>Second</p>",
            htmlDeps: [{ name: "second", version: "1.0.0" }],
          })}
          titleId="artifact-title"
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
    const { unmount } = renderArtifact(artifact(), { shiny })

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
    const first = artifact({ content: '<input id="shared-input">' })
    const { rerender, unmount } = renderArtifact(first, { shiny })

    await waitFor(() => expect(shiny.bindAll).toHaveBeenCalledTimes(1))
    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <ChatArtifact
          artifact={artifact({
            content: '<div><input id="shared-input"></div>',
          })}
          titleId="artifact-title"
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
        <ChatArtifact
          artifact={artifact({ width: "400px" })}
          titleId="artifact-title"
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
      name: "Resize artifact panel",
    })
    expect(separator).toHaveAttribute("aria-valuemin", "240")
    expect(separator).toHaveAttribute("aria-valuemax", "840")

    fireEvent.keyDown(separator, { key: "ArrowRight" })
    expect(onWidthChange).toHaveBeenLastCalledWith("416px")

    fireEvent.pointerDown(separator, { pointerId: 1, clientX: 100 })
    fireEvent.pointerMove(separator, { pointerId: 1, clientX: 60 })
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          <ChatArtifact
            artifact={artifact({ width: "1000px" })}
            titleId="artifact-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: shell },
      )

      await waitFor(() => {
        expect(onWidthChange).toHaveBeenCalledWith("840px")
      })
      const separator = screen.getByRole("separator", {
        name: "Resize artifact panel",
      })
      expect(separator).toHaveAttribute("aria-valuemax", "840")
      expect(separator).toHaveAttribute("aria-valuenow", "840")
      expect(separator).toHaveAttribute("aria-valuetext", "840 pixels")
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

  it("re-clamps an open desktop artifact when its container shrinks", async () => {
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          <ChatArtifact
            artifact={artifact({ width: "1000px" })}
            titleId="artifact-title"
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
        name: "Resize artifact panel",
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          <ChatArtifact
            artifact={artifact({ width: "1000px" })}
            titleId="artifact-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: layout },
      )

      layoutWidth = 1000
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          <ChatArtifact
            artifact={artifact({ width: "400px" })}
            titleId="artifact-title"
            takeover={false}
            closeButtonRef={createRef<HTMLButtonElement>()}
            onClose={vi.fn()}
            onWidthChange={onWidthChange}
          />
        </ShinyLifecycleContext.Provider>,
        { container: layout },
      )

      const separator = screen.getByRole("separator", {
        name: "Resize artifact panel",
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
    renderArtifact(artifact({ resizable: false }))
    expect(screen.queryByRole("separator")).toBeNull()
  })

  it("moves focus to the takeover back control and restores it when hidden", async () => {
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
        elementId="artifact-focus"
        inputId="artifact-focus-input"
        initialArtifact={artifact({ visible: false, content: "" })}
      />,
    )
    const priorFocus = await screen.findByRole("textbox")
    priorFocus.focus()

    act(() => {
      transport.fire("artifact-focus", {
        type: "artifact_show",
        content: "<p>Ready</p>",
      })
    })

    const back = await screen.findByRole("button", { name: "Back to chat" })
    expect(back).toHaveFocus()

    fireEvent.click(back)
    await waitFor(() => expect(priorFocus).toHaveFocus())
    vi.unstubAllGlobals()
  })

  it("moves focus to Back when a visible artifact transitions to takeover", async () => {
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          elementId="artifact-resize-focus"
          inputId="artifact-resize-focus-input"
          initialArtifact={artifact()}
        />,
      )

      const chatControl = await screen.findByRole("textbox")
      chatControl.focus()
      const layout = view.container.querySelector(
        ".shiny-chat-layout",
      ) as HTMLElement

      layoutWidth = 1000
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })

      const back = await screen.findByRole("button", { name: "Back to chat" })
      expect(back).toHaveFocus()

      fireEvent.click(back)
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

  it("keeps non-chat focus outside the artifact during a takeover transition", async () => {
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          elementId="artifact-outside-focus"
          inputId="artifact-outside-focus-input"
          initialArtifact={artifact()}
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

      await screen.findByRole("button", { name: "Back to chat" })
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
        if (this.classList.contains("shiny-chat-artifact")) {
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
          elementId="artifact-stale-focus"
          inputId="artifact-stale-focus-input"
          initialArtifact={artifact()}
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
      await screen.findByRole("button", { name: "Back to chat" })

      layoutWidth = 1200
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      await screen.findByRole("button", { name: "Close artifact" })

      const outsideControl = document.createElement("button")
      outsideControl.textContent = "Outside chat"
      document.body.append(outsideControl)
      outsideControl.focus()

      layoutWidth = 1000
      await act(async () => {
        ResizeObserverStub.resize(layout, layoutWidth)
      })
      const back = await screen.findByRole("button", { name: "Back to chat" })
      expect(outsideControl).toHaveFocus()

      fireEvent.click(back)
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

  it("does not render or activate an artifact when support is disabled", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="artifact-disabled"
        inputId="artifact-disabled-input"
      />,
    )

    act(() => {
      transport.fire("artifact-disabled", {
        type: "artifact_show",
        content: "<p>Ignored</p>",
      })
    })

    expect(screen.queryByRole("complementary")).toBeNull()
  })
})
