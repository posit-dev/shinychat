import { defineConfig, globalIgnores } from "eslint/config"
import globals from "globals"
import { fixupConfigRules, fixupPluginRules } from "@eslint/compat"
import tsParser from "@typescript-eslint/parser"
import react from "eslint-plugin-react"
import typescriptEslint from "@typescript-eslint/eslint-plugin"

import { fileURLToPath } from "url"
import { dirname } from "path"
import { FlatCompat } from "@eslint/eslintrc"
import js from "@eslint/js"

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const compat = new FlatCompat({
  baseDirectory: __dirname,
  recommendedConfig: js.configs.recommended,
  allConfig: js.configs.all,
})

export default defineConfig([
  {
    languageOptions: {
      globals: {
        ...globals.browser,
      },

      parser: tsParser,
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: {},
    },

    extends: fixupConfigRules(
      compat.extends(
        "eslint:recommended",
        "plugin:react/recommended",
        "plugin:@typescript-eslint/eslint-recommended",
        "plugin:@typescript-eslint/recommended",
        "plugin:react-hooks/recommended",
        "plugin:prettier/recommended",
        "prettier",
      ),
    ),

    plugins: {
      react: fixupPluginRules(react),
      "@typescript-eslint": fixupPluginRules(typescriptEslint),
    },

    rules: {
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "prettier/prettier": "error",
      // Disable the React in scope rule for new JSX transform
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-react": "off",
    },

    ignores: [
      "dist/**",
      "node_modules/**",
      "src/markdown-stream/**", // Ignore Lit components
      "src/chat/**", // Ignore Lit components
      "src/utils/**", // Ignore Lit utilities
    ],

    settings: {
      react: {
        version: "detect",
      },
    },
  },
  globalIgnores(["dist/*"]),
])
