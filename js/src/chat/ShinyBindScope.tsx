import { useContext, useEffect, useRef, type ReactNode } from "react"
import { ShinyLifecycleContext } from "./context"

// Complement to RawHTML/RawDOM: those sinks bind DOM they place imperatively
// (RawHTML from an HTML string, RawDOM by adopting existing nodes).
// ShinyBindScope binds a React-rendered subtree — content that must round-trip
// through the HTML processor and the trusted component map (resolving e.g.
// <shiny-aside> to its React component) yet still hosts Shiny inputs/outputs
// that need bindAll. The wrapper joins with display:contents so it adds no
// layout box of its own.
//
// Binds once per mount and unbinds on unmount. React — not this component —
// owns the subtree, so on an in-place content change React swaps bound nodes
// during commit, before any effect cleanup could unbind them. Callers whose
// content can change while mounted should key the scope by that content so a
// change remounts it: the old subtree unbinds while still intact and the new
// one binds fresh — the same unbind-old → bind-new guarantee RawHTML's
// innerHTML reset provides.
export function ShinyBindScope({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const shiny = useContext(ShinyLifecycleContext)

  useEffect(() => {
    const el = ref.current
    if (!el || !shiny) return
    // Child effects have already run, so the rendered subtree — including
    // any resolved react carriers — is in the DOM and binds here.
    shiny.bindAll(el)
    return () => {
      // On unmount the detached wrapper still holds its whole subtree, so
      // this unbinds everything the mount bound.
      shiny.unbindAll(el)
    }
  }, [shiny])

  return (
    <div ref={ref} style={{ display: "contents" }}>
      {children}
    </div>
  )
}
