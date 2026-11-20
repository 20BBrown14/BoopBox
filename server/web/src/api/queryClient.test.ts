import { notifications } from "@mantine/notifications";
import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { beforeEach, expect, type MockInstance, test, vi } from "vitest";
import { ApiError } from "./ApiError";
import { registerNavigation } from "./navigation";
import { createQueryClient } from "./queryClient";

const navigate = vi.fn();
let client: QueryClient;
let show: MockInstance<typeof notifications.show>;
let invalidate: MockInstance<QueryClient["invalidateQueries"]>;

function fail(status: number, code: string, field?: string): ApiError {
  return new ApiError({ status, code, message: "m", field });
}

async function run(
  error: ApiError,
  queryKey: QueryKey = ["users"],
): Promise<void> {
  await client
    .fetchQuery({
      queryKey,
      queryFn: () => Promise.reject(error),
    })
    .catch(() => undefined);
}

beforeEach(() => {
  navigate.mockReset();
  registerNavigation({
    navigate,
    location: { pathname: "/users/7", search: "?tab=login" },
  });
  client = createQueryClient();
  show = vi.spyOn(notifications, "show").mockReturnValue("id");
  invalidate = vi.spyOn(client, "invalidateQueries");
});

test("a 401 clears the cache and goes to login, remembering the page", async () => {
  client.setQueryData(["devices"], [1, 2]);
  await run(fail(401, "unauthorized"));

  expect(navigate).toHaveBeenCalledWith(
    "/login?next=%2Fusers%2F7%3Ftab%3Dlogin",
    {
      replace: true,
    },
  );
  expect(client.getQueryCache().getAll()).toEqual([]);
});

test("a 401 on the login page is left to the form", async () => {
  registerNavigation({
    navigate,
    location: { pathname: "/login", search: "" },
  });
  client.setQueryData(["devices"], [1, 2]);
  await run(fail(401, "unauthorized"));

  expect(navigate).not.toHaveBeenCalled();
  expect(client.getQueryData(["devices"])).toEqual([1, 2]);
});

test("a mutation's 401 redirects too", async () => {
  await client
    .getMutationCache()
    .build(client, {
      mutationFn: () => Promise.reject(fail(401, "unauthorized")),
    })
    .execute(undefined)
    .catch(() => undefined);
  expect(navigate).toHaveBeenCalledOnce();
});

test("a 403 notifies and refetches who you are", async () => {
  await run(fail(403, "forbidden"));
  expect(show).toHaveBeenCalledOnce();
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me"] });
  expect(navigate).not.toHaveBeenCalled();
});

test("a 403 that names a field is left to the form", async () => {
  await run(fail(403, "forbidden", "current_password"));
  expect(show).not.toHaveBeenCalled();
  expect(invalidate).not.toHaveBeenCalled();
});

test("a 403 on me doesn't refetch me", async () => {
  await run(fail(403, "forbidden"), ["me"]);
  expect(show).not.toHaveBeenCalled();
  expect(invalidate).not.toHaveBeenCalled();
});

test.each([
  [500, "unknown"],
  [503, "unknown"],
  [0, "network"],
])("a %i (%s) asks for a retry", async (status, code) => {
  await run(fail(status, code));
  expect(show).toHaveBeenCalledOnce();
  expect(navigate).not.toHaveBeenCalled();
});

test.each([404, 409, 422])("a %i is left to the screen", async (status) => {
  await run(fail(status, "not_found"));
  expect(show).not.toHaveBeenCalled();
  expect(navigate).not.toHaveBeenCalled();
  expect(invalidate).not.toHaveBeenCalled();
});

test("errors that aren't ApiErrors are ignored", async () => {
  await client
    .fetchQuery({
      queryKey: ["users"],
      queryFn: () => Promise.reject(new TypeError("boom")),
    })
    .catch(() => undefined);
  expect(show).not.toHaveBeenCalled();
  expect(navigate).not.toHaveBeenCalled();
});

test("queries don't retry a 4xx, and retry anything else twice", () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry;
  if (typeof retry !== "function") throw new Error("retry isn't a function");
  expect(retry(0, fail(404, "not_found"))).toBe(false);
  expect(retry(0, fail(401, "unauthorized"))).toBe(false);
  expect(retry(0, fail(500, "unknown"))).toBe(true);
  expect(retry(1, fail(0, "network"))).toBe(true);
  expect(retry(2, fail(500, "unknown"))).toBe(false);
});

test("mutations aren't retried", () => {
  expect(
    createQueryClient().getDefaultOptions().mutations?.retry,
  ).toBeUndefined();
});
