import auth from "../locales/en/auth.json";
import common from "../locales/en/common.json";
import errors from "../locales/en/errors.json";

/** English is bundled and is the source of truth for keys. */
export const resources = { common, auth, errors } as const;

export type Namespace = keyof typeof resources;

export const defaultNS: Namespace = "common";
