import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { colorSchemePlugin } from "./tools/colorSchemePlugin.ts";

export default defineConfig({
  plugins: [react(), colorSchemePlugin()],
  server: {
    // Same origin in dev as in production, so cookies and CSRF behave the same.
    proxy: { "/api": "http://127.0.0.1:9685" },
  },
});
