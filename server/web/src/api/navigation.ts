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
