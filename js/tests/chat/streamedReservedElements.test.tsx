import { describe, it, expect, beforeEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

beforeEach(() => {
  installShinyWindowStub()
})

function renderChat(transport: ReturnType<typeof createMockTransport>) {
  return render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId="test-chat"
      inputId="test-input"
      uploadAccept={["image/png"]}
      maxUploadSize={30000000}
    />,
  )
}

// A streamed tag name arrives split across chunks. Escaping on the server
// would inspect each chunk separately and miss it; the browser reassembles the
// block before parsing, which is why the escape lives on the client.
describe("a reserved element streamed across chunk boundaries", () => {
  it("stays inert when the tag name is split mid-stream", () => {
    const transport = createMockTransport()
    const { container } = renderChat(transport)

    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })

    for (const piece of [
      "<shinychat-raw",
      "-html><img src=x onerror",
      "=alert(1)></shinychat-raw-html>",
    ]) {
      act(() => {
        transport.fire("test-chat", {
          type: "chunk",
          content: piece,
          operation: "append",
          content_type: "markdown",
        })
      })
    }

    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(container.querySelector("[onerror]")).toBeNull()
    expect(container.innerHTML).not.toContain("onerror")
    expect(container.textContent).toContain("shinychat-raw-html")
  })
})
