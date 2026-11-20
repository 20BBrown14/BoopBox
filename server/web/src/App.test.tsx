import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { App } from "./App";
import { meErrorHandler } from "./test/handlers/me";
import { renderWithProviders } from "./test/render";
import { server } from "./test/server";

function heading(name: string) {
  return screen.findByRole("heading", { level: 1, name });
}

test("renders inside the providers", () => {
  renderWithProviders(<App />);
  expect(document.documentElement).toHaveAttribute("data-mantine-color-scheme");
});

test("/ redirects to the devices page", async () => {
  renderWithProviders(<App />, { route: "/" });
  expect(await heading("Devices")).toBeInTheDocument();
});

describe("routes inside the layout", () => {
  test.each([
    ["/devices", "Devices"],
    ["/devices/boop-1", "Device"],
    ["/users", "Users"],
    ["/users/7", "User"],
    ["/server-settings", "Server settings"],
    ["/account", "Account"],
  ])("%s", async (route, title) => {
    renderWithProviders(<App />, { route });
    expect(await heading(title)).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Main" }),
    ).toBeInTheDocument();
  });
});

describe("routes outside the layout", () => {
  test.each([
    ["/login", "Log in"],
    ["/invite", "Invitation"],
  ])("%s", async (route, title) => {
    server.use(meErrorHandler(401, "unauthorized"));
    renderWithProviders(<App />, { route });
    expect(await heading(title)).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("/change-password", async () => {
    renderWithProviders(<App />, { route: "/change-password" });
    expect(await heading("Change password")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

test("an unknown path renders NotFound", async () => {
  renderWithProviders(<App />, { route: "/no/such/page" });
  expect(await heading("Page not found")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to devices" })).toHaveAttribute(
    "href",
    "/devices",
  );
});
