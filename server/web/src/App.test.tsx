import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { App } from "./App";
import { renderWithProviders } from "./test/render";

function heading(name: string) {
  return screen.getByRole("heading", { level: 1, name });
}

test("renders inside the providers", () => {
  renderWithProviders(<App />);
  expect(document.documentElement).toHaveAttribute("data-mantine-color-scheme");
});

test("/ redirects to the devices page", () => {
  renderWithProviders(<App />, { route: "/" });
  expect(heading("Devices")).toBeInTheDocument();
});

describe("routes inside the layout", () => {
  test.each([
    ["/devices", "Devices"],
    ["/devices/boop-1", "Device"],
    ["/users", "Users"],
    ["/users/7", "User"],
    ["/server-settings", "Server settings"],
    ["/account", "Account"],
  ])("%s", (route, title) => {
    renderWithProviders(<App />, { route });
    expect(heading(title)).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Main" }),
    ).toBeInTheDocument();
  });
});

describe("routes outside the layout", () => {
  test.each([
    ["/login", "Log in"],
    ["/change-password", "Change password"],
    ["/invite", "Invitation"],
  ])("%s", (route, title) => {
    renderWithProviders(<App />, { route });
    expect(heading(title)).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

test("an unknown path renders NotFound", () => {
  renderWithProviders(<App />, { route: "/no/such/page" });
  expect(heading("Page not found")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to devices" })).toHaveAttribute(
    "href",
    "/devices",
  );
});
