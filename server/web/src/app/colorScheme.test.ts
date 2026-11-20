import { beforeEach, expect, test, vi } from "vitest";
import { colorSchemeSource } from "../../tools/colorSchemePlugin";

const source = colorSchemeSource();

function run({
  stored,
  prefersDark,
}: {
  stored?: string;
  prefersDark: boolean;
}) {
  if (stored) localStorage.setItem("mantine-color-scheme-value", stored);
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query) =>
      ({
        matches: prefersDark && query === "(prefers-color-scheme: dark)",
      }) as MediaQueryList,
  );
  window.eval(source);
  return document.documentElement.getAttribute("data-mantine-color-scheme");
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
});

test("defaults to auto, following the OS", () => {
  expect(run({ prefersDark: true })).toBe("dark");
  expect(run({ prefersDark: false })).toBe("light");
});

test("a stored choice wins over the OS", () => {
  expect(run({ stored: "light", prefersDark: true })).toBe("light");
});
