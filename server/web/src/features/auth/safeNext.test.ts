import { expect, test } from "vitest";
import { safeNext } from "./safeNext";

test.each([
  ["/users/7", "/users/7"],
  ["/users/7?tab=login", "/users/7?tab=login"],
  ["/", "/"],
])("keeps the same-site path %s", (next, expected) => {
  expect(safeNext(next)).toBe(expected);
});

test.each([
  null,
  "",
  "users",
  "//evil.example",
  "//evil.example/path",
  "/\\evil.example",
  "https://evil.example",
  "javascript:alert(1)",
  "/login",
  "/login?next=%2Flogin",
])("falls back to / for %s", (next) => {
  expect(safeNext(next)).toBe("/");
});
