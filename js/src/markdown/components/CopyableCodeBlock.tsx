import { useState, useRef, type ReactNode } from "react"

interface CopyableCodeBlockProps {
  children?: ReactNode
  [key: string]: unknown
}

export function CopyableCodeBlock({
  children,
  node,
  ...props
}: CopyableCodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)

  const handleCopy = async () => {
    const codeEl = preRef.current?.querySelector("code")
    const text = codeEl?.textContent ?? ""
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <pre ref={preRef} {...props}>
      <button
        onClick={handleCopy}
        className={`code-copy-button${copied ? " code-copy-button-checked" : ""}`}
        title="Copy to clipboard"
        aria-label="Copy to clipboard"
      >
        <i className="bi" />
      </button>
      {children}
    </pre>
  )
}
