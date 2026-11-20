import js from "@eslint/js";
import eslintReact from "@eslint-react/eslint-plugin";
import i18next from "eslint-plugin-i18next";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

const testFiles = ["**/*.test.{ts,tsx}", "src/test/**"];

// eslint-plugin-react's jsx-boolean-value does not support ESLint 10 and
// @eslint-react has no equivalent, so this is a minimal local version.
const requireExplicitBoolean = {
  meta: {
    type: "suggestion",
    fixable: "code",
    schema: [],
    messages: {
      explicit: "Write `{{name}}={true}` instead of the shorthand `{{name}}`.",
    },
  },
  create(context) {
    return {
      JSXAttribute(node) {
        if (node.value !== null) return;
        const name = context.sourceCode.getText(node.name);
        context.report({
          node,
          messageId: "explicit",
          data: { name },
          fix: (fixer) => fixer.insertTextAfter(node, "={true}"),
        });
      },
    };
  },
};

export default defineConfig([
  globalIgnores(["dist", "src/api/schema.d.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
    ],
    plugins: {
      "@eslint-react": eslintReact,
      local: { rules: { "explicit-boolean-prop": requireExplicitBoolean } },
    },
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
      "local/explicit-boolean-prop": "error",
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
