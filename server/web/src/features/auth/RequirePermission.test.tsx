import { screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { App } from "../../App";
import { meFixture, meHandler, userFixture } from "../../test/handlers/me";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

async function navLabels() {
  const nav = await screen.findByRole("navigation", { name: "Main" });
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

describe("nav", () => {
  test("the owner sees every item", async () => {
    server.use(meHandler(meFixture()));
    renderWithProviders(<App />, { route: "/devices" });
    expect(await navLabels()).toEqual([
      "Devices",
      "Users",
      "Server settings",
      "Account",
    ]);
  });

  test("a user without grants sees devices and account only", async () => {
    server.use(meHandler(userFixture()));
    renderWithProviders(<App />, { route: "/devices" });
    expect(await navLabels()).toEqual(["Devices", "Account"]);
  });

  test("each grant shows its item", async () => {
    server.use(meHandler(userFixture({ global: ["users.manage"] })));
    renderWithProviders(<App />, { route: "/devices" });
    expect(await navLabels()).toEqual(["Devices", "Users", "Account"]);
  });

  test("a device grant doesn't show a global item", async () => {
    server.use(
      meHandler(userFixture({ devices: { "boop-1": ["users.manage"] } })),
    );
    renderWithProviders(<App />, { route: "/devices" });
    expect(await navLabels()).toEqual(["Devices", "Account"]);
  });
});

describe("guarded pages", () => {
  test.each(["/users", "/users/7", "/server-settings"])(
    "%s without the permission shows NoPermission",
    async (route) => {
      server.use(meHandler(userFixture()));
      renderWithProviders(<App />, { route });
      expect(
        await screen.findByRole("heading", { level: 1, name: "No permission" }),
      ).toBeInTheDocument();
    },
  );

  test("with the permission the page renders", async () => {
    server.use(meHandler(userFixture({ global: ["server_settings.manage"] })));
    renderWithProviders(<App />, { route: "/server-settings" });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Server settings" }),
    ).toBeInTheDocument();
  });
});
