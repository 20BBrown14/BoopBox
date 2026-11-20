import { useLocation } from "react-router";

/** Shows the router's current URL, which MemoryRouter keeps out of window. */
export function LocationDisplay() {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{pathname + search}</output>;
}
