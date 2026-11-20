import createClient, { type Middleware } from "openapi-fetch";
import { apiErrorFromResponse, networkError } from "./ApiError";
import type { paths } from "./schema";

export const CSRF_COOKIE = "boopbox_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  const entry = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(prefix));
  return entry === undefined
    ? undefined
    : decodeURIComponent(entry.slice(prefix.length));
}

/** Failures throw an ApiError, so they reach TanStack Query as errors. */
const middleware: Middleware = {
  onRequest({ request }) {
    if (WRITE_METHODS.has(request.method)) {
      const token = readCookie(CSRF_COOKIE);
      if (token) request.headers.set(CSRF_HEADER, token);
    }
  },
  async onResponse({ response }) {
    if (!response.ok) throw await apiErrorFromResponse(response);
  },
  onError({ error }) {
    // A cancelled request isn't a failure.
    if (error instanceof DOMException && error.name === "AbortError") {
      return error;
    }
    return networkError(error);
  },
};

/**
 * The body of a successful call. Failures already threw, so a missing body is
 * a route that returned nothing where the schema promised something.
 */
export function bodyOf<T>(result: { data?: T }): T {
  if (result.data === undefined) throw new Error("response had no body");
  return result.data;
}

export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  // Looked up per call, so a test's fetch mock is picked up.
  fetch: (request) => globalThis.fetch(request),
});

api.use(middleware);
