import { Component, type ReactNode, type ErrorInfo } from "react"

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class MessageErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("[shinychat] Error rendering message:", error, info)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="shiny-chat-message-error" role="alert">
          Error rendering message
        </div>
      )
    }
    return this.props.children
  }
}
