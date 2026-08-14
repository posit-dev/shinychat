import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { mergeCitations, type CitationEntry } from "./citations"

interface CitationRegistry {
  register: (key: string, entries: CitationEntry[]) => void
  unregister: (key: string) => void
}

const RegisterContext = createContext<CitationRegistry | null>(null)
const CitationsContext = createContext<CitationEntry[]>([])

export function CitationCollectorProvider({
  children,
}: {
  children: ReactNode
}) {
  const mapRef = useRef<Map<string, CitationEntry[]>>(new Map())
  const [citations, setCitations] = useState<CitationEntry[]>([])

  const recompute = useCallback(() => {
    const all: CitationEntry[] = []
    for (const entries of mapRef.current.values()) all.push(...entries)
    setCitations(mergeCitations(all))
  }, [])

  const register = useCallback(
    (key: string, entries: CitationEntry[]) => {
      mapRef.current.set(key, entries)
      recompute()
    },
    [recompute],
  )

  const unregister = useCallback(
    (key: string) => {
      if (mapRef.current.delete(key)) recompute()
    },
    [recompute],
  )

  const registry = useMemo<CitationRegistry>(
    () => ({ register, unregister }),
    [register, unregister],
  )

  return (
    <RegisterContext.Provider value={registry}>
      <CitationsContext.Provider value={citations}>
        {children}
      </CitationsContext.Provider>
    </RegisterContext.Provider>
  )
}

export function useCitationRegister(): CitationRegistry | null {
  return useContext(RegisterContext)
}

export function useCitations(): CitationEntry[] {
  return useContext(CitationsContext)
}
