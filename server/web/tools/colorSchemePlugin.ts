import { ColorSchemeScript } from "@mantine/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Plugin } from "vite";

const FILE_NAME = "color-scheme.js";

/** The body of Mantine's own ColorSchemeScript, for the app's settings. */
export function colorSchemeSource(): string {
  const markup = renderToStaticMarkup(
    createElement(ColorSchemeScript, { defaultColorScheme: "auto" }),
  );
  const body = /^<script[^>]*>([\s\S]*)<\/script>$/.exec(markup)?.[1];
  if (!body) throw new Error(`unexpected ColorSchemeScript markup: ${markup}`);
  return body;
}

/**
 * Serves Mantine's ColorSchemeScript as /color-scheme.js instead of inline,
 * so the CSP can keep script-src 'self'. index.html loads it in the <head>.
 */
export function colorSchemePlugin(): Plugin {
  const source = colorSchemeSource();
  return {
    name: "boopbox-color-scheme",
    configureServer(server) {
      server.middlewares.use(`/${FILE_NAME}`, (_request, response) => {
        response.setHeader("Content-Type", "text/javascript");
        response.end(source);
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: FILE_NAME, source });
    },
    transformIndexHtml(_html, context) {
      if (!context.server) return;
      // Dev only: Vite injects CSS from JS after first paint, so the page
      // would flash unstyled. A build links its stylesheet in the <head>.
      return [
        {
          tag: "link",
          attrs: {
            rel: "stylesheet",
            href: "/node_modules/@mantine/core/styles.css",
          },
          injectTo: "head",
        },
      ];
    },
  };
}
