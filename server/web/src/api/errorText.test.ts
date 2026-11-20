import { expect, test } from "vitest";
import i18n from "../i18n";
import errors from "../locales/en/errors.json";
import { ApiError } from "./ApiError";
import { errorText } from "./errorText";

const t = i18n.getFixedT("en", "errors");

function apiError(code: string, message = "server text") {
  return new ApiError({ status: 400, code, message });
}

test("translates by code", () => {
  expect(errorText(t, apiError("forbidden"))).toBe(errors.forbidden);
  expect(errorText(t, apiError("conflict"))).toBe(errors.conflict);
});

test("shows the server's message only for invalid_request", () => {
  expect(errorText(t, apiError("invalid_request", "must be shorter"))).toBe(
    "must be shorter",
  );
  expect(errorText(t, apiError("invalid_request", ""))).toBe(
    errors.invalid_request,
  );
  expect(errorText(t, apiError("conflict", "server says taken"))).toBe(
    errors.conflict,
  );
});

test("a code without a translation is the unknown text", () => {
  expect(errorText(t, apiError("brand_new_code"))).toBe(errors.unknown);
  expect(errorText(t, apiError("notify"))).toBe(errors.unknown);
});

test("an error that isn't an ApiError is the unknown text", () => {
  expect(errorText(t, new TypeError("boom"))).toBe(errors.unknown);
  expect(errorText(t, undefined)).toBe(errors.unknown);
});

test("a network failure has its own text", () => {
  const error = new ApiError({ status: 0, code: "network", message: "x" });
  expect(errorText(t, error)).toBe(errors.network);
});
