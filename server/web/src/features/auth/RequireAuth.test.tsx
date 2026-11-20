import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { App } from "../../App";
import { meErrorHandler, meFixture, meHandler } from "../../test/handlers/me";
import { LocationDisplay } from "../../test/LocationDisplay";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

function heading(name: string) {
  return screen.findByRole("heading", { level: 1, name });
}

test("a logged-in user sees the page", async () => {
  renderWithProviders(<App />, { route: "/account" });
  expect(await heading("Account")).toBeInTheDocument();
});

test("shows a loader until me arrives", () => {
  renderWithProviders(<App />, { route: "/account" });
  expect(screen.getByLabelText("Loading")).toBeInTheDocument();
});

test.each([
  [401, "unauthorized"],
  [403, "forbidden"],
])("the login redirect after a %i carries next", async (status, code) => {
  server.use(meErrorHandler(status, code));
  renderWithProviders(
    <>
      <App />
      <LocationDisplay />
    </>,
    { route: "/users/7?tab=login" },
  );
  await heading("Log in");
  expect(screen.getByTestId("location")).toHaveTextContent(
    "/login?next=%2Fusers%2F7%3Ftab%3Dlogin",
  );
});

test("must_change_password sends the user to change it", async () => {
  server.use(meHandler(meFixture({ must_change_password: true })));
  renderWithProviders(<App />, { route: "/devices" });
  expect(await heading("Change password")).toBeInTheDocument();
});

test.each(["/devices", "/users", "/server-settings", "/account"])(
  "must_change_password locks %s",
  async (route) => {
    server.use(meHandler(meFixture({ must_change_password: true })));
    renderWithProviders(<App />, { route });
    expect(await heading("Change password")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  },
);

test("a server failure offers a retry instead of a redirect", async () => {
  let calls = 0;
  server.use(
    http.get("*/api/me", () => {
      calls += 1;
      return calls === 1
        ? new HttpResponse(null, { status: 500 })
        : HttpResponse.json(meFixture());
    }),
  );
  const { user } = renderWithProviders(<App />, { route: "/account" });

  await user.click(await screen.findByRole("button", { name: "Try again" }));
  expect(await heading("Account")).toBeInTheDocument();
});

test("public pages don't ask who you are", async () => {
  server.use(meErrorHandler(401, "unauthorized"));
  renderWithProviders(<App />, { route: "/invite" });
  expect(await heading("Invitation")).toBeInTheDocument();
});
