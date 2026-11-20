import type { HttpHandler } from "msw";
import { meHandler } from "./me";

export const handlers: HttpHandler[] = [meHandler()];
