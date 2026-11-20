/** Languages that ship. Names are endonyms, so they aren't translated. */
export const LANGUAGES = [{ code: "en", name: "English" }] as const;

export type LanguageCode = (typeof LANGUAGES)[number]["code"];

export const DEFAULT_LANGUAGE: LanguageCode = "en";
