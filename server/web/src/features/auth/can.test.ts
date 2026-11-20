import { expect, test } from "vitest";
import { meFixture, userFixture } from "../../test/handlers/me";
import { can } from "./can";

test("nobody loaded can do nothing", () => {
  expect(can(undefined, "device.view")).toBe(false);
});

test("the owner can do everything, with no stored grants", () => {
  const owner = meFixture();
  expect(can(owner, "users.manage")).toBe(true);
  expect(can(owner, "server_settings.manage")).toBe(true);
  expect(can(owner, "device.control", "boop-kitchen")).toBe(true);
});

test("a global grant covers every device", () => {
  const me = userFixture({ global: ["device.view"] });
  expect(can(me, "device.view")).toBe(true);
  expect(can(me, "device.view", "boop-kitchen")).toBe(true);
  expect(can(me, "device.control", "boop-kitchen")).toBe(false);
});

test("a device grant covers only that device", () => {
  const me = userFixture({ devices: { "boop-kitchen": ["device.view"] } });
  expect(can(me, "device.view", "boop-kitchen")).toBe(true);
  expect(can(me, "device.view", "boop-den")).toBe(false);
  expect(can(me, "device.view")).toBe(false);
});

test("no grants, no access", () => {
  const me = userFixture();
  expect(can(me, "users.manage")).toBe(false);
  expect(can(me, "device.view", "boop-kitchen")).toBe(false);
});
