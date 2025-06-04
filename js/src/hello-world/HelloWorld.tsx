import { useState } from "preact/hooks"

interface HelloWorldProps {
  name?: string
}

export function HelloWorld({ name = "World" }: HelloWorldProps) {
  const [count, setCount] = useState(0)

  return (
    <div className="hello-world">
      <h1>Hello {name}!</h1>
      <p>You clicked {count} times</p>
      <button onClick={() => setCount(count + 1)} className="btn btn-primary">
        Click me
      </button>
    </div>
  )
}
