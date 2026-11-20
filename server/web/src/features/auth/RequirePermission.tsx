import type { ReactNode } from "react";
import { NoPermission } from "../../components/NoPermission";
import { type Permission, useCan } from "./can";

export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const can = useCan();
  return can(permission) ? children : <NoPermission />;
}
