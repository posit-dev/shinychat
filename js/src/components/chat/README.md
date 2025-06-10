# React Chat Components

This directory contains a complete React-based chat interface system, converted from the original Lit web components while preserving all functionality.

## Components

### Core Components

- **`ChatContainer`** - Main orchestrating component that manages state and coordinates all other components
- **`ChatMessages`** - Container for the message list with scrolling behavior  
- **`ChatMessage`** - Individual assistant messages with icons and streaming support
- **`ChatUserMessage`** - User message bubbles with styling
- **`ChatInput`** - Auto-resizing textarea input with send button and keyboard shortcuts

### Features Implemented

✅ **Complete UI Functionality**
- Auto-resize textarea input
- Send on Enter, newline on Shift+Enter
- Message rendering with markdown support
- Streaming message animation
- Loading message indicators
- Message suggestions with click/keyboard interaction
- Input validation and button state management
- Scroll behavior and focus management

✅ **React Architecture**
- Functional components with hooks
- Proper TypeScript typing
- CSS modules for styling
- Component composition and reusability
- Props-based communication (no CustomEvents)

✅ **Styling System**
- Complete CSS module (`Chat.module.css`) with all original styling
- CSS custom properties for theming
- Responsive design
- Bootstrap integration for form controls

✅ **Demo Application**
- Interactive demo showcasing all functionality
- Mock data and simulated responses
- Build system integration

## Usage

```tsx
import { ChatContainer, Message } from './components/chat'

function MyChat() {
  const [messages, setMessages] = useState<Message[]>([])
  
  const handleSendMessage = (message: Message) => {
    setMessages(prev => [...prev, message])
    // Handle sending to backend
  }
  
  return (
    <ChatContainer
      messages={messages}
      onSendMessage={handleSendMessage}
      placeholder="Type your message..."
    />
  )
}
```

## Architecture

The components use React patterns instead of CustomEvents:

- **State Management**: React state in `ChatContainer` as single source of truth
- **Component Communication**: Props and callbacks instead of DOM events
- **Lifecycle**: React hooks (`useEffect`, `useState`, `useCallback`) instead of Lit lifecycle methods
- **DOM Refs**: React refs for direct DOM access when needed (intersection observers, focus management)

## Next Steps

These components are designed to work standalone first. The next phase will add Shiny integration by creating wrapper components that:

1. Convert React props/callbacks to CustomEvents for Shiny communication
2. Handle server-side message passing
3. Integrate with Shiny's input/output system

## Build System

The components are built with:
- **esbuild** for bundling
- **Preact** (React-compatible) for smaller bundle size
- **TypeScript** for type safety
- **CSS modules** for scoped styling

Run `npm run build` to compile all components and demos.

## Demo

Open `js/src/__demos__/chat/demo.html` after building to see the interactive demo.
