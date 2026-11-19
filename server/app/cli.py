"""`boopbox` command line: offline tasks against the database file."""

import argparse
import asyncio
import getpass
import secrets
import sys
from pathlib import Path

from app.config import get_env
from app.crypto import KEY_BYTES, Keyring, KeyringError, source_aad
from app.db import SchemaError, sources
from app.db.engine import Database
from app.db.migrate import prepare_database
from app.db.timestamps import timestamp
from app.startup import check_keys


def _read_secret(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\n")


async def _set_source_secret(source_id: int, secret: str | None) -> str | None:
    env = get_env()
    if not Path(env.db_path).is_file():
        return f"no database at {env.db_path}; start the server once to create it"
    keyring = Keyring.from_env(env)
    db = Database.open(env.db_path)
    try:
        await prepare_database(db.engine)
        await check_keys(db, keyring)
        value = keyring.encrypt(secret, source_aad(source_id)) if secret else None
        async with db.write() as conn:
            if not await sources.set_secret(conn, source_id, value, timestamp()):
                return f"media source {source_id} does not exist or is deleted"
    finally:
        await db.dispose()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boopbox")
    commands = parser.add_subparsers(dest="command", required=True)
    source_secret = commands.add_parser(
        "set-source-secret",
        help="encrypt and store a media source's credential (read from a prompt "
        "or stdin)",
    )
    source_secret.add_argument("source_id", type=int)
    source_secret.add_argument(
        "--clear", action="store_true", help="remove the stored credential"
    )
    commands.add_parser("generate-key", help="print a new BOOPBOX_SECRET_KEY")
    args = parser.parse_args(argv)

    if args.command == "generate-key":
        print(secrets.token_urlsafe(KEY_BYTES))
        return 0

    secret = None
    if not args.clear:
        secret = _read_secret(f"Credential for media source {args.source_id}: ")
        if not secret:
            print("no credential given; use --clear to remove one", file=sys.stderr)
            return 1
    try:
        problem = asyncio.run(_set_source_secret(args.source_id, secret))
    except (KeyringError, SchemaError) as err:
        problem = str(err)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    action = "cleared" if args.clear else "stored"
    print(f"{action} credential for source {args.source_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
