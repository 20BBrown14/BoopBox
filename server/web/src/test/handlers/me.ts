import { http, HttpResponse } from "msw";
import type { components } from "../../api/schema";

type Me = components["schemas"]["MeOut"];
interface ErrorBody {
  code: string;
  message: string;
}

/** The owner, unless overridden. */
export function meFixture(overrides: Partial<Me> = {}): Me {
  return {
    id: 1,
    display_name: "Owner",
    is_owner: true,
    must_change_password: false,
    login: { provider: "local", username: "owner", label: null },
    permissions: { global: [], devices: {} },
    ...overrides,
  };
}

/** A non-owner with the given grants. */
export function userFixture(
  permissions: Partial<Me["permissions"]> = {},
  overrides: Partial<Me> = {},
): Me {
  return meFixture({
    id: 2,
    display_name: "Kid",
    is_owner: false,
    login: { provider: "local", username: "kid", label: null },
    permissions: { global: [], devices: {}, ...permissions },
    ...overrides,
  });
}

export function meHandler(me: Me = meFixture()) {
  return http.get<never, never, Me>("*/api/me", () => HttpResponse.json(me));
}

export function meErrorHandler(status: number, code: string) {
  return http.get<never, never, ErrorBody>("*/api/me", () =>
    HttpResponse.json({ code, message: code }, { status }),
  );
}
