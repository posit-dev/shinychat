# React Chat Components

This directory contains a complete React-based chat interface system, converted from the original Lit web components while preserving all functionality, plus Shiny integration.

## Components

### Core React Components

- **`ChatContainer`** - Main orchestrating component that manages state and coordinates all other components
- **`ChatMessages`** - Container for the message list with scrolling behavior  
- **`ChatMessage`** - Individual assistant messages with icons and streaming support
- **`ChatUserMessage`** - User message bubbles with styling
- **`ChatInput`** - Auto-resizing textarea input with send button and keyboard shortcuts

### State Management

- **`useChatState`** - Custom hook that manages all chat state logic
- **Clean separation**: UI components, state logic, and external integration are separate

### Shiny Integration

- **`ShinyChatContainer`** - Custom element that wraps React components for Shiny
- **Event-driven communication**: Uses CustomEvents instead of imperative method calls
- **Type-safe**: All Shiny messages and events are properly typed

## Features Implemented

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
- Custom hook for state management (`useChatState`)
- Proper TypeScript typing
- CSS modules for styling
- Component composition and reusability
- Props-based communication (no CustomEvents between React components)

✅ **Shiny Integration**
- CustomEvent-based communication between Shiny and React
- No imperative refs or `as any` casting
- Server message handling with HTML dependency support
- User input forwarding to Shiny server
- Compatible with existing Shiny chat API

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

### Standalone React Usage

```tsx
import { ChatContainer, Message, useChatState } from './components/chat'

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

### With Custom Hook

```tsx
import { useChatState } from './components/chat'

function MyAdvancedChat() {
  const chat = useChatState()
  
  // Direct access to all state and methods
  const handleApiResponse = (response: string) => {
    chat.appendMessage({
      role: "assistant",
      content: response,
      content_type: "markdown"
    })
  }
  
  return (
    <ChatContainer
      messages={chat.messages}
      onSendMessage={(msg) => {
        chat.handleInputSent(msg.content)
        // Send to API...
      }}
    />
  )
}
```

### Shiny Integration

The Shiny integration works through CustomEvents:

```html
<!-- In your Shiny UI -->
<shiny-chat-container id="my-chat" icon-assistant="🤖" placeholder="Ask me anything...">
</shiny-chat-container>
```

```r
# In your Shiny server
# Messages are sent via the shinyChatMessage handler
session$sendCustomMessage("shinyChatMessage", list(
  id = "my-chat",
  handler = "shiny-chat-append-message",
  obj = list(
    content = "Hello from R!",
    role = "assistant",
    content_type = "markdown"
  )
))
```

## Architecture

### Event Flow

1. **User Input**: User types in React ChatInput → calls `onInputSent`
2. **Shiny Communication**: ChatContainer sends input to Shiny via `setInputValue`
3. **Server Response**: Shiny server sends message via `shinyChatMessage` handler  
4. **CustomEvent Dispatch**: ShinyChatContainer dispatches CustomEvent
5. **React State Update**: ChatContainer listens for event → calls hook method
6. **UI Update**: React re-renders with new state

### No Imperative APIs

The system uses React patterns instead of direct method calls:

- **State Management**: `useChatState` hook instead of component state manipulation
- **Component Communication**: Props and callbacks instead of DOM events between React components
- **External Integration**: CustomEvents instead of imperative method calls
- **DOM Refs**: Only used for focus management and intersection observers, not state

## Build System

The components are built with:
- **esbuild** for bundling
- **Preact** (React-compatible) for smaller bundle size
- **TypeScript** for type safety
- **CSS modules** for scoped styling

Build entries:
- `components/chat/chat.css` - Compiled CSS
- `components/chat/shiny-chat-container.js` - Shiny integration
- `demos/chat/demo.js` - Interactive demo

Run `npm run build` to compile all components and demos.

## Demo

Open `js/src/__demos__/chat/demo-simple.html` after building to see the interactive demo.

## Benefits of This Implementation

✅ **Type Safety**: Full TypeScript coverage, no `as any` casts
✅ **Testability**: Each layer can be tested independently
✅ **Maintainability**: Clear separation of concerns
✅ **Performance**: Efficient React rendering, minimal re-renders
✅ **Compatibility**: Drop-in replacement for Lit version
✅ **Extensibility**: Easy to add new features or UI variations
