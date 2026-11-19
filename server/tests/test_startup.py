import base64
import io

import pytest

from app import cli
from app.config import RESERVED_ENV_NAMES, get_env
from app.crypto import (
    DecryptError,
    Keyring,
    KeyringError,
    key_id,
    setting_aad,
    source_aad,
)
from app.settings import REGISTRY, SettingError, parse_env_overrides
from app.startup import StartupError, start
from tests.conftest import T, add_source, query, run_sql

KEY_A = b"a" * 32
KEY_B = b"b" * 32


def _b64(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode()


async def _start_and_stop(env):
    services = await start(env)
    await services.aclose()
    return services


# --- startup sequence ---


async def test_first_start_seeds_everything(env):
    await _start_and_stop(env)
    db = env.db_path
    assert {r[0] for r in query(db, "SELECT id FROM permissions")} >= {
        "users.manage",
        "ota.manage",
        "device.view",
    }
    secrets = dict(query(db, "SELECT key, value FROM settings WHERE encrypted = 1"))
    assert set(secrets) == {"keyring.canary", "secrets.stream", "secrets.auth_token"}
    assert all(v.startswith("v1:") for v in secrets.values())


async def test_restart_keeps_generated_secrets_and_owner(env, monkeypatch):
    await _start_and_stop(env)
    before = query(env.db_path, "SELECT key, value FROM settings ORDER BY key")
    monkeypatch.delenv("BOOPBOX_DEFAULT_USERNAME")
    monkeypatch.delenv("BOOPBOX_DEFAULT_PASSWORD")
    get_env.cache_clear()
    await _start_and_stop(get_env())
    assert query(env.db_path, "SELECT key, value FROM settings ORDER BY key") == before
    assert query(env.db_path, "SELECT count(*) FROM users") == [(1,)]


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("BOOPBOX_DEFAULT_USERNAME", "", "set BOOPBOX_DEFAULT_USERNAME"),
        ("BOOPBOX_DEFAULT_USERNAME", "a/b", "BOOPBOX_DEFAULT_USERNAME"),
        ("BOOPBOX_DEFAULT_PASSWORD", "short", "BOOPBOX_DEFAULT_PASSWORD"),
    ],
)
async def test_owner_needs_valid_environment(env, monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)
    get_env.cache_clear()
    with pytest.raises(StartupError, match=message):
        await start(get_env())
    assert query(env.db_path, "SELECT count(*) FROM users") == [(0,)]


async def test_interrupted_backup_is_marked_failed(env):
    await _start_and_stop(env)
    run_sql(
        env.db_path,
        "INSERT INTO backups (started_at, status, origin) "
        f"VALUES ('{T}', 'running', 'scheduled')",
    )
    await _start_and_stop(env)
    assert query(env.db_path, "SELECT status, error FROM backups") == [
        ("failed", "interrupted")
    ]


async def test_missing_keyring_refuses(env, monkeypatch):
    monkeypatch.delenv("BOOPBOX_SECRET_KEY")
    get_env.cache_clear()
    with pytest.raises(KeyringError, match="no encryption key"):
        await start(get_env())


async def test_wrong_key_refuses_existing_database(env, monkeypatch):
    await _start_and_stop(env)
    monkeypatch.setenv("BOOPBOX_SECRET_KEY", _b64(KEY_B))
    get_env.cache_clear()
    with pytest.raises(KeyringError, match="doesn't match"):
        await start(get_env())


async def test_secret_under_unknown_key_refuses(env):
    await _start_and_stop(env)
    foreign = Keyring([KEY_B]).encrypt("x", source_aad(1))
    add_source(env.db_path, 1, secret_encrypted=foreign)
    with pytest.raises(KeyringError, match=key_id(KEY_B)):
        await start(env)


async def test_retired_key_still_decrypts(env, monkeypatch, tmp_path):
    await _start_and_stop(env)
    keys_file = tmp_path / "keys"
    keys_file.write_text(f"# rotated\n{_b64(KEY_B)}\n\n{_b64(b'k' * 32)}\n")
    keys_file.chmod(0o600)
    monkeypatch.delenv("BOOPBOX_SECRET_KEY")
    monkeypatch.setenv("BOOPBOX_SECRET_KEYS_FILE", str(keys_file))
    get_env.cache_clear()
    services = await start(get_env())
    try:
        assert services.keyring.active_kid == key_id(KEY_B)
        assert len(await services.settings.get("secrets.stream")) >= 32
    finally:
        await services.aclose()


async def test_invalid_env_override_names_the_variable(env, monkeypatch):
    monkeypatch.setenv("BOOPBOX_MQTT_PORT", "lots")
    with pytest.raises(SettingError, match="BOOPBOX_MQTT_PORT"):
        await start(env)


async def test_invalid_stored_setting_refuses(env):
    await _start_and_stop(env)
    run_sql(
        env.db_path,
        "INSERT INTO settings (key, value, updated_at) "
        f"VALUES ('mqtt.port', '0', '{T}')",
    )
    with pytest.raises(SettingError, match="mqtt.port"):
        await start(env)


# --- settings ---


async def test_precedence_env_then_row_then_default(env, monkeypatch):
    await _start_and_stop(env)
    run_sql(
        env.db_path,
        "INSERT INTO settings (key, value, updated_at) VALUES "
        f"('mqtt.host', '\"from-db\"', '{T}'), "
        f"('auth.lockout_threshold', '9', '{T}'), "
        f"('not.a.setting', '1', '{T}')",
    )
    monkeypatch.setenv("BOOPBOX_AUTH_LOCKOUT_THRESHOLD", "3")
    services = await start(env)
    try:
        values = await services.settings.snapshot()
        assert values["mqtt.host"] == "from-db"
        assert values["auth.lockout_threshold"] == 3
        assert values["mqtt.port"] == 1  # from the test environment
        assert values["invites.expiry_days"] == 3
        assert "not.a.setting" not in values
        assert services.settings.overridden("auth.lockout_threshold")
    finally:
        await services.aclose()


async def test_env_secret_is_used_and_not_stored(env, monkeypatch):
    secret = "x" * 40
    monkeypatch.setenv("BOOPBOX_SECRETS_AUTH_TOKEN", secret)
    services = await start(env)
    try:
        assert await services.settings.get("secrets.auth_token") == secret
    finally:
        await services.aclose()
    keys = [r[0] for r in query(env.db_path, "SELECT key FROM settings")]
    assert "secrets.auth_token" not in keys


def test_env_names_are_unique_and_unreserved():
    names = [s.env_name for s in REGISTRY.values()]
    assert len(names) == len(set(names))
    assert not set(names) & RESERVED_ENV_NAMES


def test_env_parsing():
    parsed = parse_env_overrides(
        {
            "BOOPBOX_MQTT_TLS": "yes",
            "BOOPBOX_MQTT_USERNAME": "",
            "BOOPBOX_PUBLIC_BASE_URL": "https://boop.example/",
            "BOOPBOX_DB_PATH": "x.db",
            "BOOPBOX_STREAM_SECRET": "stale",
        }
    )
    assert parsed == {"mqtt.tls": True, "public_base_url": "https://boop.example"}
    for name, value in [
        ("BOOPBOX_MQTT_TLS", "maybe"),
        ("BOOPBOX_STREAMING_MODE", "telepathy"),
        ("BOOPBOX_PUBLIC_BASE_URL", "ftp://x"),
        ("BOOPBOX_PUBLIC_BASE_URL", "https://u:p@x"),
        ("BOOPBOX_SECRETS_STREAM", "too-short"),
    ]:
        with pytest.raises(SettingError, match=name):
            parse_env_overrides({name: value})


# --- keyring ---


def test_keyring_round_trip_and_binding():
    ring = Keyring([KEY_A])
    sealed = ring.encrypt("hunter2", setting_aad("mqtt.password"))
    assert sealed.startswith(f"v1:{key_id(KEY_A)}:")
    assert ring.decrypt(sealed, setting_aad("mqtt.password")) == "hunter2"
    assert sealed != ring.encrypt("hunter2", setting_aad("mqtt.password"))
    with pytest.raises(DecryptError):
        ring.decrypt(sealed, setting_aad("secrets.stream"))
    with pytest.raises(DecryptError):
        Keyring([KEY_B]).decrypt(sealed, setting_aad("mqtt.password"))
    assert Keyring([KEY_B, KEY_A]).decrypt(sealed, setting_aad("mqtt.password"))


def test_keyring_rejects_bad_keys():
    with pytest.raises(KeyringError):
        Keyring([b"short"])
    with pytest.raises(KeyringError):
        Keyring([])


# --- CLI ---


def test_generate_key(capsys):
    assert cli.main(["generate-key"]) == 0
    printed = capsys.readouterr().out.strip()
    assert len(base64.urlsafe_b64decode(printed + "=")) == 32


async def _cli(args, stdin=""):
    import asyncio
    import sys

    old = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        return await asyncio.to_thread(cli.main, args)
    finally:
        sys.stdin = old


async def test_set_source_secret(env, capsys):
    await _start_and_stop(env)
    add_source(env.db_path, 1)
    assert await _cli(["set-source-secret", "1"], "jf-api-key\n") == 0
    sealed = query(env.db_path, "SELECT secret_encrypted FROM media_sources")[0][0]
    ring = Keyring.from_env(env)
    assert ring.decrypt(sealed, source_aad(1)) == "jf-api-key"

    assert await _cli(["set-source-secret", "1", "--clear"]) == 0
    assert query(env.db_path, "SELECT secret_encrypted FROM media_sources") == [(None,)]
    assert await _cli(["set-source-secret", "7"], "x\n") == 1
    assert "does not exist" in capsys.readouterr().err


async def test_set_source_secret_needs_a_database(env, capsys):
    assert await _cli(["set-source-secret", "1"], "x\n") == 1
    assert "no database" in capsys.readouterr().err
