---
provider: aws_bedrock
model: us.anthropic.claude-sonnet-4-20250514-v1:0
tools:  [files, search_web]
echo: output
---

# Product Requirements Document: Chat & Markdown Stream React Migration

## Project Overview

**Objective**: Convert existing Lit web components to React components, prioritizing UI functionality first, then Shiny integration.

**Strategy**: Build fully functional React components that work standalone, then wire up Shiny communication patterns.

## How to Connect Shiny and React

### Creating the react-based component

To initialize the React component in a Shiny app, the React-based component is typically created inside a custom element, where the `connectedCallback()` method is used to set up the component.

Here's an example for a data grid component:

```js
export class ShinyDataFrameOutput extends HTMLElement {
  reactRoot?: Root;
  errorRoot!: HTMLSpanElement;

  connectedCallback() {
    // Don't use shadow DOM so the component can inherit styles from the main document.
    const [target] = [this];

    // Create a new element that will serve as the root for the React component.
    const myDiv = document.createElement("div");
    myDiv.classList.add("html-fill-container", "html-fill-item");
    target.appendChild(myDiv);

    this.reactRoot = createRoot(myDiv);

    // Initial state data will be encoded as a `<script>` child of custom element
    const dataEl = this.querySelector("script[data-for-shiny-data-grid]");
    if (dataEl) {
      const data = JSON.parse(dataEl.innerText);
      this.renderValue(data);
    }
  }

  renderValue(value: ShinyDataGridServerInfo<unknown> | null) {
    this.clearError();

    if (!value) {
      this.reactRoot!.render(null);
      return;
    }

    this.reactRoot!.render(
      <StrictMode>
        <ShinyDataGrid
          id={this.id}
          gridInfo={value}
          bgcolor={getComputedBgColor(this)}
        ></ShinyDataGrid>
      </StrictMode>
    );
  }

  renderError(err: ErrorsMessageValue) {
    this.reactRoot!.render(null);
    this.errorRoot.innerText = err.message;
  }

  clearError() {
    this.reactRoot!.render(null);
    this.errorRoot.innerText = "";
  }
}

customElements.define("shiny-data-frame", ShinyDataFrameOutput);
```

Prefer using data attributes to pass initial state to the React component, but recognize that this is not always possible, especially when the initial state is large or complex.

When the R or Python side of the component has a large dataset representing the initial state, it is passed as a JSON-encoded string inside a `<script>` tag with an identifying attribute.
The R or Python side of the component then creates the custom element, sets its initial data using a `<script>` tag, resulting in the following HTML structure:

```html
<shiny-data-frame id="my-data-grid">
  <script type="application/json" data-for-shiny-data-grid>
    {"columns": [...], "rows": [...]}
  </script>
</shiny-data-frame>
```

### Receiving Shiny messages in React

Shiny receives server-side messages using `Shiny.addCustomMessageHandler(handler_name)`, which dispatches CustomEvents that your React component can listen for.

The pattern is to establish one message handler for Shiny's messages that have the structure

```js
message: {
  id: "component_id", // ID of the component receiving the message
  eventName: "shinychat-set-input", // Custom event name
  data: {
    // Payload data that becomes `event.detail` in the dispatched event
  }
}
```

To receive Shiny messages in a React component, you can use the `useEffect` hook to set up an event listener for CustomEvents.
Here's an example from the data grid component:

```js
useEffect(() => {
  const handleUpdateData = (
    event: CustomEvent<DataGridUpdateDataEventDetail>
  ) => {
    const evtData = event.detail;

    updateData(evtData);
  };

  if (!id) return;

  const element = document.getElementById(id);
  if (!element) return;

  element.addEventListener("updateData", handleUpdateData as EventListener);

  return () => {
    element.removeEventListener(
      "updateData",
      handleUpdateData as EventListener
    );
  };
}, [columns, id, resetCellEditMap, setTableData, updateData]);
```

### Sending data to Shiny from React

Shiny uses input values to communicate data back to the server.
Each input must have a unique ID and can be updated using `Shiny.setInputValue(inputId, value)`.
The data returned in an input value can be any JSON-serializable data structure, but must be atomic in the sense that when a value is updated the server will react to the entire change at once.
For example, if the component has two inputs, `first` and `second`, and you want the Shiny user to be able to react to changes in either input independently, you'll need to create a unique ID from the component ID and set each input value separately.

To send data to Shiny from a React component, you can use the `Shiny.setInputValue` function directly in your event handlers or state update functions, for example with `useEffect()`.
Here's an example from the data grid component:

```js
useEffect(() => {
  if (!id) return;
  const shinySort: prepareShinyData(sorting, columns);
  window.Shiny.setInputValue!(`${id}_sort`, shinySort);
}, [columns, id, sorting]);
```

### React Considerations

These are useful considerations when building React components that will integrate with Shiny:

* Keep visual elements in the light DOM to inherit styles from the main document.
* Use Preact instead of React to reduce bundle size, as it is API-compatible with React.
* Use `createRoot` from `react-dom/client` and treat each component as a small React application.
* React bundles must be declared as dependencies, not just included as script tags
* Use ES modules (⁠type = "module") for better compatibility

## Phase 1: React UI Components

### Task 1: Project Setup & Basic React Infrastructure

**Objective**: Get React development environment working with existing build system.

**Deliverables**:
1. Updated `package.json` with React dependencies
2. Modified `tsconfig.json` for React JSX
3. Updated `build.ts` to handle React + existing SCSS
4. Basic test setup (vitest + React Testing Library)
5. Simple "Hello World" React component that builds successfully

**Key Focus**: Minimal changes to get React building alongside existing code.

**Acceptance Criteria**:
- [x] `npm run build` successfully compiles React components
- [x] Can import and render a basic React component
- [x] SCSS compilation still works
- [x] TypeScript compilation works without errors
- [x] `npm test` runs component tests successfully


### Task 2: MarkdownStream React Component (UI Only)

**Objective**: Create a fully functional MarkdownStream React component that renders all content types, handles streaming, and includes syntax highlighting - but without Shiny integration.

**Context**: Port the entire UI functionality from `markdown-stream.ts`, focusing on content rendering, streaming states, and user interactions.

**Deliverables**:
1. `components/MarkdownStream.tsx` with:
   - Props: `content`, `contentType`, `streaming`, `autoScroll`, `onContentChange`, `onStreamEnd`
   - Content rendering for all types (markdown, semi-markdown, HTML, text)
   - Streaming state with dot indicator
   - Syntax highlighting with highlight.js
   - Code copy functionality
   - Auto-scroll behavior
   - All visual states and transitions

2. `components/MarkdownStream.module.css` - Complete styling
3. Storybook or demo page to showcase functionality
4. Unit tests for all rendering scenarios

**Key Focus**: Perfect visual and interaction parity with Lit version, testable in isolation.

**Acceptance Criteria**:
- [ ] All content types render identically to Lit version
- [ ] Streaming animation and behavior matches
- [ ] Syntax highlighting works correctly
- [ ] Code copy buttons function properly
- [ ] Auto-scroll behavior matches original
- [ ] Component works in isolation with props

<!-- HIDE -->

### Task 3: Complete Chat UI System

**Objective**: Build the entire chat interface as functional React components with all interactions working, but using React props/callbacks instead of CustomEvents.

**Context**: Convert all chat components from `chat.ts` to React, focusing on UI interactions, state management, and component communication through React patterns.

**Deliverables**:

1. **React Components**:
   - `components/ChatMessage.tsx` - Uses MarkdownStream, handles icons and streaming
   - `components/ChatUserMessage.tsx` - Simple wrapper around MarkdownStream
   - `components/ChatInput.tsx` - Auto-resize textarea, keyboard shortcuts, validation
   - `components/ChatMessages.tsx` - Message list container
   - `components/ChatContainer.tsx` - Main component orchestrating everything

2. **React State Management**:
   - Message list state management
   - Input state and validation
   - Loading states
   - Streaming states
   - Focus management

3. **UI Interactions**:
   - Send message on Enter (Shift+Enter for newline)
   - Auto-resize textarea
   - Input validation and button states
   - Message suggestions (click/keyboard)
   - Loading message indicators
   - Scroll behavior

4. **Complete Styling** (`components/Chat.module.css`):
   - Grid layout, message styling, input styling
   - All animations and transitions
   - Responsive behavior
   - CSS custom properties with defaults

5. **Demo Application**:
   - Simple HTML page that demonstrates full chat functionality
   - Mock data for testing different scenarios
   - All interactions working without Shiny

**Key Focus**: Complete, self-contained chat interface that works perfectly in React.

**Acceptance Criteria**:
- [ ] Chat interface looks and behaves identically to Lit version
- [ ] All user interactions work (typing, sending, suggestions)
- [ ] Message rendering and streaming work perfectly
- [ ] Auto-scroll and focus management match original
- [ ] Demo page showcases all functionality
- [ ] No Shiny dependencies required for UI functionality


## Phase 2: Shiny Integration Layer

### Task 4: Shiny Communication Bridge

**Objective**: Add Shiny integration layer that bridges React component state with CustomEvents and Shiny message handlers.

**Context**: Create the glue code that makes React components work with Shiny's communication patterns, preserving exact same API as Lit version.

**Deliverables**:

1. **Shiny Integration Utilities** (`utils/shiny-integration.ts`):
   - React hooks for Shiny message handlers
   - CustomEvent dispatch utilities
   - HTML dependency management
   - Error handling and user feedback

2. **Message Handlers**:
   - `shinyChatMessage` handler that dispatches to React components
   - `shinyMarkdownStreamMessage` handler
   - Proper error handling when elements don't exist

3. **React-to-Shiny Bridge**:
   - Convert React callbacks to CustomEvents
   - Handle input events and dispatch to Shiny
   - Manage component lifecycle with Shiny binding/unbinding

4. **Global API** (`src/index.ts`):
   - Functions to initialize React apps on DOM elements
   - Component registration and cleanup
   - Backwards-compatible API with Lit version

**Key Focus**: Exact same Shiny integration patterns as Lit version.

**Acceptance Criteria**:
- [ ] All CustomEvents fire with identical data structures
- [ ] Shiny message handlers work identically to Lit version
- [ ] HTML dependencies render correctly
- [ ] Error handling matches original behavior
- [ ] Multiple chat instances work independently


### Task 5: Bundle Creation & Testing

**Objective**: Create final single ESM bundle and comprehensive testing.

**Deliverables**:
1. Updated `build.ts` for single bundle output
2. Complete test suite validating React vs Lit behavior
3. Performance benchmarks
4. Browser compatibility testing
5. Final `shinychat.min.js` bundle

**Acceptance Criteria**:
- [ ] Single bundle contains everything needed
- [ ] All tests pass with >95% coverage
- [ ] Performance matches or exceeds Lit version
- [ ] Works in all target browsers

<!-- /HIDE -->

## Current file structure

Our working directory is the root of the project, which contains a `js/` folder that is the focus of this project and which contains the JavaScript source code for the chat and markdown stream components.
The current file structure is as follows:

```
js
├── README-REACT.md
├── README-markdown-stream.md
├── build.ts
├── demo-simple.html
├── demo.html
├── esbuild-metadata.json
├── eslint.config.js
├── package-lock.json
├── package.json
├── src
│   ├── __demos__ # Demos of new React components
│   │   └── markdown-stream
│   │       ├── MarkdownStreamDemo.tsx
│   │       ├── demo-simple.tsx
│   │       └── demo.tsx
│   ├── chat # Old lit implementation of Chat
│   │   ├── chat.scss
│   │   └── chat.ts
│   ├── components # New React components
│   │   ├── MarkdownStream.css
│   │   ├── MarkdownStream.tsx
│   │   └── __tests__
│   │       ├── MarkdownStream.integration.test.tsx
│   │       ├── MarkdownStream.test.tsx
│   │       └── test-setup.ts
│   ├── hello-world # Testing React setup
│   │   ├── HelloWorld.test.tsx
│   │   ├── HelloWorld.tsx
│   │   ├── hello-world.scss
│   │   └── hello-world.tsx
│   ├── markdown-stream # Old lit implementation of MarkdownStream
│   │   ├── highlight_styles.scss
│   │   ├── markdown-stream.scss
│   │   └── markdown-stream.ts
│   └── utils # old lit utilities
│       └── _utils.ts
├── tsconfig.json
├── vitest.config.ts
└── vitest.setup.ts
```

IMPORTANT: DO NOT USE THE `list_files` tool to list all of the files in `js/` unless you've included a regular expression to filter out irrelevant files, like `node_modules`, `dist`, or other generated files.
Assume the above information is correct and up-to-date at the start of our conversation.

## Running code

Use the tools available to you to your best ability.
If you need to run code, please output the code that should be run and ask me to run the code for you.
If you need the results, please ask me to run the code and provide the results.

## Small edits

For small one-to-three line edits, don't use the `write_text_file` tool.
Instead, please tell me what changes to make and I will make them for you.
Do use the `write_text_file` tool for larger edits, such as entire files or if providing the content for a file that doesn't already exist.

## Pause for collaboration

Before making any changes, explain the plan of action and ask for confirmation.
Pause between units of work to allow for collaboration and to confirm the next steps.
Remember: it's better to pause and confirm that a step is correct than to proceed forward with many incorrect changes.
Never guess: always ask for clarification if you're unsure about something.
