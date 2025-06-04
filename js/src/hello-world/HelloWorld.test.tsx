import { render, screen, fireEvent } from "@testing-library/preact"
import { HelloWorld } from "./HelloWorld"

describe("HelloWorld", () => {
  test("renders hello message", () => {
    render(<HelloWorld />)
    expect(screen.getByText("Hello World!")).toBeInTheDocument()
  })

  test("renders custom name", () => {
    render(<HelloWorld name="React" />)
    expect(screen.getByText("Hello React!")).toBeInTheDocument()
  })

  test("increments counter on button click", () => {
    render(<HelloWorld />)

    const button = screen.getByRole("button", { name: /click me/i })
    const counter = screen.getByText("You clicked 0 times")

    expect(counter).toBeInTheDocument()

    fireEvent.click(button)
    expect(screen.getByText("You clicked 1 times")).toBeInTheDocument()

    fireEvent.click(button)
    expect(screen.getByText("You clicked 2 times")).toBeInTheDocument()
  })
})
