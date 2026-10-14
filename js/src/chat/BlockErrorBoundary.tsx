import { Component, type ReactNode, type ErrorInfo } from "react"

interface Props {
  children: ReactNode
  /** Rendered in place of the children after a render error. */
  fallback?: ReactNode
  /**
   * When this value changes after an error, the boundary resets and retries
   * rendering the children. Pass the block/value the children derive from so
   * a transient error (e.g. mid-stream) recovers on the next update while a
   * deterministic one stays contained.
   */
  resetKey?: unknown
  /** Short label included in the console warning (e.g. block type, tool name). */
  context?: string
}

interface State {
  hasError: boolean
}

/**
 * Containment boundary for a single unit of message content (a block or a
 * tool card body). A render error degrades only that unit to `fallback`
 * instead of bubbling to the per-message boundary and wiping the whole
 * message. Unlike MessageErrorBoundary it recovers: when `resetKey`
 * changes, the error clears and the children retry.
 */
export class BlockErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn(
      `[shinychat] Error rendering ${this.props.context ?? "content"}:`,
      error,
      info,
    )
  }

  componentDidUpdate(prevProps: Props): void {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false })
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // `fallback={null}` is a deliberate choice to render nothing, so test
      // against undefined rather than using ??.
      if (this.props.fallback !== undefined) {
        return this.props.fallback
      }
      return (
        <div className="shiny-chat-block-error" role="alert">
          This content couldn&rsquo;t be displayed.
        </div>
      )
    }
    return this.props.children
  }
}
