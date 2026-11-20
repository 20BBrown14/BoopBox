import { useCallback } from "react";
import { type Me, useMe } from "./api";

/** The server's permission catalog (app/permissions.py). */
export type Permission =
  | "users.manage"
  | "devices.manage"
  | "sources.manage"
  | "mappings.edit"
  | "ota.manage"
  | "server_settings.manage"
  | "device.view"
  | "device.control";

/**
 * Mirrors the server's check: owner, then a global grant, then a grant on the
 * device. Only for hiding UI; the server still checks every request.
 */
export function can(
  me: Me | undefined,
  permission: Permission,
  deviceId?: string,
): boolean {
  if (!me) return false;
  if (me.is_owner) return true;
  if (me.permissions.global.includes(permission)) return true;
  if (deviceId === undefined) return false;
  return me.permissions.devices[deviceId]?.includes(permission) ?? false;
}

export function useCan() {
  const { data: me } = useMe();
  return useCallback(
    (permission: Permission, deviceId?: string) =>
      can(me, permission, deviceId),
    [me],
  );
}
