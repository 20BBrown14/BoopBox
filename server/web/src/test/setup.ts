import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// MSW's "error" mode only fails the request, which code under test may swallow.
// Collecting them here fails the test regardless.
const unhandled: string[] = [];

beforeAll(() => {
  server.listen({
    onUnhandledFrame({ frame, defaults }) {
      const { request } = frame.data as { request?: Request };
      unhandled.push(
        request ? `${request.method} ${request.url}` : frame.protocol,
      );
      defaults.error();
    },
  });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  if (unhandled.length > 0) {
    const requests = unhandled.splice(0).join(", ");
    throw new Error(`Request without an MSW handler: ${requests}`);
  }
});

afterAll(() => {
  server.close();
});

// jsdom has neither; Mantine needs both.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;
