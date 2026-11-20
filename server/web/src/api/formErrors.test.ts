import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, type MockInstance, test, vi } from "vitest";
import i18n from "../i18n";
import errors from "../locales/en/errors.json";
import { ApiError } from "./ApiError";
import { applyApiError } from "./formErrors";

const t = i18n.getFixedT("en", "errors");
let show: MockInstance<typeof notifications.show>;

function renderForm() {
  return renderHook(() =>
    useForm({
      initialValues: { username: "", grants: { devices: { "boop-1": [] } } },
    }),
  ).result;
}

function apiError(status: number, code: string, field?: string) {
  return new ApiError({ status, code, message: "server text", field });
}

beforeEach(() => {
  show = vi.spyOn(notifications, "show").mockReturnValue("id");
});

test("an error naming a form field goes under that field", () => {
  const form = renderForm();
  act(() =>
    applyApiError(form.current, apiError(409, "conflict", "username"), t),
  );
  expect(form.current.errors).toEqual({ username: errors.conflict });
  expect(show).not.toHaveBeenCalled();
});

test("a dotted field path reaches a nested field", () => {
  const form = renderForm();
  const error = apiError(422, "invalid_request", "grants.devices.boop-1");
  act(() => applyApiError(form.current, error, t));
  expect(form.current.errors).toEqual({
    "grants.devices.boop-1": "server text",
  });
});

test("a field the form doesn't have becomes a notification", () => {
  const form = renderForm();
  act(() => applyApiError(form.current, apiError(409, "conflict", "email"), t));
  expect(form.current.errors).toEqual({});
  expect(show).toHaveBeenCalledWith(
    expect.objectContaining({ message: errors.conflict }),
  );
});

test("an error without a field becomes a notification", () => {
  const form = renderForm();
  act(() => applyApiError(form.current, apiError(404, "not_found"), t));
  expect(show).toHaveBeenCalledWith(
    expect.objectContaining({ message: errors.not_found }),
  );
});

test.each([
  [401, "unauthorized"],
  [403, "forbidden"],
  [500, "unknown"],
  [0, "network"],
])("a %i the query client already reacts to is left alone", (status, code) => {
  const form = renderForm();
  act(() => applyApiError(form.current, apiError(status, code), t));
  expect(show).not.toHaveBeenCalled();
  expect(form.current.errors).toEqual({});
});

test("an error that isn't an ApiError is a generic notification", () => {
  const form = renderForm();
  act(() => applyApiError(form.current, new TypeError("boom"), t));
  expect(show).toHaveBeenCalledWith(
    expect.objectContaining({ message: errors.unknown }),
  );
});
