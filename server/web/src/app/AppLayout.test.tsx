import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "../App";
import { renderWithProviders } from "../test/render";

// jsdom applies Mantine's `hidden-from-sm` display:none at every width, and
// role queries can't name a hidden element, so look it up by its aria-label.
function burger(name: "Open navigation" | "Close navigation") {
  return screen.getByLabelText(name);
}

test("lists the nav items and marks the current one", () => {
  renderWithProviders(<App />, { route: "/users/7" });
  const nav = screen.getByRole("navigation", { name: "Main" });
  const links = Array.from(nav.querySelectorAll("a")).map((a) => [
    a.textContent,
    a.getAttribute("href"),
  ]);
  expect(links).toEqual([
    ["Devices", "/devices"],
    ["Users", "/users"],
    ["Server settings", "/server-settings"],
    ["Account", "/account"],
  ]);
  expect(screen.getByRole("link", { name: "Users" })).toHaveAttribute(
    "data-active",
    "true",
  );
  expect(screen.getByRole("link", { name: "Devices" })).not.toHaveAttribute(
    "data-active",
  );
});

test("the burger toggles the nav", async () => {
  const { user } = renderWithProviders(<App />, { route: "/devices" });
  expect(burger("Open navigation")).toHaveAttribute("aria-expanded", "false");

  await user.click(burger("Open navigation"));
  expect(burger("Close navigation")).toHaveAttribute("aria-expanded", "true");

  await user.click(burger("Close navigation"));
  expect(burger("Open navigation")).toHaveAttribute("aria-expanded", "false");
});

test("choosing a nav item navigates and closes the nav", async () => {
  const { user } = renderWithProviders(<App />, { route: "/devices" });
  await user.click(burger("Open navigation"));

  await user.click(screen.getByRole("link", { name: "Account" }));

  expect(
    screen.getByRole("heading", { level: 1, name: "Account" }),
  ).toBeInTheDocument();
  expect(burger("Open navigation")).toHaveAttribute("aria-expanded", "false");
});
