import type { Permission } from "../features/auth/can";

export interface NavItem {
  path: string;
  label: "nav.devices" | "nav.users" | "nav.serverSettings" | "nav.account";
  /** Hidden from users who lack it. */
  permission?: Permission;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { path: "/devices", label: "nav.devices" },
  { path: "/users", label: "nav.users", permission: "users.manage" },
  {
    path: "/server-settings",
    label: "nav.serverSettings",
    permission: "server_settings.manage",
  },
  { path: "/account", label: "nav.account" },
];
