import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    include: ["**/*.{test,spec}.{ts,tsx}"],
    exclude: [
      "node_modules/**",
      "dist/**",
      "src/markdown-stream/**", // Exclude Lit components
      "src/chat/**", // Exclude Lit components
      "src/utils/**", // Exclude Lit utilities
    ],
  },
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "preact",
    jsxDev: false,
  },
  resolve: {
    alias: {
      react: "preact/compat",
      "react-dom": "preact/compat",
      "react/jsx-runtime": "preact/jsx-runtime",
    },
  },
})
