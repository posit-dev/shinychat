import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["**/node_modules/**"],
    setupFiles: ["./vitest.setup.ts"],
  },
})
