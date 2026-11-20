import { afterEach, describe, expect, test } from "vitest";
import i18n, { syncDocumentLanguage } from ".";

type Tree = { [key: string]: string | Tree };

function flatKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string"
      ? [prefix + key]
      : flatKeys(value, `${prefix}${key}.`),
  );
}

const files = import.meta.glob<Tree>("../locales/*/*.json", {
  eager: true,
  import: "default",
});

const locales: Record<string, Record<string, Tree>> = {};
for (const [path, tree] of Object.entries(files)) {
  const [, language, namespace] = /locales\/([^/]+)\/([^/]+)\.json$/.exec(
    path,
  )!;
  locales[language] = { ...locales[language], [namespace]: tree };
}

const english = locales.en;
const others = Object.keys(locales).filter((language) => language !== "en");

describe("locale files", () => {
  test("English exists", () => {
    expect(english).toBeDefined();
  });

  test.each(others)("%s has no key English lacks", (language) => {
    for (const [namespace, tree] of Object.entries(locales[language])) {
      expect(english[namespace], `${language}/${namespace}.json`).toBeDefined();
      const known = new Set(flatKeys(english[namespace]));
      const extra = flatKeys(tree).filter((key) => !known.has(key));
      expect(extra, `${language}/${namespace}.json`).toEqual([]);
    }
  });
});

describe("<html lang>", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  test("follows the active language", async () => {
    document.documentElement.lang = "xx";
    await i18n.changeLanguage("en");
    expect(document.documentElement.lang).toBe("en");
  });

  test("syncDocumentLanguage sets it", () => {
    syncDocumentLanguage("de");
    expect(document.documentElement.lang).toBe("de");
  });
});

test("interpolated values are not HTML-escaped", () => {
  i18n.addResource("en", "common", "probe", "Hi {{name}}");
  // @ts-expect-error -- key added at runtime for this test only
  expect(i18n.t("probe", { name: "Tom & <Jerry>" })).toBe("Hi Tom & <Jerry>");
});
