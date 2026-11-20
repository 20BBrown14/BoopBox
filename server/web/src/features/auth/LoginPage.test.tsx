import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { App } from "../../App";
import type { components } from "../../api/schema";
import { meErrorHandler, meFixture } from "../../test/handlers/me";
import { LocationDisplay } from "../../test/LocationDisplay";
import { renderWithProviders } from "../../test/render";
import { server } from "../../test/server";

type LoginBody = components["schemas"]["TokenRequest"];
type SessionOut = components["schemas"]["SessionOut"];
type ErrorBody = { code: string; message: string; field?: string };

const PASSWORD = "the-right-password";

/** A server with one account; `me` answers once the login succeeds. */
function loginServer() {
  let loggedIn = false;
  const posted: LoginBody[] = [];
  server.use(
    http.get("*/api/me", () =>
      loggedIn
        ? HttpResponse.json(meFixture())
        : HttpResponse.json(
            { code: "unauthorized", message: "authentication required" },
            { status: 401 },
          ),
    ),
    http.post<never, LoginBody, SessionOut | ErrorBody>(
      "*/api/auth/login",
      async ({ request }) => {
        const body = await request.json();
        posted.push(body);
        if (body.password !== PASSWORD) {
          return HttpResponse.json(
            { code: "unauthorized", message: "invalid username or password" },
            { status: 401 },
          );
        }
        loggedIn = true;
        return HttpResponse.json({ must_change_password: false });
      },
    ),
  );
  return { posted };
}

function renderLogin(route = "/login") {
  return renderWithProviders(
    <>
      <App />
      <LocationDisplay />
    </>,
    { route },
  );
}

async function submit(
  user: ReturnType<typeof renderLogin>["user"],
  username: string,
  password: string,
) {
  await user.type(await screen.findByLabelText(/Username/), username);
  await user.type(screen.getByLabelText(/Password/), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

function location() {
  return screen.getByTestId("location");
}

test("a successful login goes to next", async () => {
  const { posted } = loginServer();
  const { user } = renderLogin("/login?next=%2Fusers%2F7");

  await submit(user, "owner", PASSWORD);

  expect(
    await screen.findByRole("heading", { level: 1, name: "User" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent("/users/7");
  expect(posted).toEqual([{ username: "owner", password: PASSWORD }]);
});

test("without next it goes to the start page", async () => {
  loginServer();
  const { user } = renderLogin();
  await submit(user, "owner", PASSWORD);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Devices" }),
  ).toBeInTheDocument();
});

test.each([
  "%2F%2Fevil.example",
  "https%3A%2F%2Fevil.example",
  "%2F%5Cevil.example",
])("an off-site next (%s) falls back to the start page", async (next) => {
  loginServer();
  const { user } = renderLogin(`/login?next=${next}`);
  await submit(user, "owner", PASSWORD);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Devices" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent(/^\/devices$/);
});

test("a wrong password shows the one generic message", async () => {
  loginServer();
  const { user } = renderLogin();

  await submit(user, "owner", "wrong-password");

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Wrong username or password.",
  );
  expect(location()).toHaveTextContent("/login");
});

test("empty fields are caught before anything is sent", async () => {
  const { posted } = loginServer();
  const { user } = renderLogin();

  await user.click(await screen.findByRole("button", { name: "Log in" }));

  expect(screen.getAllByText("Required")).toHaveLength(2);
  expect(posted).toEqual([]);
});

test("a server field error lands on that field", async () => {
  server.use(
    meErrorHandler(401, "unauthorized"),
    http.post<never, LoginBody, ErrorBody>("*/api/auth/login", () =>
      HttpResponse.json(
        {
          code: "invalid_request",
          message: "username is too long",
          field: "username",
        },
        { status: 422 },
      ),
    ),
  );
  const { user } = renderLogin();

  await submit(user, "owner", PASSWORD);

  expect(await screen.findByText("username is too long")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("someone already logged in goes straight to next", async () => {
  renderLogin("/login?next=%2Faccount");
  expect(
    await screen.findByRole("heading", { level: 1, name: "Account" }),
  ).toBeInTheDocument();
  expect(location()).toHaveTextContent("/account");
});
