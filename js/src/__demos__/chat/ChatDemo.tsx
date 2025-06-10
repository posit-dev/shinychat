import { useState, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import { ChatContainer, Message } from "../../components/chat"
// Import the CSS file to make sure styles are applied
import "../../components/chat/Chat.module.css"

const DEMO_MESSAGES: Message[] = [
  {
    id: "1",
    role: "assistant",
    content:
      'Hello! I\'m your AI assistant. How can I help you today?\n\nYou can try some suggestions like:\n- [What\'s the weather like?](.suggestion){data-suggestion="What\'s the weather like?"}\n- [Tell me a joke](.suggestion submit){data-suggestion="Tell me a joke" data-suggestion-submit="true"}\n- [Help me write code](.suggestion){data-suggestion="Help me write code"}',
  },
]

const SAMPLE_RESPONSES = [
  "That's a great question! Let me help you with that.",
  "Here's what I found:\n\n```javascript\nconst example = 'This is some sample code';\nconsole.log(example);\n```\n\nWould you like me to explain how this works?",
  "I understand you're looking for information about that topic. Here are some key points:\n\n1. First important point\n2. Second consideration\n3. Final thoughts\n\nIs there anything specific you'd like me to elaborate on?",
  "That's an interesting perspective! Here's my response with some **markdown formatting**:\n\n- *Italic text* for emphasis\n- **Bold text** for importance\n- `inline code` for technical terms\n\n> This is a blockquote to highlight important information.\n\nDoes this help answer your question?",
  "I can help you with that! Here's a step-by-step approach:\n\n### Step 1: Understanding the basics\nFirst, let's cover the fundamentals...\n\n### Step 2: Implementation\n```python\ndef example_function():\n    return \"Hello, World!\"\n```\n\n### Step 3: Testing\nMake sure to test your implementation thoroughly.\n\nWould you like me to go deeper into any of these steps?",
]

export function ChatDemo(): JSX.Element {
  const [messages, setMessages] = useState<Message[]>(DEMO_MESSAGES)
  const [isTyping, setIsTyping] = useState(false)

  const handleSendMessage = useCallback((message: Message) => {
    // Add user message immediately
    setMessages((prev) => [...prev, message])
    setIsTyping(true)

    // Simulate AI response after a delay
    setTimeout(
      () => {
        const response =
          SAMPLE_RESPONSES[Math.floor(Math.random() * SAMPLE_RESPONSES.length)]
        if (response) {
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: response,
            content_type: "markdown",
          }

          setMessages((prev) => [...prev, assistantMessage])
          setIsTyping(false)
        }
      },
      1000 + Math.random() * 2000,
    ) // Random delay between 1-3 seconds
  }, [])

  const handleSuggestionClick = useCallback(
    (suggestion: string, submit: boolean) => {
      if (submit) {
        const userMessage: Message = {
          id: `user-${Date.now()}`,
          role: "user",
          content: suggestion,
        }
        handleSendMessage(userMessage)
      }
    },
    [handleSendMessage],
  )

  const clearChat = () => {
    setMessages(DEMO_MESSAGES)
    setIsTyping(false)
  }

  const addTypingMessage = () => {
    if (isTyping) return

    setIsTyping(true)
    const typingMessage: Message = {
      id: `typing-${Date.now()}`,
      role: "assistant",
      content: "",
      content_type: "markdown",
    }
    setMessages((prev) => [...prev, typingMessage])

    // Remove typing message after a few seconds
    setTimeout(() => {
      setMessages((prev) => prev.filter((msg) => msg.id !== typingMessage.id))
      setIsTyping(false)
    }, 3000)
  }

  // Add typing message when there are no assistant messages with empty content
  const displayMessages = [...messages]
  if (
    isTyping &&
    !messages.some((msg) => msg.role === "assistant" && msg.content === "")
  ) {
    displayMessages.push({
      id: `typing-indicator`,
      role: "assistant",
      content: "",
      content_type: "markdown",
    })
  }

  return (
    <div
      style={{
        height: "600px",
        maxWidth: "800px",
        margin: "0 auto",
        border: "1px solid #e9ecef",
        borderRadius: "8px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "1rem",
          borderBottom: "1px solid #e9ecef",
          backgroundColor: "#f8f9fa",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.25rem" }}>Chat Demo</h3>
        <div>
          <button
            onClick={addTypingMessage}
            disabled={isTyping}
            style={{ marginRight: "0.5rem" }}
            className="btn btn-sm btn-outline-secondary"
          >
            Show Typing
          </button>
          <button onClick={clearChat} className="btn btn-sm btn-outline-danger">
            Clear Chat
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "hidden" }}>
        <ChatContainer
          id="demo-chat"
          messages={displayMessages}
          iconAssistant=""
          placeholder="Type your message here..."
          onSendMessage={handleSendMessage}
          onSuggestionClick={handleSuggestionClick}
        />
      </div>
    </div>
  )
}
