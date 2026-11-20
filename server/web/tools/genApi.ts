/**
 * Generates the API types from the server's schema, or with --check says
 * whether the committed ones are current. Not git-based: the check builds a
 * fresh copy in a temp directory and compares it with src/api.
 *
 * The server's Python comes from BOOPBOX_PYTHON, else server/.venv.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const SERVER_DIR = resolve(import.meta.dirname, "../..");
const API_DIR = resolve(import.meta.dirname, "../src/api");
const PYTHON =
  process.env.BOOPBOX_PYTHON ?? join(SERVER_DIR, ".venv/bin/python");
const FILES = ["openapi.json", "schema.d.ts", "server-setting-keys.json"];

function generate(outDir: string) {
  execFileSync(
    PYTHON,
    [join(SERVER_DIR, "scripts/dump_openapi.py"), "--out-dir", outDir],
    { stdio: "inherit" },
  );
  execFileSync(
    "npx",
    [
      "--no-install",
      "openapi-typescript",
      join(outDir, "openapi.json"),
      "-o",
      join(outDir, "schema.d.ts"),
    ],
    { stdio: "inherit" },
  );
}

function read(path: string) {
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

function check() {
  const fresh = mkdtempSync(join(tmpdir(), "boopbox-api-"));
  try {
    generate(fresh);
    const stale = FILES.filter(
      (name) => read(join(API_DIR, name)) !== read(join(fresh, name)),
    );
    if (stale.length > 0) {
      console.error(
        `Out of date: ${stale.map((name) => `src/api/${name}`).join(", ")}\n` +
          "Run `npm run gen:api` and commit the result.",
      );
      process.exitCode = 1;
    }
  } finally {
    rmSync(fresh, { recursive: true, force: true });
  }
}

if (process.argv.includes("--check")) {
  check();
} else {
  generate(API_DIR);
}
