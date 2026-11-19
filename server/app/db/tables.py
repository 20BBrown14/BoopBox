"""SQLAlchemy Core definition of the schema. notes/data_design.md is the spec."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)

metadata = MetaData()


def _table(name: str, *items, autoincrement: bool = False) -> Table:
    return Table(
        name,
        metadata,
        *items,
        sqlite_strict=True,
        sqlite_autoincrement=autoincrement,
    )


def _id() -> Column:
    return Column("id", Integer, primary_key=True)


def _text(
    name: str,
    check: str | None = None,
    *,
    nullable: bool = True,
    default: str | None = None,
) -> Column:
    return Column(
        name,
        Text,
        *([CheckConstraint(check)] if check else []),
        nullable=nullable,
        server_default=text(default) if default is not None else None,
    )


def _int(
    name: str,
    check: str | None = None,
    *,
    nullable: bool = True,
    default: int | None = None,
) -> Column:
    return Column(
        name,
        Integer,
        *([CheckConstraint(check)] if check else []),
        nullable=nullable,
        server_default=text(str(default)) if default is not None else None,
    )


def _ts(name: str, *, nullable: bool = False) -> Column:
    # IS, not =: strftime returns NULL for an impossible date, and a NULL
    # comparison would pass the CHECK.
    check = f"strftime('%Y-%m-%dT%H:%M:%fZ', {name}) IS {name}"
    if nullable:
        check = f"{name} IS NULL OR {check}"
    return _text(name, check, nullable=nullable)


def _flag(name: str, default: int) -> Column:
    return _int(name, f"{name} IN (0, 1)", nullable=False, default=default)


def _user_fk(name: str, *, nullable: bool = True, ondelete: str | None = None):
    return Column(
        name, Integer, ForeignKey("users.id", ondelete=ondelete), nullable=nullable
    )


def _created() -> list[Column]:
    return [_ts("created_at"), _user_fk("created_by")]


def _updated() -> list[Column]:
    return [_ts("updated_at"), _user_fk("updated_by")]


def _deleted() -> list[Column]:
    return [_ts("deleted_at", nullable=True), _user_fk("deleted_by")]


schema_info = _table(
    "schema_info",
    Column("id", Integer, CheckConstraint("id = 1"), primary_key=True),
    _int("version", nullable=False),
    _ts("created_at"),
)

users = _table(
    "users",
    _id(),
    _text("display_name", "length(display_name) BETWEEN 1 AND 64", nullable=False),
    _text("email", "length(email) <= 254"),
    _flag("is_owner", 0),
    _flag("disabled", 0),
    _int("token_version", nullable=False, default=0),
    _ts("last_login_at", nullable=True),
    *_created(),
    *_updated(),
    *_deleted(),
    CheckConstraint("is_owner = 0 OR (disabled = 0 AND deleted_at IS NULL)"),
    Index("users_owner", "is_owner", unique=True, sqlite_where=text("is_owner = 1")),
    autoincrement=True,
)

auth_identities = _table(
    "auth_identities",
    _id(),
    _user_fk("user_id", nullable=False, ondelete="CASCADE"),
    _text("provider", nullable=False),
    _text("issuer", "length(issuer) <= 255", nullable=False, default="''"),
    _text("subject", "length(subject) BETWEEN 1 AND 255", nullable=False),
    _text("label", "length(label) <= 255"),
    _text("secret_hash"),
    _flag("must_change_password", 0),
    _int("failed_attempts", "failed_attempts >= 0", nullable=False, default=0),
    _ts("last_failed_at", nullable=True),
    _ts("locked_until", nullable=True),
    _ts("last_used_at", nullable=True),
    _ts("created_at"),
    _ts("updated_at"),
    *_deleted(),
    Index(
        "auth_identities_user",
        "user_id",
        unique=True,
        sqlite_where=text("deleted_at IS NULL"),
    ),
    # Covers deleted rows too, so a local username is never reusable.
    Index(
        "auth_identities_local",
        "subject",
        unique=True,
        sqlite_where=text("provider = 'local'"),
    ),
    Index(
        "auth_identities_external",
        "provider",
        "issuer",
        "subject",
        unique=True,
        sqlite_where=text("provider <> 'local' AND deleted_at IS NULL"),
    ),
    autoincrement=True,
)

invites = _table(
    "invites",
    _id(),
    _user_fk("user_id", nullable=False, ondelete="CASCADE"),
    Column("code_hash", Text, nullable=False, unique=True),
    _ts("expires_at"),
    _ts("used_at", nullable=True),
    *_created(),
    *_deleted(),
    autoincrement=True,
)

auth_history = _table(
    "auth_history",
    _id(),
    _ts("at"),
    _text(
        "outcome",
        "outcome IN ('success', 'bad_credentials', 'unknown_user', 'locked', "
        "'disabled', 'deleted', 'provider_error')",
        nullable=False,
    ),
    _text("provider", nullable=False),
    _text("issuer", "length(issuer) <= 255", nullable=False, default="''"),
    _user_fk("user_id"),
    _text("identifier", "length(identifier) <= 255"),
    _text("client_ip", "length(client_ip) <= 45"),
    _text("user_agent", "length(user_agent) <= 255"),
    Index("auth_history_user", "user_id", "at"),
    Index("auth_history_at", "at"),
    autoincrement=True,
)

permissions = _table(
    "permissions",
    Column("id", Text, primary_key=True),
    _text("scope", "scope IN ('global', 'device', 'both')", nullable=False),
    _text("description"),
)

user_permissions = _table(
    "user_permissions",
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Text,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    _ts("granted_at"),
    _user_fk("granted_by"),
)

user_device_permissions = _table(
    "user_device_permissions",
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "device_id",
        Text,
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Text,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    _ts("granted_at"),
    _user_fk("granted_by"),
)

devices = _table(
    "devices",
    Column(
        "id",
        Text,
        CheckConstraint("length(id) BETWEEN 1 AND 32 AND id NOT GLOB '*[^a-z0-9_-]*'"),
        primary_key=True,
    ),
    _text("friendly_name", "length(friendly_name) <= 64"),
    _text("mqtt_account", "length(mqtt_account) <= 64"),
    _flag("revoked", 0),
    _text("ota_secret_hash", "length(ota_secret_hash) = 64"),
    _text("device_token_hash", "length(device_token_hash) = 64"),
    _ts("last_seen_at", nullable=True),
    _text("firmware_version", "length(firmware_version) <= 32"),
    *_created(),
    *_updated(),
    *_deleted(),
)

media_sources = _table(
    "media_sources",
    _id(),
    _text("type", "length(type) BETWEEN 1 AND 32", nullable=False),
    _text("name", "length(name) BETWEEN 1 AND 64", nullable=False),
    _text("name_key", "length(name_key) BETWEEN 1 AND 192", nullable=False),
    _text("base_url", "length(base_url) BETWEEN 1 AND 2048", nullable=False),
    _text("settings", "length(settings) <= 4096", nullable=False, default="'{}'"),
    _text("secret_encrypted", "length(secret_encrypted) <= 4096"),
    _flag("enabled", 1),
    *_created(),
    *_updated(),
    *_deleted(),
    Index(
        "media_sources_name",
        "name_key",
        unique=True,
        sqlite_where=text("deleted_at IS NULL"),
    ),
    Index(
        "media_sources_endpoint",
        "type",
        "base_url",
        unique=True,
        sqlite_where=text("deleted_at IS NULL"),
    ),
    autoincrement=True,
)

settings = _table(
    "settings",
    Column(
        "key",
        Text,
        CheckConstraint(
            "length(key) BETWEEN 1 AND 64 AND key NOT GLOB '*[^a-z0-9._]*'"
        ),
        primary_key=True,
    ),
    _text("value", "length(value) <= 16384", nullable=False),
    _flag("encrypted", 0),
    *_updated(),
)

mappings = _table(
    "mappings",
    _id(),
    _text(
        "slug",
        "length(slug) BETWEEN 1 AND 128 AND slug NOT GLOB '*[^a-z0-9/_-]*'",
        nullable=False,
    ),
    _text("name", "length(name) BETWEEN 1 AND 100", nullable=False),
    _flag("all_devices", 1),
    _text(
        "play_order",
        "play_order IN ('sequential', 'random')",
        nullable=False,
        default="'random'",
    ),
    _text(
        "play_type",
        "play_type IN ('one', 'all', 'all_repeat')",
        nullable=False,
        default="'one'",
    ),
    *_created(),
    *_updated(),
    Index("mappings_slug", "slug", unique=True),
    autoincrement=True,
)

mapping_devices = _table(
    "mapping_devices",
    Column(
        "mapping_id",
        Integer,
        ForeignKey("mappings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("device_id", Text, ForeignKey("devices.id"), primary_key=True),
    *_created(),
)

mapping_entries = _table(
    "mapping_entries",
    _id(),
    Column(
        "mapping_id",
        Integer,
        ForeignKey("mappings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_id", Integer, ForeignKey("media_sources.id"), nullable=False),
    _text("item", "length(item) BETWEEN 1 AND 256", nullable=False),
    _text("kind", "kind IN ('item', 'collection')", nullable=False, default="'item'"),
    _int("position", nullable=False),
    _text("title", "length(title) <= 256"),
    _text(
        "status",
        "status IN ('unknown', 'ok', 'missing')",
        nullable=False,
        default="'unknown'",
    ),
    _ts("status_checked_at", nullable=True),
    *_created(),
    *_updated(),
    *_deleted(),
    Index(
        "mapping_entries_item",
        "mapping_id",
        "source_id",
        "item",
        unique=True,
        sqlite_where=text("deleted_at IS NULL"),
    ),
    Index("mapping_entries_by_source", "source_id"),
    Index("mapping_entries_status", "status", "mapping_id"),
    autoincrement=True,
)

playback_progress = _table(
    "playback_progress",
    Column(
        "mapping_id",
        Integer,
        ForeignKey("mappings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "device_id",
        Text,
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    _text("queue", "length(queue) <= 400000", nullable=False),
    _int("position", nullable=False, default=0),
    _ts("created_at"),
    _ts("last_played_at"),
    Index("playback_progress_last_played", "last_played_at"),
)

tags = _table(
    "tags",
    _id(),
    Column(
        "uid",
        Text,
        CheckConstraint("length(uid) BETWEEN 1 AND 32 AND uid NOT GLOB '*[^0-9A-F:]*'"),
        nullable=False,
        unique=True,
    ),
    _ts("first_seen_at"),
    Column("first_seen_device_id", Text, ForeignKey("devices.id"), nullable=False),
    _text("first_slug", "length(first_slug) <= 128", nullable=False),
    _ts("last_seen_at"),
    Column("last_seen_device_id", Text, ForeignKey("devices.id"), nullable=False),
    _text("last_slug", "length(last_slug) <= 128", nullable=False),
    Index("tags_last_seen", "last_seen_at"),
    autoincrement=True,
)

boops = _table(
    "boops",
    _id(),
    _ts("received_at"),
    Column("device_id", Text, ForeignKey("devices.id"), nullable=False),
    Column("tag_id", Integer, ForeignKey("tags.id")),
    _text("slug", "length(slug) <= 128"),
    _ts("box_at", nullable=True),
    _text("correlation_id", "length(correlation_id) <= 64"),
    _text(
        "outcome",
        "outcome IN ('played', 'unknown_tag', 'out_of_scope', 'item_unavailable', "
        "'source_unavailable', 'unsupported_version')",
        nullable=False,
    ),
    Column("mapping_id", Integer, ForeignKey("mappings.id", ondelete="SET NULL")),
    Column("entry_id", Integer, ForeignKey("mapping_entries.id", ondelete="SET NULL")),
    Column("source_id", Integer, ForeignKey("media_sources.id")),
    _text("item", "length(item) <= 256"),
    # mapping_id and entry_id aren't required: deleting a mapping clears them.
    CheckConstraint(
        "outcome <> 'played' OR (source_id IS NOT NULL AND item IS NOT NULL)"
    ),
    Index("boops_received", "received_at"),
    Index("boops_device", "device_id", "received_at"),
    Index("boops_tag", "tag_id", "received_at"),
    autoincrement=True,
)

backups = _table(
    "backups",
    _id(),
    _ts("started_at"),
    _ts("finished_at", nullable=True),
    _text("status", "status IN ('running', 'succeeded', 'failed')", nullable=False),
    _text("origin", "origin IN ('scheduled', 'manual')", nullable=False),
    _user_fk("requested_by"),
    _text("path", "length(path) <= 1024"),
    _int("size_bytes"),
    _text("error", "length(error) <= 1024"),
    CheckConstraint(
        "status <> 'succeeded' OR "
        "(finished_at IS NOT NULL AND path IS NOT NULL AND size_bytes IS NOT NULL)"
    ),
    Index("backups_started", "started_at"),
    autoincrement=True,
)
