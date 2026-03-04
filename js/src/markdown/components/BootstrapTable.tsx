import type { ReactNode } from "react"

interface BootstrapTableProps {
  children?: ReactNode
  [key: string]: unknown
}

export function BootstrapTable({ children, node, ...props }: BootstrapTableProps) {
  return (
    <table className="table table-striped table-bordered" {...props}>
      {children}
    </table>
  )
}
