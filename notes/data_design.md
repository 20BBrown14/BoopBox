# BoopBox Server — Data Design

Planning doc for the SQLite data model: users, authentication, permissions and
devices. No implementation yet.

## Table of contents

- [Conventions](#conventions)
- [Schema creation](#schema-creation)
  - [Definition and query layer](#definition-and-query-layer)
  - [Unique among live rows](#unique-among-live-rows)
  - [SQLite specifics](#sqlite-specifics)
  - [Omitted from the snippets](#omitted-from-the-snippets)
  - [Schema version](#schema-version)
- [Metadata and soft deletes](#metadata-and-soft-deletes)
  - [Standard columns](#standard-columns)
  - [Rules](#rules)
  - [Soft-delete consequences](#soft-delete-consequences)
  - [Per-table summary](#per-table-summary)
  - [History](#history)
- [Limits and validation](#limits-and-validation)
  - [Layers](#layers)
  - [Text normalization](#text-normalization)
  - [Limits](#limits)
  - [Input from boxes](#input-from-boxes)
- [Users and auth](#users-and-auth)
  - [Requirements](#requirements)
  - [users](#users)
  - [auth_identities](#auth_identities)
  - [invites](#invites)
  - [Failed logins](#failed-logins)
  - [Authentication history](#authentication-history)
- [Permissions](#permissions)
  - [Catalog](#catalog)
  - [Tables](#tables)
  - [Permission check](#permission-check)
  - [Device visibility](#device-visibility)
- [Devices](#devices)
- [Media sources](#media-sources)
- [Slug mappings](#slug-mappings)
  - [Playback progress](#playback-progress)
- [Tags seen](#tags-seen)
- [Boop history](#boop-history)
- [Retention](#retention)
- [Backups](#backups)
- [Settings](#settings)
  - [Registry](#registry)
  - [Table](#settings-table)
  - [Setting keys](#setting-keys)
  - [Environment overrides](#environment-overrides)
  - [Environment](#environment)
  - [Encryption](#encryption)
  - [Key rotation](#key-rotation)
  - [Generated secrets](#generated-secrets)
- [Flows](#flows)
  - [Bootstrap owner](#bootstrap-owner)
  - [Invite and redeem](#invite-and-redeem)
  - [Re-invite (lost access)](#re-invite-lost-access)
  - [Owner recovery](#owner-recovery)
  - [Deleting a user](#deleting-a-user)
  - [Request authentication](#request-authentication)
- [Open questions](#open-questions)

## Conventions

- **Primary keys** are `INTEGER PRIMARY KEY AUTOINCREMENT` and foreign keys to
  them are `INTEGER`. `AUTOINCREMENT` is deliberate: without it SQLite can hand
  the id of a removed highest row to a new row, which would silently re-point old
  references. With it an id is never reissued.
- **Natural text keys** are used where a human-meaningful value already
  identifies the row: `devices.id` (the id in the box's MQTT topics, chosen by
  the admin) and `permissions.id` (stable names defined in code, like
  `users.manage`).
- **UUIDs** are reserved for identifiers that must not collide across entity
  types. No table needs one today; a tag's slug already fills that role.
- Integer ids are guessable. Access is always decided by authorization checks,
  never by an id being hard to guess.
- **Timestamps** are ISO-8601 in UTC, stored as text in one fixed format:
  `YYYY-MM-DDTHH:MM:SS.sssZ` (millisecond precision, always the `Z` suffix), for
  example `2026-11-13T09:30:00.000Z`. The database is always UTC; conversion to
  local time happens only when displaying. The fixed width means text comparison
  matches time order, so `<`, `>` and `ORDER BY` work directly. One app helper
  produces every timestamp, and nothing writes them by hand.
- **Booleans** are `INTEGER` 0/1 flags, checked to be 0 or 1.
- **Foreign keys are enforced on every connection** with
  `PRAGMA foreign_keys = ON`.
- **No migrations yet.** The schema is created from scratch and any existing
  database is discarded. Migration tooling is needed once there is data worth
  keeping.

## Schema creation

SQLite is the only supported database. The schema uses SQLite features freely
where they make it simpler, such as partial indexes and `GLOB` checks.

### Definition and query layer

- The schema is defined once in code as SQLAlchemy Core tables, columns,
  constraints and indexes. The DDL is generated from that definition, not
  maintained by hand. The SQL in this document is what it produces.
- The app reaches the database only through a repository layer, so no handler
  contains SQL. Queries are written with SQLAlchemy Core, which replaces the
  current hand-written SQLite calls.
- Other databases are not a target. Keeping SQL behind the repository layer and
  SQLAlchemy Core leaves a later port possible, but nothing here is designed
  for one.
- **Minimum version: SQLite 3.37** (for `STRICT`). The server checks the linked
  SQLite version at startup and refuses to start on an older one.

### Unique among live rows

Soft delete means many rules read "unique among rows that aren't deleted". These
are partial unique indexes:

```sql
CREATE UNIQUE INDEX media_sources_name ON media_sources (name_key)
    WHERE deleted_at IS NULL;
```

Deleted rows fall outside the index, so they never conflict with anything, and
live rows must be unique. A rule that depends on another condition uses its own
`WHERE`, such as the one-owner rule on `users`. A query only uses a partial index
when its own `WHERE` implies the index's condition, so lookups through one
include that condition (for example `provider = 'local'`).

### SQLite specifics

- **`STRICT` tables.** SQLite normally lets any value into any column, so text
  like `'abc'` can sit in an `INTEGER` column. `STRICT` rejects a value that can't
  be converted to the declared type. It can't be added to an existing table,
  which is why it is decided now.
- **Timestamp format check.** `CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', col) IS
  col)` on every timestamp column (`col IS NULL OR ...` where nullable). It
  accepts only the fixed UTC format and real dates. It must use `IS`, not `=`:
  an impossible date makes `strftime` return NULL, and a comparison with NULL
  passes a `CHECK`.
- **Character-set checks** on device ids, slugs, tag UIDs and setting keys use
  `GLOB`.
- **Case-insensitive text** uses an app-computed key column (`name_key`), not
  `COLLATE NOCASE`, because `NOCASE` only folds ASCII.
- **Connection setup:** `PRAGMA foreign_keys = ON`, WAL and the other pragmas.
- **File maintenance:** `auto_vacuum` and `incremental_vacuum` (see Retention).
- **Backups** use `VACUUM INTO` or the online backup API (see Backups).
- **Concurrency.** SQLite serializes writers, but uniqueness is still enforced
  by the database through the constraints above, never by an app-side lookup
  alone.

### Omitted from the snippets

To keep the SQL in this document readable, the generator adds three things that
the snippets don't repeat:

- every table is created `STRICT`
- every flag column gets `CHECK (col IN (0, 1))`
- every timestamp column gets the format check above

Everything else in a snippet, including the other CHECKs, is applied as written.

### Schema version

A one-row table records the schema version.

```sql
CREATE TABLE schema_info (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    version     INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
```

It is written once when the schema is created, with `version = 1`. At startup:

| State | Behavior |
|-------|----------|
| no `schema_info` table | create the schema from scratch |
| version equals the server's | start normally |
| version is higher | refuse to start: the database is newer than this server |
| version is lower | refuse to start until migration tooling exists |

Stamping the version from the first release is what lets later migrations tell
databases apart.

## Metadata and soft deletes

### Standard columns

Mutable, user-owned tables carry this set:

```sql
created_at  TEXT NOT NULL,
created_by  INTEGER REFERENCES users(id),
updated_at  TEXT NOT NULL,
updated_by  INTEGER REFERENCES users(id),
deleted_at  TEXT,                       -- NULL = live
deleted_by  INTEGER REFERENCES users(id)
```

### Rules

- Soft delete is the default. Hard deletes are allowed as deliberate, per-table
  exceptions (see the summary).
- A NULL actor (`*_by`) means **system**: the bootstrap owner and anything else
  created by the server itself. Self-redeemed rows also have no admin actor.
- Users are never hard-deleted, so actor FKs never dangle.
- `updated_at` / `updated_by` are set together by the repository layer in a
  single code path. SQLite triggers can't know the acting user, so no triggers.
- **Telemetry is not an edit.** `devices.last_seen_at`,
  `devices.firmware_version`, `users.last_login_at`,
  `auth_identities.last_used_at`, `auth_identities.label` and the failed-login
  columns change on their own and must not bump `updated_at` / `updated_by`.
- `disabled` (reversible suspension) and `deleted_at` (removed) are different
  states and both exist where relevant.

### Soft-delete consequences

- **Cascades don't fire.** `ON DELETE CASCADE` only runs on a real delete. The
  app performs the cascade by hand (see Deleting a user). The FKs keep their
  `CASCADE` clause as a backstop for the rare hard delete.
- **Uniqueness must account for deleted rows.** Each unique constraint is either
  scoped to live rows through a partial index (so a deleted row frees its slot;
  see Unique among live rows) or full (a deleted row keeps its slot reserved).
  Which one is chosen per constraint and why is called out on the table.
- **Every read filters `deleted_at IS NULL`.** Do this in the repository layer or
  in views, not by hand at each call site.

### Per-table summary

| table | created_* | updated_* | deleted_* | notes |
|-------|-----------|-----------|-----------|-------|
| `users` | yes | yes | yes | |
| `auth_identities` | `created_at` only | `updated_at` only | yes | actor is the user themself or the invite issuer |
| `invites` | yes | no | yes | immutable; `deleted_*` = revoked |
| `user_permissions` | `granted_at`, `granted_by` | no | **hard delete** | revoke removes the row |
| `user_device_permissions` | `granted_at`, `granted_by` | no | **hard delete** | revoke removes the row |
| `permissions` | no | no | no | seeded from code |
| `devices` | yes | yes | yes | `revoked` is separate from deleted |
| `media_sources` | yes | yes | yes | `enabled` is separate from deleted |
| `settings` | no | `updated_at`, `updated_by` | **hard delete** | reset to default deletes the row |
| `mappings` | yes | yes | **hard delete** | deleting frees the slug and cascades to entries, box list and progress |
| `mapping_entries` | yes | yes | yes | `status` columns are telemetry |
| `mapping_devices` | yes | no | **hard delete** | removing a box removes the row |
| `playback_progress` | `created_at` only | no | **hard delete** | runtime state; expires and is purged |
| `auth_history` | `at` only | no | **hard delete** | append-only log; purged by age |
| `tags` | `first_seen_at` | `last_seen_at` | no | written by the server from boops; never purged |
| `boops` | `received_at` only | no | **hard delete** | append-only log; purged by age |
| `backups` | `started_at` only | `finished_at` | **hard delete** | pruned together with its file |

Grants are hard-deleted because soft-deleting one breaks the composite primary
key on re-grant, and a grant has no state worth keeping once revoked.

### History

No audit log and no per-row version history for now. The row-level who/when
columns above are the whole tracking story. If edit history or revert becomes
useful later (most likely for collections and slug mappings once they are
stored in the database), it can be added per table without changing these
columns.

## Limits and validation

Every value a user or a box can supply has a limit. Limits protect the UI, the
MQTT topics, password-hashing cost and database size. They are fixed in code, not
settings.

### Layers

- **The app validates first** and is authoritative. A failure returns an error
  naming the field, never a raw database error.
- **The database CHECKs are a backstop.** They cover length bounds, plus the
  character set where `GLOB` can express it (device id and slug), so a bug or a
  direct insert can't store junk. Local usernames have no character-set CHECK
  because `auth_identities.subject` is shared with OAuth subjects, which are
  opaque.
- **Lengths count characters** (code points), which is what SQLite's `length()`
  counts for `TEXT`. The app and the CHECKs therefore agree. JSON size caps count
  characters too.

### Text normalization

Before validating or comparing, the app trims leading and trailing whitespace and
normalizes to Unicode NFC. Single-line fields reject control characters,
including newlines. Normalizing first means a limit or a uniqueness rule can't be
dodged with combining characters or padding.

### Limits

| Field | Limit | DB CHECK |
|-------|-------|----------|
| `users.display_name` | 1-64 characters | length |
| `users.email` | up to 254; exactly one `@`; never verified | length |
| local username (`auth_identities.subject`) | 3-32, lowercase `a-z 0-9 . _ -` | app only |
| other `subject` / `issuer`, `auth_identities.label` | up to 255 | length |
| password | 12-128 characters, any characters, no composition rules | none |
| invite code (as submitted) | up to 128 | none |
| `devices.id` | 1-32, `a-z 0-9 _ -` | length + character set |
| `devices.friendly_name`, `mqtt_account` | up to 64 | length |
| `devices.ota_secret_hash`, `device_token_hash` | exactly 64 (SHA-256 hex) | length |
| `devices.firmware_version` | up to 32; a longer version reply is dropped | length |
| `media_sources.name` | 1-64 | length |
| `media_sources.type` | 1-32 | length |
| `media_sources.base_url` | up to 2048; `http` or `https`; no embedded credentials, query or fragment | length |
| `media_sources.settings` | valid JSON object, up to 4096 | length (JSON validity is app only) |
| `media_sources.secret_encrypted` | up to 4096 | length |
| `mappings.slug` | 1-128, `a-z 0-9 / _ -` | length + character set |
| `mappings.name` | 1-100 | length |
| `mapping_entries.item` | 1-256 | length |
| `auth_history.identifier`, `issuer`, `user_agent` | up to 255 | length |
| `auth_history.client_ip` | up to 45 | length |
| `tags.uid` | 1-32, uppercase hex and `:` | length + character set |
| `tags.first_slug`, `last_slug` | up to 128, may be empty | length |
| `boops.slug` | up to 128 | length |
| `boops.correlation_id` | up to 64 | length |
| `boops.item` | up to 256 | length |
| `mapping_entries.title` | up to 256 | length |
| `backups.path`, `backups.error` | up to 1024 | length |
| entries per mapping | 999 | app only |
| items in a play queue | 1000, and at least 1 | app only |
| `playback_progress.queue` | up to 400000 characters | length |

- **Passwords** have a maximum only to bound Argon2id hashing cost. Length
  matters more than composition, so there are no required character classes.
- **Device ids** go into MQTT topics, so the character set excludes `/`, `+` and
  `#`.
- **Slug suffix.** The server-added collision suffix is a dash plus 6 random
  characters, so the name-derived part of a generated slug is truncated to 121.
- **Queue cap.** A collection that expands past 1000 items is truncated to 1000
  and the truncation is logged. It is a safety bound, not an expected case.
- **Not limited.** The number of users, devices, sources and mappings is
  unbounded.

### Input from boxes

A box's payload is untrusted input:

- An MQTT payload over 4096 bytes is rejected before parsing.
- A tag UID is up to 32 characters and a boop correlation id up to 64.
- The slug read from a tag is capped at 128 characters, the same as the longest
  mapping slug. Anything longer can't match a mapping, so it resolves as an
  unknown tag. When a slug is recorded, only its first 128 characters are kept.

## Users and auth

### Requirements

- Login by local username + password, or an external provider. Jellyfin and
  Google first.
- One login method per user for now.
- Users are invited by an admin, not self-registered.
- Case-insensitive local usernames, never reusable (even after deletion).
- Stateless auth: no session table.

### users

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name  TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 64),
    email         TEXT CHECK (length(email) <= 254),
    is_owner      INTEGER NOT NULL DEFAULT 0,
    disabled      INTEGER NOT NULL DEFAULT 0,
    token_version INTEGER NOT NULL DEFAULT 0,
    last_login_at TEXT,
    created_at    TEXT NOT NULL,
    created_by    INTEGER REFERENCES users(id),
    updated_at    TEXT NOT NULL,
    updated_by    INTEGER REFERENCES users(id),
    deleted_at    TEXT,
    deleted_by    INTEGER REFERENCES users(id),

    CHECK (is_owner = 0 OR (disabled = 0 AND deleted_at IS NULL))
);

-- at most one owner
CREATE UNIQUE INDEX users_owner ON users (is_owner) WHERE is_owner = 1;
```

- `is_owner` marks the bootstrap account. It is the only one, cannot be
  disabled or deleted (enforced by the CHECK), and always has every permission
  (see Permission check).
- `is_owner` is set once by the bootstrap and never exposed for editing.
- A live user with no live `auth_identities` row is pending (invited, not yet
  redeemed). No status column needed.
- `email` is optional and never used to match or link accounts.
- `token_version` counts how many times this user's login tokens have been
  revoked. See Request authentication.

### auth_identities

```sql
CREATE TABLE auth_identities (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider             TEXT NOT NULL,   -- 'local' | 'jellyfin' | 'google'
    issuer               TEXT NOT NULL DEFAULT '' CHECK (length(issuer) <= 255),
    subject              TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 255),
    label                TEXT CHECK (length(label) <= 255),  -- from the provider
    secret_hash          TEXT,            -- Argon2id; local only
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts      INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    last_failed_at       TEXT,
    locked_until         TEXT,
    last_used_at         TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    deleted_at           TEXT,
    deleted_by           INTEGER REFERENCES users(id)
);

-- one live method per user
CREATE UNIQUE INDEX auth_identities_user ON auth_identities (user_id)
    WHERE deleted_at IS NULL;
-- local usernames are reserved forever: deleted rows keep their slot
CREATE UNIQUE INDEX auth_identities_local ON auth_identities (subject)
    WHERE provider = 'local';
-- external accounts: a deleted row frees the slot
CREATE UNIQUE INDEX auth_identities_external
    ON auth_identities (provider, issuer, subject)
    WHERE provider <> 'local' AND deleted_at IS NULL;
```

| provider | issuer | subject |
|----------|--------|---------|
| `local` | `''` | lowercased username |
| `google` | `https://accounts.google.com` | Google `sub` claim |
| `jellyfin` | `media_sources.id` of the Jellyfin source, as text | Jellyfin user id |

- Usernames are lowercased by the app **only when `provider = 'local'`**. No
  `COLLATE NOCASE`: OAuth subjects are opaque ids and must not be case-folded.
- **Local usernames are never reusable.** `auth_identities_local` covers every
  local row, deleted or not, so deleting a user or replacing their identity keeps
  the old row (and its username) in place. This is why identities are
  soft-deleted and kept. Login looks a username up with `provider = 'local'` in
  the query so it uses that index.
- The one exception is the same user getting their own username back; see
  Re-invite.
- External accounts are deliberately **not** reserved: once the identity is
  deleted, that Google or Jellyfin account can be linked again, including by the
  same person returning as a new user. Reserving them would be a small change:
  drop the `deleted_at IS NULL` condition from `auth_identities_external`.
- **`label`** is a readable name for the account, so the UI can show who a user
  logs in as without calling the provider: the Google `email` claim, or the
  Jellyfin username. It is NULL for local identities, whose `subject` is already
  the username. The server refreshes it from the provider on each successful
  login. It is telemetry, doesn't bump `updated_*`, and is never used to match an
  account. It comes from outside, so it is shown as inert text.
- Jellyfin issuer is the source id because a Jellyfin user id is only unique per
  server, and more than one Jellyfin source can exist. It is not an enforced FK
  because the column is shared with other providers; the app validates it.
- Jellyfin isn't OAuth: login is the server validating credentials against the
  Jellyfin source. The result still lands here as an identity.
- Accounts are never matched or auto-linked by email.
- `must_change_password` is set on the bootstrap owner and honored at login.

### invites

```sql
CREATE TABLE invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash   TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    deleted_at  TEXT,
    deleted_by  INTEGER REFERENCES users(id)
);
```

- The code is a high-entropy random value, shown to the admin once. Only a
  SHA-256 hash is stored. A fast hash is fine here; Argon2id is for passwords.
- Valid means `used_at IS NULL`, `deleted_at IS NULL`, and `expires_at` in the
  future. Invites expire after the `invites.expiry_days` setting, 3 days by
  default.
- Issuing a new invite for a user revokes (soft-deletes) their earlier unused
  ones.
- Invites are immutable apart from being used or revoked, so no `updated_*`.

### Failed logins

Local passwords are throttled with a temporary lockout, tracked on the identity
by `failed_attempts`, `last_failed_at` and `locked_until`.

- **Local only.** Jellyfin logins are checked by the Jellyfin server, which does
  its own lockout, and the identity isn't known until Jellyfin accepts the
  credentials. Google logins are handled by Google.
- **Settings.** `auth.lockout_threshold` failures (default 5) lock the identity
  for `auth.lockout_minutes` (default 15).
- **Counting.** A wrong password increments `failed_attempts` and sets
  `last_failed_at`. If the previous failure was more than `auth.lockout_minutes`
  ago, the count restarts at 1, so old failures don't accumulate forever.
  Reaching the threshold sets `locked_until` to now plus the lockout period.
- **Atomic update.** Counting is one `UPDATE` statement that computes the new
  count and the lock together, so parallel guesses can't each read the same count
  and slip past the threshold.
- **While locked,** every attempt is rejected without checking the password, and
  is not counted. A correct password during the lock is still rejected, and
  repeated attempts can't extend the lock.
- **On success,** `failed_attempts`, `last_failed_at` and `locked_until` are
  cleared. A lock also clears when `locked_until` passes, because it is compared
  to the current time rather than reset by a job.
- **Admin override.** An admin can clear a lock. A password reset or a redeemed
  re-invite also clears it.
- **One error for everything.** A wrong password, an unknown username and a
  locked account all return the same generic "invalid username or password". A
  distinct "locked" message would confirm that a username exists. The cost is
  that a locked-out person isn't told why; the admin UI shows lock state. For an
  unknown username the server still runs a dummy password-hash check, so response
  time doesn't reveal that it doesn't exist.
- **Not an edit.** These columns are telemetry and don't bump `updated_*`.
- **Known limits.** A deliberate attacker can keep a known username locked by
  failing on purpose, though the lock always expires. Guesses against unknown
  usernames aren't counted or blocked, since there's no identity row to count
  against; they are recorded in the authentication history below.

### Authentication history

An append-only log of every login attempt, successful or not. It answers "who
logged in, from where, and who has been trying and failing". It is separate from
the failed-login columns: those are the live throttling state, this is the
record. Throttling never queries it.

```sql
CREATE TABLE auth_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    outcome     TEXT NOT NULL CHECK (outcome IN (
                    'success', 'bad_credentials', 'unknown_user', 'locked',
                    'disabled', 'deleted', 'provider_error')),
    provider    TEXT NOT NULL,                 -- 'local' | 'jellyfin' | 'google'
    issuer      TEXT NOT NULL DEFAULT '' CHECK (length(issuer) <= 255),
    user_id     INTEGER REFERENCES users(id),  -- NULL when no user matched
    identifier  TEXT CHECK (length(identifier) <= 255),  -- as typed; untrusted
    client_ip   TEXT CHECK (length(client_ip) <= 45),
    user_agent  TEXT CHECK (length(user_agent) <= 255)
);

CREATE INDEX auth_history_user ON auth_history (user_id, at);
CREATE INDEX auth_history_at ON auth_history (at);
```

- **What is recorded.** Every attempt to log in, on any provider, including
  attempts for usernames that don't exist and attempts blocked by a lock. Normal
  authenticated requests are not logged; only logins are.
- **Outcomes.** `success`; `bad_credentials` (known user, wrong password);
  `unknown_user`; `locked`; `disabled`; `deleted`; `provider_error` (Jellyfin
  unreachable or Google failed). The caller still sees only the one generic
  error. The detailed outcome is for administrators.
- **`user_id`** is set when an identity was matched and NULL otherwise.
- **`identifier`** is what was typed as the username, and is NULL for Google.
  It is attacker-controlled text, so it is capped and shown as inert text, never
  interpolated into HTML or a query. The submitted password, or any part of it,
  is never stored.
- **`client_ip`** is the address the app sees. Behind a reverse proxy that is the
  proxy's address unless `auth.trust_forwarded_header` is on. Turn that on only
  when a proxy you control overwrites the forwarding header, because otherwise a
  client can claim any address.
- **Same transaction.** The history row is written in the same transaction as the
  failed-login counter update, so the two can't disagree.
- **Append-only.** Rows are never edited or soft-deleted, so there are no
  `updated_*` or `deleted_*` columns. They are removed only by the retention
  purge, `auth.history_retention_days` (default 90; `0` keeps them forever).
- **`users.last_login_at`** stays as a cheap denormalized field for listings, set
  from successful rows.
- **Known limit.** Unknown-username attempts aren't throttled, so a flood can
  grow the table within the retention window. Retention is by age; there is no
  row-count cap.

## Permissions

Granular, additive grants. No roles for now; a role can later be a bundle that
expands into these grants without changing the tables below.

Permissions come in two scopes: system-wide, and per device. Per-device grants
are what let a user see and control only certain boxes.

### Catalog

Seeded from code at startup (upsert). Code is the source of truth; the table
exists for referential integrity.

| id | scope | meaning |
|----|-------|---------|
| `users.manage` | global | create/disable/delete users, issue invites, grant permissions |
| `devices.manage` | global | add and revoke devices |
| `sources.manage` | global | add, edit, delete and enable/disable media sources |
| `mappings.edit` | global | create, edit and delete slug mappings |
| `ota.manage` | global | manage firmware/OTA |
| `server_settings.manage` | global | edit server settings |
| `device.view` | both | see a box |
| `device.control` | both | send commands to a box |

`both` means it can be granted globally (every box) or on a single box.

### Tables

```sql
CREATE TABLE permissions (
    id           TEXT PRIMARY KEY,
    scope        TEXT NOT NULL CHECK (scope IN ('global', 'device', 'both')),
    description  TEXT
);

CREATE TABLE user_permissions (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted_at    TEXT NOT NULL,
    granted_by    INTEGER REFERENCES users(id),
    PRIMARY KEY (user_id, permission_id)
);

CREATE TABLE user_device_permissions (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id     TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted_at    TEXT NOT NULL,
    granted_by    INTEGER REFERENCES users(id),
    PRIMARY KEY (user_id, device_id, permission_id)
);
```

Two grant tables instead of one with a nullable `device_id`, because a nullable
column in a primary key/UNIQUE would allow duplicate global grants in SQLite.

The `scope` rules (`global` perms only in `user_permissions`; `device`/`both` in
`user_device_permissions`; `both` also allowed in `user_permissions`) are
enforced by the app when granting, not by the schema.

### Permission check

`can(user, permission, device?)`:

1. User is deleted or disabled -> deny.
2. User is `is_owner` -> allow. The owner's access is **implicit**, not stored
   as grant rows, so newly added permissions apply to it automatically.
3. A `user_permissions` row for the permission -> allow (applies to all devices).
4. If a device is given, a `user_device_permissions` row for
   `(user, device, permission)` -> allow.
5. Otherwise deny.

### Device visibility

A user sees a device if they can `device.view` it. The device list is every
device (when they hold global `device.view`, or are the owner) plus the devices
with a `device.view` row in `user_device_permissions`. Deleted devices are
excluded.

`device.control` should not imply `device.view`; granting control on a box
without view is a configuration mistake the grant UI should prevent.

## Devices

A device is one BoopBox unit. The table holds its metadata and the hashes of
the two credentials the box presents over HTTP.

```sql
CREATE TABLE devices (
    id               TEXT PRIMARY KEY        -- e.g. 'boop-kitchen'
                     CHECK (length(id) BETWEEN 1 AND 32
                            AND id NOT GLOB '*[^a-z0-9_-]*'),
    friendly_name    TEXT CHECK (length(friendly_name) <= 64),
    mqtt_account     TEXT CHECK (length(mqtt_account) <= 64),
    revoked          INTEGER NOT NULL DEFAULT 0,
    ota_secret_hash  TEXT CHECK (length(ota_secret_hash) = 64),    -- SHA-256 hex
    device_token_hash TEXT CHECK (length(device_token_hash) = 64), -- SHA-256 hex
    last_seen_at     TEXT,
    firmware_version TEXT CHECK (length(firmware_version) <= 32),
    created_at       TEXT NOT NULL,
    created_by       INTEGER REFERENCES users(id),
    updated_at       TEXT NOT NULL,
    updated_by       INTEGER REFERENCES users(id),
    deleted_at       TEXT,
    deleted_by       INTEGER REFERENCES users(id)
);
```

- `id` is the device id used in the MQTT topics (`boopbox/<id>/...`). It is never
  reused: a deleted device keeps its row, so its id stays taken.
- `mqtt_account` is a non-secret pointer to the device's account on the MQTT
  broker, or NULL when the broker uses a shared login. The broker owns the
  password; none is stored here.
- **Credentials.** `ota_secret_hash` checks the HTTP Basic password on the
  firmware download. `device_token_hash` checks the bearer token on device API
  routes. Both secrets are generated by the server when the device is added,
  shown to the admin once for flashing, and stored only as a SHA-256 hash. A
  fast hash is fine because they are high-entropy random values, like invite
  codes. Either can be regenerated from the UI, which replaces the hash and is
  an edit (bumps `updated_*`). NULL means not provisioned, and nothing matches
  it.
- **Revoked** means blocked but still visible in the UI. A revoked device fails
  both HTTP credentials, and the server drops its MQTT messages before doing
  anything else: no `tags` upsert, no `boops` row, no `last_seen_at` update,
  and no reply. The broker can still accept its connection, because the broker
  owns the MQTT login; revoke the broker account too to cut it off there.
- **Deleted** means hidden. A deleted device is treated as revoked.
- `last_seen_at` is set from boop and OTA traffic, and `firmware_version` is
  reported by the box. Both are telemetry and don't bump `updated_*`. Neither
  changes for a revoked or deleted device.
- Devices are added in the UI; none are seeded at startup.

## Media sources

A media source is a configured connection to a backend that serves audio, such
as a Jellyfin server. Any number of sources can exist, including several of the
same type. They are created, edited and deleted in the UI, not in config files.

```sql
CREATE TABLE media_sources (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    type             TEXT NOT NULL            -- 'jellyfin'; more types later
                     CHECK (length(type) BETWEEN 1 AND 32),
    name             TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 64),
    name_key         TEXT NOT NULL            -- name case-folded by the app
                     CHECK (length(name_key) BETWEEN 1 AND 192),
    base_url         TEXT NOT NULL            -- normalized by the app before storing
                     CHECK (length(base_url) BETWEEN 1 AND 2048),
    settings         TEXT NOT NULL DEFAULT '{}'  -- JSON object, non-secret, type-specific
                     CHECK (length(settings) <= 4096),
    secret_encrypted TEXT                     -- encrypted API key / credential
                     CHECK (length(secret_encrypted) <= 4096),
    enabled          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL,
    created_by       INTEGER REFERENCES users(id),
    updated_at       TEXT NOT NULL,
    updated_by       INTEGER REFERENCES users(id),
    deleted_at       TEXT,
    deleted_by       INTEGER REFERENCES users(id)
);

-- no two live sources share a display name, ignoring case
CREATE UNIQUE INDEX media_sources_name ON media_sources (name_key)
    WHERE deleted_at IS NULL;
-- no two live sources point at the same server
CREATE UNIQUE INDEX media_sources_endpoint ON media_sources (type, base_url)
    WHERE deleted_at IS NULL;
```

- `id` is stable. Everything that refers to a source (slug mappings,
  Jellyfin login identities) uses the id, never the name, so renaming is safe.
- **Sources are edited, not recreated.** When a server's address or credential
  changes, the source row is edited in place. The id stays the same, so its
  mappings and Jellyfin logins keep working.
- **`name_key`** is the name in NFC and Unicode case-folded form, set by the app
  whenever the name changes. A plain unique index on it gives case-insensitive
  uniqueness. SQLite's `NOCASE` collation wouldn't, because it only folds ASCII.
- **Uniqueness** is two rules over live rows: the name (case-insensitive, through
  `name_key`) and the `(type, base_url)` pair. Deleted sources free both, since
  references use the id. The app normalizes `base_url` (lowercase scheme and host, no trailing
  slash) so the index catches trivial variants. One source per server is
  intended; there is no separate-account-on-the-same-server case.
- `type` is validated by the app against the source implementations it knows,
  not by a CHECK, so adding a type needs no migration.
- `settings` holds non-secret, type-specific options (for Jellyfin, an optional
  user id). It is not part of the uniqueness rule.
- **Credentials are encrypted, not hashed**, because the server must send them
  to the backend. They use the same encryption as secret settings (see
  Settings). The API never returns the credential; editing a source can only
  replace it. Losing the key means re-entering every source credential.
- `enabled` is a reversible off switch, like `users.disabled`. A disabled source
  is not used for playback or login.
- Adding, editing, deleting and enabling/disabling a source all require the
  global `sources.manage` permission.
- Deleting a source leaves anything referencing it dangling by design: slug
  mappings to it fail with a source-unavailable error, and Jellyfin-linked users
  can no longer log in through it until they are re-invited.

## Slug mappings

A tag carries an opaque slug (for example `boop/zelda`). A mapping ties that slug
to one or more things to play, and says how to play them. By default a mapping
applies to every box, so the same tag works anywhere. It can instead be limited
to a chosen set of boxes: one, several, or none.

Each slug has a list of entries. An entry points at one item or one collection
on one media source. A collection is expanded to its member items by the source
at play time, so only the collection's id is stored.

```sql
CREATE TABLE mappings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL               -- normalized by the app; immutable
                CHECK (length(slug) BETWEEN 1 AND 128
                       AND slug NOT GLOB '*[^a-z0-9/_-]*'),
    name        TEXT NOT NULL               -- friendly name; not unique
                CHECK (length(name) BETWEEN 1 AND 100),
    all_devices INTEGER NOT NULL DEFAULT 1, -- 1 = every box; 0 = only mapping_devices
    play_order  TEXT NOT NULL DEFAULT 'random'
                CHECK (play_order IN ('sequential', 'random')),
    play_type   TEXT NOT NULL DEFAULT 'one'
                CHECK (play_type IN ('one', 'all', 'all_repeat')),
    created_at  TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER REFERENCES users(id)
);

-- mappings are hard-deleted, so a plain unique index; deleting frees the slug
CREATE UNIQUE INDEX mappings_slug ON mappings (slug);

CREATE TABLE mapping_devices (
    mapping_id  INTEGER NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
    device_id   TEXT NOT NULL REFERENCES devices(id),
    created_at  TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    PRIMARY KEY (mapping_id, device_id)
);

CREATE TABLE mapping_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mapping_id  INTEGER NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
    source_id   INTEGER NOT NULL REFERENCES media_sources(id),
    item        TEXT NOT NULL               -- opaque id on the source
                CHECK (length(item) BETWEEN 1 AND 256),
    kind        TEXT NOT NULL DEFAULT 'item' CHECK (kind IN ('item', 'collection')),
    position    INTEGER NOT NULL,
    title       TEXT CHECK (length(title) <= 256),     -- cached by the UI
    status      TEXT NOT NULL DEFAULT 'unknown'
                CHECK (status IN ('unknown', 'ok', 'missing')),
    status_checked_at TEXT,
    created_at  TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER REFERENCES users(id),
    deleted_at  TEXT,
    deleted_by  INTEGER REFERENCES users(id)
);

-- the same item can't be listed twice in one mapping; also serves resolution,
-- which reads a mapping's live entries
CREATE UNIQUE INDEX mapping_entries_item
    ON mapping_entries (mapping_id, source_id, item)
    WHERE deleted_at IS NULL;

CREATE INDEX mapping_entries_by_source ON mapping_entries (source_id);

-- for the "needs attention" list
CREATE INDEX mapping_entries_status ON mapping_entries (status, mapping_id);

CREATE TABLE playback_progress (
    mapping_id      INTEGER NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
    device_id       TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    queue           TEXT NOT NULL           -- JSON array of {source_id, item}
                    CHECK (length(queue) <= 400000),
    position        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    last_played_at  TEXT NOT NULL,
    PRIMARY KEY (mapping_id, device_id)
);

CREATE INDEX playback_progress_last_played ON playback_progress (last_played_at);
```

- **Two tables, not a JSON column**, so entries reference `media_sources` with a
  real foreign key, "what uses this source" is a query, and each entry records
  who added, changed or removed it.
- **Slug normalization.** The app trims and lowercases the slug on write and on
  lookup, so `Boop/Zelda` on a tag and `boop/zelda` in the UI are the same
  mapping. The slug is the lookup key a box sends, so it is indexed through the
  unique index.
- **Box scope.** `all_devices = 1` (the default) means every box resolves the
  slug and `mapping_devices` is ignored. With `all_devices = 0`, only the boxes
  listed in `mapping_devices` resolve it, and any other box gets the unknown-tag
  error. That list can hold one box, several, or none; a mapping with no boxes is
  parked and resolves nowhere. The flag exists so "none" and "all" are different
  things. Removing a box from the list is a hard delete. A listed box that is
  deleted or revoked never resolves, and `device_id` has no cascade because
  devices are soft-deleted.
- **Name versus slug.** The slug is the unique machine identifier written onto
  the physical tag. The name is the friendly label shown in the UI. It is free
  text and not unique, so two parents can each have a mapping called "Zelda".
- **Choosing the slug.** When a mapping is created the user can give the slug,
  for example the one already on a tag (a "set up this tag" screen fills it in
  from `tags.last_slug`). A given slug that is taken is rejected as taken. If no
  slug is given, the server proposes one from the name and, if it is taken,
  silently appends a short random suffix. The UI shows the final slug after
  creation. The slug can't be changed afterwards because tags already carry it;
  only the name and the contents can change.
- **One mapping per slug.** A slug plays the same thing on every box that can
  resolve it. What a slug plays is changed by editing its mapping's entries and
  settings, never by pointing the slug somewhere else.
- **An empty mapping is valid.** A mapping with no entries is a known slug that
  has nothing to play yet. A boop on it is answered and logged as
  `item_unavailable`, not `unknown_tag`.
- **Playback settings** live on the mapping, one pair per slug:

  | column | values | default |
  |--------|--------|---------|
  | `play_order` | `sequential`, `random` | `random` |
  | `play_type` | `one`, `all`, `all_repeat` | `one` |

  The defaults are in the schema, and the UI and server enforce them too.
  `play_type` is: play a single item, play everything once, or play everything
  and loop.
- **How the settings apply.** Resolution builds one pool: the live, playable
  entries in `position` order, with each collection expanded to its items in the
  source's own order. Then `play_order` is applied (`sequential` keeps the pool
  order, `random` shuffles it), then `play_type` decides how much of it plays.
  `sequential` with `one` always plays the first item; no rotation state is
  kept.
- **Deleting a mapping is a hard delete.** The server stops recognizing the slug
  at once, and its entries, box list and playback progress go with it through
  their cascades. The slug is free again afterwards. Any physical tag still
  carrying it resolves as an unknown tag, and plays whatever a later mapping
  with the same slug holds. Boop history keeps the slug as text, so past boops
  stay readable.
- **Entries.** `item` is the source's own id and is opaque to the app. `kind`
  says whether to play it directly or expand it. The same item can't be listed
  twice under one slug. `source_id` can't be changed on an existing entry; to
  move to another source, remove the entry and add a new one.
- **`position`** orders the entries. It is not unique, so reordering doesn't
  need to shuffle values to avoid collisions. Order by `position`, then
  `created_at`.
- **Editing the list** is add, remove (soft delete) and reorder, each stamped
  with the acting user. A change of `item` or `kind` on an existing entry is an
  edit: it sets `updated_*` and resets the entry's health (see Entry health).
- **Dangling references are allowed.** `source_id` has no cascade because
  sources are soft-deleted. An entry whose source is deleted or disabled can't
  play and is skipped at resolve time. If no playable entry remains, the box
  gets a source-unavailable error.

**Entry health.** An item can disappear from its source after a mapping is built.
The server records that, and the UI, which fetches live data from the source,
lets the user fix it.

- **Cached title.** `title` is the item's display name, supplied by the UI when it
  saves the entry. It lets the UI list a broken entry by name even when the
  source can't be reached. The server never writes it. It can be NULL.
- **`status`** is `unknown` (never checked, or just edited), `ok`, or `missing`
  (the source answered and doesn't have that item). `status_checked_at` is when
  it was last set. The server sets both whenever it contacts the source about an
  entry: expanding a collection, fetching an item's metadata, or proxying a
  stream. It writes them in the same short transaction as the boop outcome.
  They are telemetry and don't bump `updated_*`.
- **Source outages don't mark entries.** Failing to reach a source says nothing
  about its items, and marking them would flag every entry on that source after a
  single outage. Only a source that answers "not found" sets `missing`. Whether a
  source is reachable is not stored.
- **Choosing entries.** When building the pool for a boop, entries marked
  `missing` are left out as long as another entry is usable. If none is, the
  missing ones are tried again, so an item that reappears recovers on its own and
  its entry returns to `ok`.
- **Collections.** A collection entry's status is about the collection's own id.
  A member that is missing inside a working collection is skipped at play time
  and isn't recorded.
- **Outcome when nothing plays.** The box gets `source_unavailable` if every
  attempted entry failed because its source was unreachable, and
  `item_unavailable` otherwise.
- **Fixing it.** The UI lists live entries with `status = 'missing'`,
  which `mapping_entries_status` serves. The user can replace the entry or edit its
  `item`, and either resets the status to `unknown`. The UI can also ask for a
  re-check, which contacts the source and updates the status.
- **No mapping-level status is stored.** Whether a mapping can play at all is
  derived from its entries and their sources.

Resolving a slug reads its mapping, checks the box is in scope, then reads
its live entries in order and only entries whose source is live and enabled.

### Playback progress

`playback_progress` remembers where a box is in a slug's play order, so a server
restart doesn't lose it. It is short-lived runtime state, not user data. It is
named for what it holds because "session" already suggests login sessions, which
this design doesn't have.

- **When rows exist.** Only for `play_type` `all` and `all_repeat`. `one` keeps
  no state: `random` picks fresh on every boop and `sequential` always plays the
  first item.
- **Per box and per slug.** The kitchen box and the bedroom box track the same
  tag independently. The primary key is `(mapping_id, device_id)`.
- **What is stored.** `queue` is the resolved play order: collections expanded,
  `play_order` applied, as a list of source and item ids. `position` indexes into
  it. Storing the resolved list keeps a shuffle stable across restarts and stops
  later edits to a collection from shifting an in-progress pass.
- **On boop.** If a row exists and hasn't expired, playback resumes from
  `position`. Otherwise a fresh queue is built and `position` starts at 0.
- **Ending.** `all` deletes its row after the last item, so the next boop starts
  fresh. `all_repeat` wraps `position` back to 0 and keeps the row.
- **Expiry.** A row expires after an idle timeout measured from
  `last_played_at`: the `playback.idle_timeout_days` setting, 3 days by default. Reads treat an expired
  row as absent, so behavior doesn't depend on when cleanup runs. A periodic job
  deletes expired rows so the table doesn't grow.
- **Invalidation.** Changing a mapping's entries, `play_order` or `play_type`, or
  removing a box from its list, deletes the affected rows. Deleting a mapping
  removes its rows through the cascade. Devices are soft-deleted, so the app
  deletes a device's rows itself when the device is deleted.
- **No actor columns.** Rows are hard-deleted and carry no `created_by` or
  `deleted_*`.

## Tags seen

A record of every physical tag any box has read: when it was first seen, when it
was last seen, which box saw it each time, and what slug it carried each time.
It is separate from mappings. A mapping says what a slug plays; this says what
tags exist, including tags nobody has set up yet.

```sql
CREATE TABLE tags (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    uid                   TEXT NOT NULL UNIQUE
                          CHECK (length(uid) BETWEEN 1 AND 32
                                 AND uid NOT GLOB '*[^0-9A-F:]*'),
    first_seen_at         TEXT NOT NULL,
    first_seen_device_id  TEXT NOT NULL REFERENCES devices(id),
    first_slug            TEXT NOT NULL CHECK (length(first_slug) <= 128),
    last_seen_at          TEXT NOT NULL,
    last_seen_device_id   TEXT NOT NULL REFERENCES devices(id),
    last_slug             TEXT NOT NULL CHECK (length(last_slug) <= 128)
);

CREATE INDEX tags_last_seen ON tags (last_seen_at);
```

Each boop the server accepts is recorded with one statement:

```sql
INSERT INTO tags (uid, first_seen_at, first_seen_device_id, first_slug,
                  last_seen_at, last_seen_device_id, last_slug)
VALUES (:uid, :now, :device, :slug, :now, :device, :slug)
ON CONFLICT (uid) DO UPDATE SET
    last_seen_at        = excluded.last_seen_at,
    last_seen_device_id = excluded.last_seen_device_id,
    last_slug           = excluded.last_slug;
```

- **`uid`** is the tag's hardware UID as the box reports it, normalized by the app
  to uppercase hex with `:` separators. It identifies a tag but proves nothing:
  cheap tags can be cloned, so it is never used to authenticate or authorize.
- **First fields never change.** `first_seen_at`, `first_seen_device_id` and
  `first_slug` are written once, when the tag is first seen. The upsert leaves
  them alone.
- **Last fields update on every boop.** `last_slug` differing from `first_slug`
  means the tag was rewritten at some point.
- **Times are the server's receive time**, not the box's timestamp, so they are
  always on one clock.
- **Slugs are stored as read** from the tag (trimmed and capped at 128
  characters), not lowercased, so the record shows what the tag actually carried.
  A slug is arbitrary text from a physical object, so it is untrusted: shown as
  inert text, never interpolated into HTML or a query. It can be empty.
- **Mapping lookup is by normalized slug**, with no foreign key. A tag whose
  `last_slug` matches no mapping is an unmapped tag, which is what a future
  "unknown tag, set it up?" screen queries. A tag is never given a mapping
  automatically; the server only answers slugs that a user has mapped.
- **What is recorded.** Boops the server accepts from a known, live, unrevoked
  device with a valid payload, including tags with no mapping and tags that
  aren't BoopBox tags at all, such as a transit card. Rejected payloads aren't
  recorded.
- **No actor, no deletion, no retention purge.** The server writes these rows,
  not a user. The table grows only with the number of distinct tags, so it isn't
  purged the way boop history is.

## Boop history

An append-only log of boops: each time a box read a tag and the server handled
it, what happened. It backs "recently played", shows which tags are failing, and
helps diagnose a box. It is separate from `tags`, which keeps one row per
physical tag forever; this log is purged by age.

```sql
CREATE TABLE boops (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at    TEXT NOT NULL,
    device_id      TEXT NOT NULL REFERENCES devices(id),
    tag_id         INTEGER REFERENCES tags(id),
    slug           TEXT CHECK (length(slug) <= 128),
    box_at         TEXT,
    correlation_id TEXT CHECK (length(correlation_id) <= 64),
    outcome        TEXT NOT NULL CHECK (outcome IN (
                       'played', 'unknown_tag', 'out_of_scope',
                       'item_unavailable', 'source_unavailable',
                       'unsupported_version')),
    mapping_id     INTEGER REFERENCES mappings(id) ON DELETE SET NULL,
    entry_id       INTEGER REFERENCES mapping_entries(id) ON DELETE SET NULL,
    source_id      INTEGER REFERENCES media_sources(id),
    item           TEXT CHECK (length(item) <= 256),
    -- mapping_id and entry_id aren't required: deleting a mapping clears them
    CHECK (outcome <> 'played' OR (source_id IS NOT NULL AND item IS NOT NULL))
);

CREATE INDEX boops_received ON boops (received_at);
CREATE INDEX boops_device   ON boops (device_id, received_at);
CREATE INDEX boops_tag      ON boops (tag_id, received_at);
```

- **Outcomes.** `played` means playback was started. The rest are failures:
  `unknown_tag` (no mapping for the slug), `out_of_scope` (a mapping exists
  but not for this box), `item_unavailable` (including an empty mapping),
  `source_unavailable` and
  `unsupported_version`. `out_of_scope` is only for the log: the box is told
  `unknown_tag`, so it can't learn that a slug exists elsewhere.
- **What `played` records.** `mapping_id`, `entry_id`, `source_id` and `item`
  (the concrete item chosen, which for a collection is the expanded member). All
  four are written, but the CHECK requires only `source_id` and `item`, because
  deleting the mapping sets the other two to NULL. Failures record whatever was
  known by then.
- **Only the boop is logged.** Later items in an `all` or `all_repeat` queue are
  not boops and aren't recorded here. Neither are plays started from the UI.
- **`slug`** is stored as read from the tag, so the log stays accurate after a
  mapping is renamed or deleted. Same rules as in Tags seen: capped and treated as
  untrusted text.
- **`tag_id`** links to `tags`. It is NULL, along with `slug` and
  `correlation_id`, for an `unsupported_version` row where the payload couldn't
  be read.
- **Times.** `received_at` is the server's clock and is what ordering and
  retention use. `box_at` is the box's own timestamp converted to ISO-8601 UTC. It
  is informational and NULL if the box's clock was unset or implausible.
- **`correlation_id`** is the box's per-boop id. It is only unique per boot, so it
  isn't a key. MQTT redelivery can produce a duplicate row, and that isn't
  deduplicated.
- **Not every payload is logged.** Oversized or unparseable payloads are dropped
  without a row, so a misbehaving client can't fill the table. The exception is a
  payload with an unsupported protocol version, which is logged because it
  usually means a firmware mismatch worth seeing.
- **Written once the outcome is known**, in one short transaction together with
  the `tags` upsert. No network call to a media source happens inside that
  transaction.
- **Retention.** Rows older than `boops.retention_days` (default 90) are purged.
  Setting it to `0` keeps them forever.
  Nothing else references `boops`, so a purge can't orphan anything.
- **References after deletion.** Devices and sources are soft-deleted, so those
  foreign keys stay valid. Deleting a mapping sets `mapping_id` and `entry_id`
  to NULL on its boops, and the stored `slug` still says what was booped.

## Retention

What is removed, when, and by what. The rules live here in one place; the
sections for each table say only how long its data is kept.

| Data | Rule | Setting | Default |
|------|------|---------|---------|
| `boops` | rows older than the period | `boops.retention_days` | 90 |
| `auth_history` | rows older than the period | `auth.history_retention_days` | 90 |
| `playback_progress` | rows idle longer than the timeout | `playback.idle_timeout_days` | 3 |
| `invites` | finished invites older than the period | `invites.retention_days` | 30 |
| `backups` | all but the newest N successful backups, and their files | `backup.keep_count` | 7 |
| `tags` | never removed | | |
| soft-deleted rows | never removed | | |
| failed-login counters | never purged; reset on success, and restart after a quiet period | | |
| grants, `mappings`, `mapping_devices` | hard-deleted at the moment they are removed; a mapping takes its entries and progress with it | | |

`0` means keep forever for every retention setting except
`playback.idle_timeout_days`, which is an expiry, not a retention period, and
must be at least 1.

**Finished invites.** An invite is finished once it is used, revoked, or past its
expiry. It is purged `invites.retention_days` after the earliest of those
moments. An invite that is still open is never purged. Who invited whom stays
recorded on the user (`users.created_by`), so purging invites loses no
provenance.

**Soft-deleted rows are never purged.** This covers users, identities, devices,
sources and mapping entries (until their mapping is deleted). Other rows depend
on them: boop history points at devices, entries and sources, actor columns
point at users, and deleted usernames and device ids stay reserved by the rows
that hold them.
Purging would break those references and guarantees. A manual "erase" action is
not designed.

### Purge job

- **One job** runs every `retention.purge_interval_hours` (default 24) and once
  at startup.
- **Cutoffs** are computed from the current UTC time and compared to the stored
  ISO-8601 timestamps as text, using the indexes on `boops.received_at`,
  `auth_history.at` and `playback_progress.last_played_at`.
- **Batches.** Each class is deleted in batches of 1000 rows, one short
  transaction per batch. SQLite has one writer at a time, so a single huge
  `DELETE` would stall every other write, such as a boop being recorded. The
  batch size is a constant in code.
- **Off the event loop.** It runs on a worker thread like every database call.
- **Independent classes.** A failure in one class is logged and doesn't stop the
  others. A class set to `0` is skipped. The job logs how many rows it removed
  per class.
- **Idempotent.** Running it twice in a row changes nothing the second time.
- **Reads never depend on it.** Anything that has expired is already treated as
  absent when read (a stale `playback_progress` row, an expired invite), so the
  purge only reclaims space and its timing doesn't change behavior.
- **Shortening is destructive.** Lowering a retention period deletes the newly
  out-of-range data at the next run, and raising it again doesn't bring it back.
  The UI should confirm before saving a shorter period.
- **File size.** SQLite reuses freed pages but never shrinks the file by itself.
  The database is created with `PRAGMA auto_vacuum = INCREMENTAL`, which has to
  be set before the first table exists, and the purge job ends with
  `PRAGMA incremental_vacuum` to return the space.

## Backups

The server takes scheduled backups of the whole database while it keeps running.
When, how many, and where are all settings.

```sql
CREATE TABLE backups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    origin       TEXT NOT NULL CHECK (origin IN ('scheduled', 'manual')),
    requested_by INTEGER REFERENCES users(id),     -- manual backups only
    path         TEXT CHECK (length(path) <= 1024),
    size_bytes   INTEGER,
    error        TEXT CHECK (length(error) <= 1024),
    CHECK (status <> 'succeeded'
           OR (finished_at IS NOT NULL AND path IS NOT NULL AND size_bytes IS NOT NULL))
);

CREATE INDEX backups_started ON backups (started_at);
```

The table is the record of what was attempted, so the UI can show the last
success and any failures. It lives in the database it describes, which is fine: a
backup holds the history up to the moment it was taken.

### How a backup is taken

- **A consistent snapshot, not a file copy.** Copying a live database file, with
  its write-ahead log, can capture a half-written state. The server runs
  `VACUUM INTO` (or the online backup API) on a worker thread. It reads one
  consistent moment, and the app keeps recording boops and handling logins
  meanwhile.
- **Written under a temporary name**, then renamed to
  `boopbox-<UTC timestamp>.db` only after it has been checked. `VACUUM INTO`
  refuses to overwrite an existing file, and a partial file never carries a final
  name.
- **Checked before it counts.** The server opens the new file and runs an
  integrity check. Only then does the row become `succeeded`, with `path` and
  `size_bytes`. A file that fails the check is deleted and the row is `failed`
  with a short, sanitized message.
- **A failure never deletes a good backup.** Pruning only runs after a success.

### Schedule

- A scheduled backup is **due** when the newest successful backup started more
  than `backup.interval_hours` ago. Because it is computed from the last success,
  changing the interval takes effect immediately, and a restart neither skips a
  backup nor runs one twice.
- **After a failure** the next attempt is one hour later, or the interval if that
  is shorter, so a persistent problem isn't retried in a tight loop.
- **If the server was down** when a backup came due, one runs shortly after it
  starts, without delaying startup.
- **One at a time.** A `running` row blocks a second backup. At startup any
  `running` row is left over from a crash and is marked `failed` as interrupted.
- **Manual backups** can be started from the UI at any time. They are recorded
  with `origin = 'manual'` and the requesting user.
- `backup.enabled = false` stops scheduled backups; manual ones still work.

### Keeping and pruning

- After each success, only the newest `backup.keep_count` successful backups are
  kept. Older ones are deleted, file and row together. `0` keeps all of them.
- Failed rows older than the oldest kept success are removed as well.
- Pruning deletes only files named by the table's own `path` values. It never
  lists the directory and deletes what it finds.

### Destination and safety

- `backup.directory` must be a directory the server can write to. It is created if
  missing, and saving a new value tests it with a small write, so a bad path is
  caught in the UI instead of at 3 a.m.
- Backups on the same disk as the database protect against corruption and
  mistakes but not against losing the disk. Point the directory at a different
  disk or a mounted share. Backup files are ordinary files, so unlike the live
  SQLite database they are safe on a network share.
- A backup contains password hashes, encrypted credentials, the encrypted signing
  secrets, and login history including client addresses. Backup files are created
  readable only by the server's user, and the directory likewise. They aren't
  separately encrypted.
- **The encryption keys are not in the backup.** A restored database needs the
  keys it was encrypted with. With a different key the server refuses to start (see Encryption).
  The key must be saved somewhere else, and the UI should remind the owner to do
  so when backups are first enabled.

### Restore

Restore is done offline, not from the UI, because replacing a live database from
inside the app is risky:

1. Stop the server.
2. Replace the database file with the chosen backup, and remove any leftover
   write-ahead log and shared-memory files from the old database.
3. Start the server with a keyring that contains the keys the backup was
   encrypted with.

At startup the server checks the schema version (see Schema version). Anything
written after the backup was taken is lost.

## Settings

Everything configurable lives in the database and is edited in the UI. There are
no configuration files. Any setting can also be pinned from the environment (see
Environment overrides), which wins over the database. The only other inputs from
outside the database are the few environment values listed under Environment.

### Registry

The set of settings is defined in code, the same way permissions are. Each entry
has a key, a type (string, integer, boolean or enum), a default, validation
(range, length, allowed values), whether it is secret, and whether changing it
needs the affected component to reconnect. The database stores only overrides: a
key with no row has its default. Resetting a setting to its default deletes its
row. A row whose key isn't in the registry is ignored.

### Settings table

```sql
CREATE TABLE settings (
    key         TEXT PRIMARY KEY
                CHECK (length(key) BETWEEN 1 AND 64 AND key NOT GLOB '*[^a-z0-9._]*'),
    value       TEXT NOT NULL CHECK (length(value) <= 16384),  -- JSON; ciphertext if encrypted
    encrypted   INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER REFERENCES users(id)                   -- NULL = system
);
```

- `value` is JSON text, so integers, booleans and strings round-trip without a
  per-key column type. The registry validates it before it is written.
- `encrypted = 1` means `value` is ciphertext (see Encryption). The flag is
  stored so a row is always decoded the way it was written, even if the registry
  changes later.
- Secret values are never returned by the API. It reports only whether one is set,
  and editing can only replace it.
- Changing the MQTT settings makes the MQTT client reconnect. Other settings take
  effect the next time they are read.
- Settings are not soft-deleted and have no `created_*`: a row is an override that
  exists or doesn't.

### Setting keys

| key | type | default | notes |
|-----|------|---------|-------|
| `public_base_url` | URL, up to 2048 | `http://127.0.0.1:9685` | the server's public root: boxes use it, and invite links are built on it |
| `mqtt.host` | string | `localhost` | |
| `mqtt.port` | integer 1-65535 | `1883` | |
| `mqtt.username` | string | empty | |
| `mqtt.password` | secret | unset | |
| `mqtt.tls` | boolean | `false` | |
| `mqtt.tls_ca` | PEM text, up to 16384 | empty | CA certificate for the broker |
| `streaming.mode` | enum | `proxy` | `redirect` is a later option |
| `streaming.pause_budget_seconds` | integer 0-86400 | `1800` | added to item duration for stream token expiry |
| `ota.manifest_version` | string, up to 32 | empty | no manifest is served while empty |
| `auth.token_lifetime_hours` | integer 1-720 | `8` | |
| `invites.expiry_days` | integer 1-30 | `3` | |
| `auth.lockout_threshold` | integer 1-100 | `5` | failed local logins before a lock |
| `auth.lockout_minutes` | integer 1-1440 | `15` | lock length, and the window for counting failures |
| `auth.history_retention_days` | integer 0-3650 | `90` | how long login history is kept; `0` = forever |
| `auth.trust_forwarded_header` | boolean | `false` | use the proxy's forwarded client address for `client_ip` |
| `playback.idle_timeout_days` | integer 1-365 | `3` | |
| `boops.retention_days` | integer 0-3650 | `90` | how long boop history is kept; `0` = forever |
| `invites.retention_days` | integer 0-3650 | `30` | how long finished invites are kept; `0` = forever |
| `retention.purge_interval_hours` | integer 1-168 | `24` | how often the purge job runs |
| `backup.enabled` | boolean | `true` | scheduled backups on or off |
| `backup.interval_hours` | integer 1-720 | `24` | how often a scheduled backup is due |
| `backup.keep_count` | integer 0-1000 | `7` | successful backups kept; `0` = keep all |
| `backup.directory` | string, up to 1024 | a `backups` folder next to the database | where backup files are written |
| `secrets.stream` | secret | generated | signs stream URLs |
| `secrets.auth_token` | secret | generated | signs login tokens |

**Retention settings.** Every setting that says how long data is kept follows one
rule: `0` means keep forever, and the purge job skips that data class entirely.
Keeping forever means the data grows without bound and the database and its
backups grow with it.

### Environment overrides

Any setting in the registry can be set from the environment. This covers
headless and compose deployments, and recovery when a bad value (a wrong MQTT
host, say) is saved in the database.

- **Name.** `BOOPBOX_` plus the key in upper case with `.` replaced by `_`:
  `mqtt.host` is `BOOPBOX_MQTT_HOST`, `public_base_url` is
  `BOOPBOX_PUBLIC_BASE_URL`. A test asserts that no two registry keys map to the
  same name.
- **Precedence.** Environment, then the database row, then the registry default.
  An empty variable counts as unset.
- **Read once at startup** and validated by the registry like any other value.
  An invalid value refuses startup with an error naming the variable.
- **Read-only in the UI.** An overridden setting is shown with its effective
  value and marked as set by the environment. The API rejects writes to it. Any
  database row for it is left alone, so removing the variable falls back to the
  stored value on the next start.
- **Secrets** set this way (`mqtt.password`, for example) are held in memory only,
  never written to the database and never returned by the API.
- **Generated secrets.** If `secrets.stream` or `secrets.auth_token` is set in
  the environment, the server uses it and doesn't generate one, and rotating it
  from the UI is disabled.
- `BOOPBOX_DEFAULT_*` and the keyring variables below are not settings and
  aren't covered by this rule.

### Environment

Apart from setting overrides, only these come from the environment:

| value | why it can't be a setting |
|-------|---------------------------|
| `BOOPBOX_DEFAULT_USERNAME`, `BOOPBOX_DEFAULT_PASSWORD` | create the owner on first run (see Bootstrap owner); ignored once any user exists |
| `BOOPBOX_SECRET_KEYS_FILE`, or `BOOPBOX_SECRET_KEY` | the keyring that encrypts the database's secrets, so it can't be stored in it. The file allows rotating keys without a restart; the single variable is a one-key shorthand (see Encryption) |
| location of the database file | needed to open the database at all |

Network binding and container wiring are deployment details, not application
data.

### Encryption

Secret settings and `media_sources.secret_encrypted` use one scheme.

- **Keyring.** One or more keys, each 32 random bytes, base64url-encoded. The
  first is the **active** key and encrypts every new value. Any others are
  **retired**: they can only decrypt.
  - From a file named by `BOOPBOX_SECRET_KEYS_FILE`: one key per line, blank lines
    and `#` comments ignored, readable only by the server's user.
  - Or from `BOOPBOX_SECRET_KEY`, which holds a single key. If both are set the
    file wins. If neither is set the server refuses to start.
  - A key's **id** (`kid`) is the first 8 hex characters of its SHA-256. It isn't
    secret and only says which key a value was encrypted with.
- **Cipher.** Authenticated encryption (AES-256-GCM) with a fresh random nonce
  per value. The setting key, or the source's id, is bound in as associated data,
  so a ciphertext copied into a different row fails to decrypt.
- **Format.** `v1:<kid>:<base64url>`, where the last part is the nonce followed by
  the ciphertext. The `kid` lets the server pick the right key for each value,
  which is what makes rotation possible without a restart. The `v1` leaves room to
  change the algorithm later.
- **Key check.** On first run the server stores an encrypted canary value. At
  every startup, and at every keyring reload, it checks two things: the canary
  decrypts, and every `kid` used by any stored value is in the keyring. If either
  fails, startup is refused with a clear error. A reload that fails the check is
  rejected and the previous keyring stays in use. The server never falls back to
  regenerating secrets, which could silently replace good data.
- **Loss.** A value whose key is missing from the keyring is unrecoverable. If
  every key is lost, source credentials and the MQTT password must be re-entered
  on a fresh database, and the signing secrets regenerate. Back the keys up
  separately from database backups.

### Key rotation

Keys can be rotated while the server keeps running, with no restart and no
interruption to anything playing. The mechanism is the keyring file and the `kid`
on every value; the environment variable alone can't change in a running process,
so rotation needs the file.

1. **Add the new key.** Generate a new key and put it on the first line of the
   keyring file, with the current key left below it.
2. **Reload.** An admin action in the UI, or a `SIGHUP`, makes the server re-read
   the file. It applies the Key check and swaps the keyring in memory only if that
   passes. From then on, every new or edited secret uses the new key, and old
   values still decrypt with the retired one.
3. **Re-encrypt.** A background job moves every value still under a retired key
   to the active key. It covers the encrypted rows in `settings`, including the
   canary, and `media_sources.secret_encrypted`. It starts after a reload and can
   be started again from the UI.
4. **Retire.** When no value uses the old key any more, remove its line and
   reload. A reload that drops a key still in use is rejected.

How the re-encryption stays safe:

- **Compare-and-set.** Each value is updated with a condition that it still holds
  the ciphertext that was read (`UPDATE ... WHERE value = <old ciphertext>`). If a
  user edited the secret meanwhile, the update matches no rows and is skipped,
  because the new write is already under the active key.
- **One value per transaction,** so nothing holds a long lock and a failure
  loses at most one value's progress.
- **Resumable and idempotent.** The state is just which `kid` each value carries.
  An interrupted run continues on the next trigger, and running it again changes
  nothing once everything is on the active key. The progress shown in the UI is
  the count of values per `kid`.
- **Always readable.** At every moment during a rotation, every value can be
  decrypted by some key in the keyring, so nothing needs to pause.
- **Not an edit.** Re-encryption doesn't touch `updated_*`.

Things rotation doesn't do:

- **Backups keep their old keys.** A backup holds values under the keys that were
  active when it was taken, so restoring one needs those keys in the keyring.
  Keep retired keys for as long as any backup that needs them is kept. Extra
  retired keys cost nothing. After a restore, the re-encrypt job brings the values
  up to the active key.
- **A leaked key.** Rotation re-encrypts the database but doesn't change the
  Jellyfin API keys or the MQTT password themselves. If a key leaked together with
  a copy of the database, change those credentials at their sources.
- **Signing secrets** (`secrets.stream`, `secrets.auth_token`) are not encryption
  keys. Rotating them is a separate action with its own effects (see Generated
  secrets).
- **One server process.** A reload reaches the process that receives it. The
  server runs as a single process, so that is all of it.

### Generated secrets

`secrets.stream` and `secrets.auth_token` are 32 random bytes, generated by the
server, never entered by hand.

- On startup, if a secret has no row, it is generated and stored once, encrypted,
  with `updated_by` NULL (system). If a row exists it is never regenerated.
- An admin can rotate either one on demand. Rotating `secrets.auth_token` logs
  everyone out. Rotating `secrets.stream` invalidates stream URLs already sent
  to boxes, so anything mid-play would fail on its next request.

## Flows

### Bootstrap owner

At startup, if `users` has no rows (live or deleted):

1. Read `BOOPBOX_DEFAULT_USERNAME` and `BOOPBOX_DEFAULT_PASSWORD` from the
   environment.
2. Create a `users` row with `is_owner = 1` and NULL `created_by`.
3. Create a `local` identity (username lowercased) with an Argon2id hash of the
   password and `must_change_password = 1`.

If `users` has any rows, the env vars are not read at all. The env password is
only ever a first-login credential; once changed, only the DB hash matters.
At first login the owner is required to set a new password before doing
anything else.

### Invite and redeem

1. An admin (`users.manage`) creates a `users` row (name, optional email) and
   issues an invite. The code is shown once.
2. The admin gives the code to the person.
3. The person enters the code and picks a login method:
   - local: chooses a username and password
   - Google or Jellyfin: completes that provider's flow
4. The server creates the `auth_identities` row, sets `invites.used_at`, and the
   user is active.

Invalid, expired, revoked, or already-used codes are rejected with a generic
error that doesn't say which. A local username that is taken, including by a
deleted user, is rejected as taken.

### Re-invite (lost access)

An admin issues a new invite for an existing, already-active user. Redeeming it
replaces that user's identity with the newly chosen method. In one transaction:

1. The user's live identity is soft-deleted (`deleted_by` = the admin who issued
   the invite).
2. The new identity is inserted.

Exception: if the user chooses the same local username they already had, the
existing row is revived (clear `deleted_at`/`deleted_by`, set the new
`secret_hash`) instead of inserting, since the reserved username would otherwise
block them. A username belonging to any other user is still rejected.

Permissions and the user row are untouched.

**The owner can't be re-invited.** Issuing an invite for the owner is rejected by
the app. Otherwise anyone with `users.manage` could redeem it, replace the
owner's login, and hold an account that can't be deleted. A lost owner login is
fixed offline; see Owner recovery.

### Owner recovery

Recovering the owner account needs shell access to the server host. Nothing
reachable over the network can trigger it.

1. Stop the server.
2. Run `boopbox reset-owner` against the database file. It prompts for a
   username and password rather than taking them as arguments, so they stay out
   of shell history. It doesn't need the keyring.
3. In one transaction it soft-deletes the owner's live identity (`deleted_by`
   NULL, meaning system) and inserts a `local` identity with an Argon2id hash
   and `must_change_password = 1`. The username rules are the same as for a
   re-invite: the owner's own earlier username is revived, and anyone else's is
   rejected. It also increments `token_version`.
4. Start the server.

### Deleting a user

Soft delete, done by the app in one transaction:

1. Set `deleted_at` / `deleted_by` on the user.
2. Soft-delete their live identity (keeps the local username reserved).
3. Soft-delete their unused invites.
4. Leave their grants in place; the permission check denies deleted users, so
   they are inert.

The owner cannot be deleted (CHECK constraint).

### Request authentication

Stateless signed tokens, valid for `auth.token_lifetime_hours` (8 by default).
A token carries the user id, that user's `token_version` at the time it was
issued, and its expiry.

On every request the server:

1. Verifies the signature and expiry.
2. Loads the user and rejects the request if the user is disabled or deleted.
3. Rejects the request if the token's version differs from
   `users.token_version`.
4. Checks permissions from the DB.

Grant changes, disabling and deleting therefore take effect on the next request,
and so does revoking tokens.

**Revoking tokens.** Incrementing `users.token_version` invalidates every token
that user already holds, with no session table. It is incremented when:

- the user's password changes, whether they change it or an admin resets it
- a re-invite is redeemed (the login method is replaced)
- the owner is recovered with `boopbox reset-owner`
- the user is disabled or deleted
- the user, or an admin on their behalf, chooses "log out everywhere"

The response to a password change includes a new token carrying the new version,
so the person changing it stays logged in on that device and is logged out
everywhere else.

The version is a counter, not a "valid after" timestamp. A timestamp has a
same-second edge case: a token issued right after the change can be rejected as
older than it, or one issued just before it accepted. A counter compares
exactly. It is per user, so revoking one user's tokens doesn't affect anyone
else. To log out everyone at once, rotate `secrets.auth_token`.

The version bump is part of the change that causes it and is not counted as a
separate edit, so it doesn't touch `updated_*`.

The remaining limit is that a single token can't be revoked alone: revocation
applies to all of a user's tokens.

The token signing secret is its own setting (`secrets.auth_token`), separate from
the stream signing secret.

## Open questions

- **Advancing through a queue.** For `all` and `all_repeat`, how a box gets from
  one item to the next is a transport question, not a storage one, and is
  undecided. The schema supports both options:
  - *Server-fed stream.* The server keeps one HTTP response open and continues it
    with the next item from the source. The box needs no firmware change and no
    "finished" message, and the server owns the queue. It needs the items joined
    into one audio format (raw concatenation is only clean for something like
    MP3, otherwise a transcode through the source or ffmpeg). A continuous
    stream has no byte offsets, so resuming after a pause restarts the current
    item or uses the stored position. `all_repeat` needs a stop condition,
    because a token's expiry is only checked when a connection opens.
  - *Box-reported.* The box publishes an event when an item finishes and the
    server sends the next `play`. Per-item tokens and ranges stay as they are, but
    it needs a firmware change and a recovery path for a missed event.

  With the server-fed option, `playback_progress` may need an `offset_ms` column
  to resume part-way through an item. A spike on the real box, streaming a few
  joined MP3s, would settle the format question.
- **Self-service** (a user changing their own password or display name without
  `users.manage`): deferred, not needed yet.
