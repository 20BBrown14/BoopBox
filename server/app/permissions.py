from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import permissions as grants
from app.db.users import AuthUser

# id -> (scope, description). Seeded into `permissions` at startup.
CATALOG: dict[str, tuple[str, str]] = {
    "users.manage": (
        "global",
        "create, disable and delete users, issue invites, grant permissions",
    ),
    "devices.manage": ("global", "add and revoke devices"),
    "sources.manage": (
        "global",
        "add, edit, delete and enable or disable media sources",
    ),
    "mappings.edit": ("global", "create, edit and delete slug mappings"),
    "ota.manage": ("global", "manage firmware and OTA"),
    "device.view": ("both", "see a box"),
    "device.control": ("both", "send commands to a box"),
}


async def can(
    conn: AsyncConnection,
    user: AuthUser,
    permission: str,
    device_id: str | None = None,
) -> bool:
    """`user` is already known to be live and not disabled."""
    if permission not in CATALOG:
        raise KeyError(f"unknown permission {permission!r}")
    if user.is_owner:
        return True
    return await grants.has_grant(conn, user.id, permission, device_id)
