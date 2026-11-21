import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../../App";
import i18n from "../../i18n";
import { meFixture, meHandler } from "../../test/handlers/me";
import { LocationDisplay } from "../../test/LocationDisplay";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

// A second language, since only English ships so far.
vi.mock("../../i18n/languages", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../../i18n/languages")>();
  return {
    ...original,
    LANGUAGES: [...original.LANGUAGES, { code: "xx", name: "Test language" }],
  };
});

afterEach(async () => {
  await i18n.changeLanguage("en");
  localStorage.clear();
});

/** Records the session calls; `me` answers 401 after a logout. */
function sessionServer() {
  let loggedIn = true;
  const calls: string[] = [];
  server.use(
    http.get("*/api/me", () =>
      loggedIn
        ? HttpResponse.json(meFixture())
        : HttpResponse.json(
            { code: "unauthorized", message: "authentication required" },
            { status: 401 },
          ),
    ),
    http.post("*/api/auth/logout", () => {
      calls.push("logout");
      loggedIn = false;
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("*/api/auth/logout-all", () => {
      calls.push("logout-all");
      return HttpResponse.json({ must_change_password: false });
    }),
  );
  return { calls };
}

function renderAccount() {
  return renderWithProviders(
    <>
      <App />
      <LocationDisplay />
    </>,
    { route: "/account" },
  );
}

function location() {
  return screen.getByTestId("location");
}

async function section(name: string) {
  return within(await screen.findByRole("region", { name }));
}

test("shows the display name and local username", async () => {
  renderAccount();
  const login = await section("Your login");
  expect(login.getByText("Owner")).toBeInTheDocument();
  expect(login.getByText("owner")).toBeInTheDocument();
});

test("an external login shows its label and no password change", async () => {
  server.use(
    meHandler(
      meFixture({
        login: { provider: "google", username: null, label: "me@example.com" },
      }),
    ),
  );
  renderAccount();
  const login = await section("Your login");
  expect(login.getByText("me@example.com")).toBeInTheDocument();
  expect(
    login.queryByRole("link", { name: "Change password" }),
  ).not.toBeInTheDocument();
});

test("change password comes back to the account page", async () => {
  renderAccount();
  const login = await section("Your login");
  expect(login.getByRole("link", { name: "Change password" })).toHaveAttribute(
    "href",
    "/change-password?next=%2Faccount",
  );
});

test("logging out clears the cache and goes to the login page", async () => {
  const { calls } = sessionServer();
  const { user, queryClient } = renderAccount();
  const sessions = await section("Sessions");
  await user.click(sessions.getByRole("button", { name: "Log out" }));
  expect(
    await screen.findByRole("heading", { level: 1, name: "Log in" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent(/^\/login$/);
  expect(calls).toEqual(["logout"]);
  expect(queryClient.getQueryData(["me"])).toBeUndefined();
});

test("logging out everywhere asks first", async () => {
  const { calls } = sessionServer();
  const { user } = renderAccount();
  const sessions = await section("Sessions");
  await user.click(
    sessions.getByRole("button", { name: "Log out everywhere" }),
  );
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByText("Log out everywhere?")).toBeInTheDocument();
  expect(calls).toEqual([]);
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(calls).toEqual([]);
});

test("confirming logs out everywhere and stays here", async () => {
  const { calls } = sessionServer();
  const { user } = renderAccount();
  const sessions = await section("Sessions");
  await user.click(
    sessions.getByRole("button", { name: "Log out everywhere" }),
  );
  const dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("button", { name: "Log out everywhere" }));
  expect(
    await screen.findByText("Logged out everywhere else."),
  ).toBeInTheDocument();
  expect(calls).toEqual(["logout-all"]);
  expect(location()).toHaveTextContent(/^\/account$/);
});

test("changing language updates the text and <html lang>", async () => {
  const supported = i18n.options.supportedLngs as string[];
  supported.push("xx");
  i18n.addResourceBundle("xx", "account", { title: "Konto" });
  try {
    const { user } = renderAccount();
    const preferences = await section("Preferences");
    await user.selectOptions(preferences.getByLabelText("Language"), "xx");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Konto" }),
    ).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("xx");
  } finally {
    supported.splice(supported.indexOf("xx"), 1);
    i18n.removeResourceBundle("xx", "account");
  }
});

test("the color scheme can be chosen", async () => {
  const { user } = renderAccount();
  const preferences = await section("Preferences");
  await user.click(preferences.getByLabelText("Dark"));
  expect(document.documentElement).toHaveAttribute(
    "data-mantine-color-scheme",
    "dark",
  );
});
