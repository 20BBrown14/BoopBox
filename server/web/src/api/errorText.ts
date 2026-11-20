import type { TFunction } from "i18next";
import { resources } from "../i18n/resources";
import { ApiError } from "./ApiError";

type Errors = typeof resources.errors;
type ErrorKey = {
  [K in keyof Errors]: Errors[K] extends string ? K : never;
}[keyof Errors];

function isErrorKey(code: string): code is ErrorKey {
  return (
    typeof (resources.errors as Record<string, unknown>)[code] === "string"
  );
}

/**
 * Text for an error, chosen by its code. Only `invalid_request` shows the
 * server's own (English) message, for details that have no translation yet.
 */
export function errorText(t: TFunction<"errors">, error: unknown): string {
  if (!(error instanceof ApiError)) return t("unknown");
  if (error.code === "invalid_request" && error.message) return error.message;
  return isErrorKey(error.code) ? t(error.code) : t("unknown");
}
