import js from "@eslint/js";
import eslintReact from "@eslint-react/eslint-plugin";
import i18next from "eslint-plugin-i18next";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const testFiles = ["**/*.test.{ts,tsx}", "src/test/**"];

export default defineConfig([
  globalIgnores(["dist", "src/api/schema.d.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
    ],
    plugins: { "@eslint-react": eslintReact },
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@eslint-react/dom-no-dangerously-set-innerhtml": "error",
      "@eslint-react/dom-no-dangerously-set-innerhtml-with-children": "error",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: testFiles,
    plugins: { i18next },
    rules: {
      // JSX text plus the props that carry visible text. Other props
      // (variant, size, to, ...) are configuration, not copy.
      "i18next/no-literal-string": [
        "error",
        {
          mode: "jsx-only",
          "jsx-attributes": {
            include: [
              "label",
              "description",
              "placeholder",
              "title",
              "error",
              "alt",
              "aria-label",
            ],
            exclude: [],
          },
        },
      ],
    },
  },
]);
