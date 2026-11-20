import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import resourcesToBackend from "i18next-resources-to-backend";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LANGUAGE, LANGUAGES } from "./languages";
import { defaultNS, resources } from "./resources";

export const LANGUAGE_STORAGE_KEY = "boopbox.language";

export function syncDocumentLanguage(language: string) {
  document.documentElement.lang = language;
}

i18n.on("languageChanged", syncDocumentLanguage);

void i18n
  .use(LanguageDetector)
  // Non-English languages are separate chunks, fetched when chosen.
  .use(
    resourcesToBackend(
      (language: string, namespace: string) =>
        import(`../locales/${language}/${namespace}.json`),
    ),
  )
  .use(initReactI18next)
  .init({
    resources: { [DEFAULT_LANGUAGE]: resources },
    partialBundledLanguages: true,
    initAsync: false,
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs: LANGUAGES.map((language) => language.code),
    load: "languageOnly",
    ns: Object.keys(resources),
    defaultNS,
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ["localStorage"],
    },
    // React escapes rendered text; escaping here too would show "&amp;".
    interpolation: { escapeValue: false },
  });

export default i18n;
