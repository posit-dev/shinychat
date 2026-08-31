import { describe, it, expect, vi } from "vitest"
import { render, act } from "@testing-library/react"
import { HtmlBlockContent } from "../../src/chat/HtmlBlockContent"
import { ShinyLifecycleContext } from "../../src/chat/context"
import type { ShinyLifecycle } from "../../src/transport/types"
import type { HtmlDep } from "../../src/transport/types"

const depA = { name: "lib-a", version: "1.0" } as unknown as HtmlDep
const depB = { name: "lib-b", version: "1.0" } as unknown as HtmlDep

/**
 * A Shiny lifecycle whose renderDependencies resolves only when the test
 * says so, per dep identity.
 */
function mockShinyWithGatedDeps(): {
  shiny: ShinyLifecycle
  resolve: (dep: HtmlDep) => void
} {
  const resolvers = new Map<HtmlDep, () => void>()
  const shiny: ShinyLifecycle = {
    bindAll: vi.fn(async () => {}),
    unbindAll: vi.fn(),
    renderDependencies: vi.fn(
      (deps: HtmlDep[]) =>
        new Promise<void>((resolve) => {
          resolvers.set(deps[0]!, resolve)
        }),
    ),
    showClientMessage: vi.fn(),
  }
  return {
    shiny,
    resolve: (dep) => resolvers.get(dep)?.(),
  }
}

describe("HtmlBlockContent", () => {
  it("re-gates when the instance is reused with different deps (block replacement)", async () => {
    // MarkdownStream's replace (or a Chat message update) can swap one
    // block for another at the same position: React reuses the component
    // instance, so readiness must be tracked against the CURRENT htmlDeps,
    // not the deps the instance mounted with.
    const { shiny, resolve } = mockShinyWithGatedDeps()

    const { container, rerender } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='a'>A</div>"}
          htmlDeps={[depA]}
        />
      </ShinyLifecycleContext.Provider>,
    )

    // Gated on depA: nothing mounts until it resolves.
    expect(container.querySelector("[data-island='a']")).toBeNull()
    await act(async () => {
      resolve(depA)
    })
    expect(container.querySelector("[data-island='a']")?.textContent).toBe("A")

    // The instance is reused for a replacement block with different deps.
    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='b'>B</div>"}
          htmlDeps={[depB]}
        />
      </ShinyLifecycleContext.Provider>,
    )

    // The replacement must not mount before its own deps finish loading —
    // and the old block's HTML must not linger behind the gate.
    expect(shiny.renderDependencies).toHaveBeenCalledWith([depB])
    expect(container.querySelector("[data-island='b']")).toBeNull()
    expect(container.querySelector("[data-island='a']")).toBeNull()

    await act(async () => {
      resolve(depB)
    })
    expect(container.querySelector("[data-island='b']")?.textContent).toBe("B")
  })

  it("mounts a dependency-free replacement immediately (never permanently hidden)", async () => {
    // A block whose deps never resolve, replaced by a dependency-free
    // block: the replacement has nothing to wait for and must mount at
    // once (a stale pending gate must not hide it forever).
    const { shiny } = mockShinyWithGatedDeps()

    const { container, rerender } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='a'>A</div>"}
          htmlDeps={[depA]}
        />
      </ShinyLifecycleContext.Provider>,
    )
    expect(container.querySelector("[data-island='a']")).toBeNull()

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='b'>B</div>"}
          htmlDeps={[]}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(container.querySelector("[data-island='b']")?.textContent).toBe("B")
  })
})
