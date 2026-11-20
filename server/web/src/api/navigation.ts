/** Lets code outside React (the query client) move the router. */
export interface Navigation {
  navigate: (to: string, options?: { replace?: boolean }) => void;
  location: { pathname: string; search: string };
}

let current: Navigation | null = null;

export function registerNavigation(navigation: Navigation | null) {
  current = navigation;
}

export function getNavigation(): Navigation | null {
  return current;
}

export const LOGIN_PATH = "/login";

/** The login page, sending the person back to `from` afterwards. */
export function loginPath(from: { pathname: string; search: string }): string {
  return `${LOGIN_PATH}?next=${encodeURIComponent(from.pathname + from.search)}`;
}
