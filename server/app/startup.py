"""Everything that must succeed before the server accepts a request."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.auth.passwords import (
    hash_password,
    normalize_password,
    normalize_username,
    password_problem,
    username_problem,
)
from app.config import Environment, raw_environment
from app.crypto import DecryptError, Keyring, KeyringError, kid_of, setting_aad
from app.db import backups, permissions, users
from app.db import settings as setting_rows
from app.db.engine import Database
from app.db.migrate import prepare_database
from app.db.timestamps import timestamp
from app.permissions import CATALOG
from app.settings import SettingsStore, defaults, parse_env_overrides
from app.sources import SourceRegistry

log = logging.getLogger(__name__)

CANARY_KEY = "keyring.canary"
_CANARY_TEXT = "boopbox keyring canary"


class StartupError(RuntimeError):
    pass


@dataclass
class Services:
    env: Environment
    db: Database
    keyring: Keyring
    settings: SettingsStore
    sources: SourceRegistry

    async def aclose(self) -> None:
        await self.sources.aclose()
        await self.db.dispose()


async def check_keys(db: Database, keyring: Keyring) -> None:
    """The canary decrypts and every stored ciphertext's key is present."""
    aad = setting_aad(CANARY_KEY)
    async with db.write() as conn:
        row = await setting_rows.get(conn, CANARY_KEY)
        if row is None:
            await setting_rows.put(
                conn,
                CANARY_KEY,
                keyring.encrypt(json.dumps(_CANARY_TEXT), aad),
                encrypted=True,
                now=timestamp(),
            )
        else:
            try:
                keyring.decrypt(row.value, aad)
            except DecryptError as err:
                raise KeyringError(
                    f"the keyring doesn't match this database ({err}); start with "
                    "the keys it was encrypted with"
                ) from None
        values = await setting_rows.encrypted_values(conn)
    try:
        used = {kid_of(v) for v in values}
    except DecryptError as err:
        raise KeyringError(f"a stored secret is malformed: {err}") from None
    missing = used - keyring.kids
    if missing:
        kids = ", ".join(sorted(missing))
        raise KeyringError(f"stored secrets use keys missing from the keyring: {kids}")


async def bootstrap_owner(db: Database, env: Environment) -> None:
    """Create the owner from the environment, only while `users` is empty."""
    async with db.read() as conn:
        if await users.any_user(conn):
            return
    if not env.default_username or not env.default_password:
        raise StartupError(
            "no users exist yet: set BOOPBOX_DEFAULT_USERNAME and "
            "BOOPBOX_DEFAULT_PASSWORD to create the owner"
        )
    username = normalize_username(env.default_username)
    password = normalize_password(env.default_password)
    if problem := username_problem(username):
        raise StartupError(f"BOOPBOX_DEFAULT_USERNAME: {problem}")
    if problem := password_problem(password):
        raise StartupError(f"BOOPBOX_DEFAULT_PASSWORD: {problem}")
    secret_hash = await hash_password(password)
    async with db.write() as conn:
        if await users.any_user(conn):
            return
        await users.create_owner(conn, username, secret_hash, timestamp())
    log.info(
        "created owner account %r; its password must be changed at first login",
        username,
    )


async def start(env: Environment) -> Services:
    keyring = Keyring.from_env(env)
    overrides = parse_env_overrides(raw_environment())
    Path(env.db_path).resolve().parent.mkdir(parents=True, exist_ok=True)
    db = Database.open(env.db_path)
    try:
        await prepare_database(db.engine)
        async with db.write() as conn:
            await permissions.upsert_catalog(conn, CATALOG)
        await check_keys(db, keyring)
        settings = SettingsStore(
            db,
            keyring,
            env_overrides=overrides,
            default_values=defaults(env.db_path),
        )
        await settings.check_stored()
        await settings.ensure_generated_secrets()
        await bootstrap_owner(db, env)
        async with db.write() as conn:
            if interrupted := await backups.fail_interrupted(conn, timestamp()):
                log.warning("marked %d interrupted backup(s) as failed", interrupted)
    except BaseException:
        await db.dispose()
        raise
    return Services(env, db, keyring, settings, SourceRegistry(db, keyring))
