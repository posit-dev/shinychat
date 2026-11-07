import { useRef, type ReactNode } from "react"
import { CopyButton } from "./CopyButton"

interface CopyableCodeBlockProps {
  children?: ReactNode
  [key: string]: unknown
}

export function CopyableCodeBlock({
  children,
  node,
  ...props
}: CopyableCodeBlockProps) {
  const preRef = useRef<HTMLPreElement>(null)

  return (
    <pre ref={preRef} {...props}>
      <CopyButton
        getText={() => preRef.current?.querySelector("code")?.textContent ?? ""}
      />
      {children}
    </pre>
  )
}
