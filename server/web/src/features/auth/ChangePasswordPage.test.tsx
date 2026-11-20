import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { App } from "../../App";
import type { components } from "../../api/schema";
import { meErrorHandler, meFixture } from "../../test/handlers/me";
import { LocationDisplay } from "../../test/LocationDisplay";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

type PasswordBody = components["schemas"]["PasswordChangeRequest"];
type ErrorBody = { code: string; message: string; field?: string };

const CURRENT = "the-old-password";
const NEW = "a-brand-new-password";

/** One logged-in user; the password change clears `must_change_password`. */
function passwordServer({ mustChange }: { mustChange: boolean }) {
  let loggedIn = true;
  const posted: PasswordBody[] = [];
  server.use(
    http.get("*/api/me", () => {
      return loggedIn
        ? HttpResponse.json(meFixture({ must_change_password: mustChange }))
        : HttpResponse.json(
            { code: "unauthorized", message: "authentication required" },
            { status: 401 },
          );
    }),
    http.post<never, PasswordBody, ErrorBody | { must_change_password: false }>(
      "*/api/auth/password",
      async ({ request }) => {
        const body = await request.json();
        posted.push(body);
        if (body.current_password !== CURRENT) {
          return HttpResponse.json(
            {
              code: "forbidden",
              message: "current password is incorrect",
              field: "current_password",
            },
            { status: 403 },
          );
        }
        mustChange = false;
        return HttpResponse.json({ must_change_password: false });
      },
    ),
    http.post("*/api/auth/logout", () => {
      loggedIn = false;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { posted };
}

function renderPage(route = "/change-password") {
  return renderWithProviders(
    <>
      <App />
      <LocationDisplay />
    </>,
    { route },
  );
}

type User = ReturnType<typeof renderPage>["user"];

async function fill(user: User, current: string, next: string, confirm = next) {
  await user.type(await screen.findByLabelText(/^Current password/), current);
  await user.type(screen.getByLabelText(/^New password/), next);
  await user.type(screen.getByLabelText(/^Confirm new password/), confirm);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

function location() {
  return screen.getByTestId("location");
}

test("forced mode explains why and only offers logging out", async () => {
  passwordServer({ mustChange: true });
  renderPage("/change-password?next=%2Fdevices");
  expect(
    await screen.findByText(
      "You need to choose a new password before you can continue.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  expect(screen.queryAllByRole("link")).toEqual([]);
  const form = screen
    .getByRole("heading", { name: "Change password" })
    .closest("form") as HTMLElement;
  expect(
    within(form)
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((text) => text),
  ).toEqual(["Change password", "Log out"]);
});

test("logging out from forced mode goes to the login page", async () => {
  passwordServer({ mustChange: true });
  const { user, queryClient } = renderPage();
  await user.click(await screen.findByRole("button", { name: "Log out" }));
  expect(
    await screen.findByRole("heading", { level: 1, name: "Log in" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent(/^\/login$/);
  expect(queryClient.getQueryData(["me"])).toBeUndefined();
});

test("a voluntary change has no explanation and can be cancelled", async () => {
  passwordServer({ mustChange: false });
  const { user } = renderPage("/change-password?next=%2Faccount");
  await user.click(await screen.findByRole("link", { name: "Cancel" }));
  expect(
    await screen.findByRole("heading", { level: 1, name: "Account" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/need to choose a new password/),
  ).not.toBeInTheDocument();
});

test.each([
  ["too short", "a".repeat(11)],
  ["too long", "a".repeat(129)],
])("a new password that is %s is caught", async (_name, password) => {
  const { posted } = passwordServer({ mustChange: false });
  const { user } = renderPage();
  await user.type(await screen.findByLabelText(/^Current password/), CURRENT);
  // Pasting, because typing 129 characters one by one is slow.
  await user.click(screen.getByLabelText(/^New password/));
  await user.paste(password);
  await user.click(screen.getByLabelText(/^Confirm new password/));
  await user.paste(password);
  await user.click(screen.getByRole("button", { name: "Change password" }));
  expect(
    await screen.findByText("Use 12 to 128 characters."),
  ).toBeInTheDocument();
  expect(posted).toEqual([]);
});

test("a confirmation that doesn't match is caught", async () => {
  const { posted } = passwordServer({ mustChange: false });
  const { user } = renderPage();
  await fill(user, CURRENT, NEW, `${NEW}x`);
  expect(
    await screen.findByText("The passwords don't match."),
  ).toBeInTheDocument();
  expect(posted).toEqual([]);
});

test("a wrong current password shows on that field", async () => {
  passwordServer({ mustChange: false });
  const { user } = renderPage();
  await fill(user, "not-the-password", NEW);
  expect(
    await screen.findByText("The current password is wrong."),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText(/^Current password/),
  ).toHaveAccessibleDescription("The current password is wrong.");
  expect(screen.queryByText("Not allowed")).not.toBeInTheDocument();
  expect(location()).toHaveTextContent("/change-password");
});

test("success refreshes me and goes to next", async () => {
  const { posted } = passwordServer({ mustChange: true });
  const { user, queryClient } = renderPage(
    "/change-password?next=%2Fusers%2F7",
  );
  await fill(user, CURRENT, NEW);
  expect(
    await screen.findByRole("heading", { level: 1, name: "User" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent("/users/7");
  expect(screen.getByText("Password changed.")).toBeInTheDocument();
  expect(posted).toEqual([{ current_password: CURRENT, new_password: NEW }]);
  expect(queryClient.getQueryData(["me"])).toMatchObject({
    must_change_password: false,
  });
});

test("without next a success goes to the start page", async () => {
  passwordServer({ mustChange: false });
  const { user } = renderPage();
  await fill(user, CURRENT, NEW);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Devices" }),
  ).toBeInTheDocument();
});

test("someone logged out is sent to log in first", async () => {
  server.use(meErrorHandler(401, "unauthorized"));
  renderPage();
  expect(
    await screen.findByRole("heading", { level: 1, name: "Log in" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent("/login?next=%2Fchange-password");
});
