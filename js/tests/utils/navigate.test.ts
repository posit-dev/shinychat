import { afterEach, describe, expect, test, vi } from "vitest"
import { navigateTo } from "../../src/utils/navigate"

describe("navigateTo", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  test("reload with null url hard navigates to current path", () => {
    const assign = vi.fn()
    vi.stubGlobal("location", {
      ...window.location,
      assign,
      pathname: "/current-path",
    })

    navigateTo(null, true)

    expect(assign).toHaveBeenCalledWith("/current-path")
  })
})
