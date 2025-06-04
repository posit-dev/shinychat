# React Migration Setup

This document describes the React infrastructure setup for migrating Lit components to React.

## Overview

We're using **Preact** instead of React for smaller bundle sizes while maintaining full React API compatibility. Components are wrapped in custom elements to integrate with Shiny.

## Architecture

### Custom Element Wrapper Pattern

Each React component is wrapped in a custom element class that:
1. Renders the React component using `preact/render`
2. Handles data attributes for initial props
3. Cleans up on disconnection

Example:
```typescript
export class ShinyHelloWorld extends HTMLElement {
  connectedCallback() {
    const name = this.getAttribute('data-name') || 'World';
    render(<HelloWorld name={name} />, this);
  }
  
  disconnectedCallback() {
    render(null, this);
  }
}

customElements.define('shiny-hello-world', ShinyHelloWorld);
```

### Component Structure

```
src/
├── hello-world/
│   ├── HelloWorld.tsx          # React component
│   ├── HelloWorld.test.tsx     # Tests
│   ├── hello-world.tsx         # Custom element wrapper
│   └── hello-world.scss        # Styles
```

## Development Workflow

### Building
```bash
npm run build        # Full build with linting
npm run build-fast   # Fast build without minification
npm run watch        # Watch mode with linting
npm run watch-fast   # Fast watch mode
```

### Testing
```bash
npm test             # Run all tests
npm run test:watch   # Watch mode for tests
```

### Demo
Open `demo.html` in a browser to see the components in action.

## Configuration

### TypeScript (tsconfig.json)
- `jsx: "react-jsx"` with `jsxImportSource: "preact"`
- Supports both `.ts` and `.tsx` files

### Build (build.ts)
- Preact aliases for React compatibility
- SCSS compilation
- ES module output

### Testing (jest.config.js)
- Jest with jsdom environment
- React Testing Library for component testing
- Preact aliases for test compatibility

## Next Steps

1. **Chat Component Migration**: Convert `src/chat/chat.ts` to React
2. **Markdown Stream Migration**: Convert `src/markdown-stream/markdown-stream.ts` to React
3. **Shiny Integration**: Add message handlers and input value communication
4. **Advanced Testing**: Add integration tests and component interaction testing

## Dependencies

### Runtime
- `preact`: React-compatible library with smaller bundle size

### Development
- `@testing-library/preact`: Component testing utilities
- `@testing-library/jest-dom`: Custom Jest matchers
- `jest`: Test runner
- `ts-jest`: TypeScript support for Jest
