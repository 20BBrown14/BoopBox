import { LOGIN_PATH } from "../../api/navigation";

/**
 * A `next` query value that is safe to navigate to: a path on this site.
 * `//host` and `/\host` are protocol-relative URLs to another site, and going
 * back to the login page would loop.
 */
export function safeNext(next: string | null): string {
  if (
    !next ||
    !next.startsWith("/") ||
    next.startsWith("//") ||
    next.startsWith("/\\") ||
    next === LOGIN_PATH ||
    next.startsWith(`${LOGIN_PATH}?`)
  ) {
    return "/";
  }
  return next;
}
