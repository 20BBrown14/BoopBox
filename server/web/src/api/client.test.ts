import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test } from "vitest";
import { server } from "../test/server";
import { ApiError } from "./ApiError";
import { api } from "./client";

const ME = {
  id: 1,
  display_name: "Owner",
  is_owner: true,
  must_change_password: false,
  login: null,
  permissions: { global: [], devices: {} },
};

beforeEach(() => {
  document.cookie = "boopbox_csrf=token-123; path=/";
});

afterEach(() => {
  document.cookie = "boopbox_csrf=; path=/; max-age=0";
});

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => undefined,
    (caught: unknown) => caught,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

test("a success returns its data", async () => {
  server.use(http.get("*/api/me", () => HttpResponse.json(ME)));
  const { data } = await api.GET("/api/me");
  expect(data).toEqual(ME);
});

test("writes carry the CSRF header from the cookie", async () => {
  let seen: string | null = "unset";
  server.use(
    http.post("*/api/auth/logout", ({ request }) => {
      seen = request.headers.get("X-CSRF-Token");
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await api.POST("/api/auth/logout");
  expect(seen).toBe("token-123");
});

test("reads don't", async () => {
  let seen: string | null = "unset";
  server.use(
    http.get("*/api/me", ({ request }) => {
      seen = request.headers.get("X-CSRF-Token");
      return HttpResponse.json(ME);
    }),
  );
  await api.GET("/api/me");
  expect(seen).toBeNull();
});

test("a write without the cookie sends no header", async () => {
  document.cookie = "boopbox_csrf=; path=/; max-age=0";
  let seen: string | null = "unset";
  server.use(
    http.post("*/api/auth/logout", ({ request }) => {
      seen = request.headers.get("X-CSRF-Token");
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await api.POST("/api/auth/logout");
  expect(seen).toBeNull();
});

test("an error response becomes an ApiError", async () => {
  server.use(
    http.get("*/api/me", () =>
      HttpResponse.json(
        {
          code: "invalid_request",
          message: "must be at most 64 characters",
          field: "display_name",
        },
        { status: 422 },
      ),
    ),
  );
  const error = await failure(api.GET("/api/me"));
  expect(error).toMatchObject({
    status: 422,
    code: "invalid_request",
    message: "must be at most 64 characters",
    field: "display_name",
  });
});

test("an error without a field has none", async () => {
  server.use(
    http.get("*/api/me", () =>
      HttpResponse.json(
        { code: "forbidden", message: "not allowed" },
        { status: 403 },
      ),
    ),
  );
  const error = await failure(api.GET("/api/me"));
  expect(error.field).toBeUndefined();
});

test.each([
  ["plain text", new HttpResponse("Internal Server Error", { status: 500 })],
  ["another JSON shape", HttpResponse.json({ detail: "x" }, { status: 502 })],
  ["an empty body", new HttpResponse(null, { status: 503 })],
])("%s falls back to an unknown error", async (_name, response) => {
  server.use(http.get("*/api/me", () => response.clone()));
  const error = await failure(api.GET("/api/me"));
  expect(error.code).toBe("unknown");
  expect(error.status).toBe(response.status);
});

test("a failed connection becomes a network error", async () => {
  server.use(http.get("*/api/me", () => HttpResponse.error()));
  const error = await failure(api.GET("/api/me"));
  expect(error).toMatchObject({ status: 0, code: "network" });
});
