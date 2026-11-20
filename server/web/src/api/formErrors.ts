import type { UseFormReturnType } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import type { TFunction } from "i18next";
import { ApiError } from "./ApiError";
import { errorText } from "./errorText";
import { globalReaction } from "./queryClient";

function hasPath(values: unknown, path: string): boolean {
  let node: unknown = values;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === null || !(part in node)) {
      return false;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return true;
}

/**
 * Shows a failed submit's error under the field the server names, or as a
 * notification when it names none of this form's fields. Errors the query
 * client already reacted to (sign out, no permission, retry) are left alone.
 */
export function applyApiError<Values>(
  form: UseFormReturnType<Values>,
  error: unknown,
  t: TFunction<"errors">,
): void {
  if (
    error instanceof ApiError &&
    error.field !== undefined &&
    hasPath(form.getValues(), error.field)
  ) {
    form.setFieldError(error.field, errorText(t, error));
    return;
  }
  if (globalReaction(error) !== null) return;
  notifications.show({ color: "red", message: errorText(t, error) });
}
