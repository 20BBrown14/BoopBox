import { expect, test } from "vitest";
import { passwordLengthOk } from "./passwordLength";

test.each([
  ["a".repeat(11), false],
  ["a".repeat(12), true],
  ["a".repeat(128), true],
  ["a".repeat(129), false],
  ["🙂".repeat(12), true],
  ["🙂".repeat(128), true],
  ["🙂".repeat(129), false],
  // "e" plus a combining acute accent becomes one "é" under NFC.
  ["e\u0301".repeat(12), true],
  ["e\u0301".repeat(11), false],
])("%j → %s", (password, ok) => {
  expect(passwordLengthOk(password)).toBe(ok);
});
