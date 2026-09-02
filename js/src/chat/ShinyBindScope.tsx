import { useContext, useEffect, useRef, type ReactNode } from "react"
import { ShinyLifecycleContext } from "./context"

// Binds a React-rendered subtree through Shiny's bindAll/unbindAll, for
// trusted component-map content that still hosts Shiny inputs/outputs.
// Callers whose content can change while mounted should key the scope by
// that content so a change remounts it (unbind-old → bind-new).
export function ShinyBindScope({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const shiny = useContext(ShinyLifecycleContext)

  useEffect(() => {
    const el = ref.current
    if (!el || !shiny) return
    shiny.bindAll(el)
    return () => {
      shiny.unbindAll(el)
    }
  }, [shiny])

  return (
    <div ref={ref} style={{ display: "contents" }}>
      {children}
    </div>
  )
}
