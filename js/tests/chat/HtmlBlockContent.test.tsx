import { describe, it, expect, vi } from "vitest"
import { render, act } from "@testing-library/react"
import { HtmlBlockContent } from "../../src/chat/HtmlBlockContent"
import { ShinyLifecycleContext } from "../../src/chat/context"
import type { ShinyLifecycle } from "../../src/transport/types"
import type { HtmlDep } from "../../src/transport/types"

const depA = { name: "lib-a", version: "1.0" } as unknown as HtmlDep
const depB = { name: "lib-b", version: "1.0" } as unknown as HtmlDep

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
    const { shiny, resolve } = mockShinyWithGatedDeps()

    const { container, rerender } = render(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='a'>A</div>"}
          htmlDeps={[depA]}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(container.querySelector("[data-island='a']")).toBeNull()
    await act(async () => {
      resolve(depA)
    })
    expect(container.querySelector("[data-island='a']")?.textContent).toBe("A")

    rerender(
      <ShinyLifecycleContext.Provider value={shiny}>
        <HtmlBlockContent
          content={"<div data-island='b'>B</div>"}
          htmlDeps={[depB]}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(shiny.renderDependencies).toHaveBeenCalledWith([depB])
    expect(container.querySelector("[data-island='b']")).toBeNull()
    expect(container.querySelector("[data-island='a']")).toBeNull()

    await act(async () => {
      resolve(depB)
    })
    expect(container.querySelector("[data-island='b']")?.textContent).toBe("B")
  })

  it("mounts a dependency-free replacement immediately (never permanently hidden)", async () => {
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
