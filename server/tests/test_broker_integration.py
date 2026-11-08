"""Broker-backed integration test .

Opt-in and Docker-gated: brings up the real bundled Mosquitto broker + the app
via `docker compose --profile bundled-broker up` against an isolated test stack,
then exercises the live broker + ACLs + stream path end to end. Excluded from the
unit suite by the `broker_integration` marker (see pyproject addopts); run with:

    pytest -m broker_integration

The stack is isolated from the developer's own config/.env: a tmp project dir
with a fake-source config, a generated password file, and a compose override
wiring the app to the broker. It reuses the repo's real broker config/ACL files
(server/mosquitto/{mosquitto.conf,aclfile}) so the ACLs under test are the ones
shipped, not a copy.
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.broker_integration

SERVER_DIR = Path(__file__).resolve().parents[1]
MOSQUITTO_DIR = SERVER_DIR / "mosquitto"
MOSQUITTO_IMAGE = "eclipse-mosquitto:2.0"

SERVER_USER = "boopbox-server"
SERVER_PASS = "server-pw"
BOX_ID = "boop-test"
BOX_PASS = "box-pw"
OTHER_BOX_ID = "boop-other"
STREAM_SECRET = "integration-secret"

# Host-published ports, offset from the real broker (1883) and dev app (9685) to
# avoid collisions. Inside the compose network they stay 1883 and 9685.
BROKER_PORT = int(os.environ.get("BOOPBOX_TEST_BROKER_PORT", "1884"))
APP_PORT = int(os.environ.get("BOOPBOX_TEST_APP_PORT", "9686"))
APP_BASE = f"http://127.0.0.1:{APP_PORT}"

# Containers run as the invoking user so mounted files stay host-owned and
# cleanup never hits root-owned leftovers. Mosquitto 2.0 accepts this as long as
# its config/password files are not world-readable (chmod 0700 below).
HOST_USER = f"{os.getuid()}:{os.getgid()}"

# Fake source + one item mapping so a boop yields a playable stream with real
# bytes (the built-in "fake" source serves fixed bytes for item "fake-item").
TEST_CONFIG = textwrap.dedent(
    """
    sources:
      - id: fake-main
        type: fake
        base_url: http://unused
    mappings:
      "boop/item":
        - source: fake-main
          item: fake-item
          kind: item
    streaming:
      mode: proxy
      pause_budget_seconds: 1800
    ota:
      manifest_version: "0.1.0"
    """
)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        info = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20, check=False
        )
        compose = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return info.returncode == 0 and compose.returncode == 0


def _mosquitto_passwd(password_file: Path, user: str, password: str, *, create: bool):
    """Add a hashed account in `password_file` via the broker image.

    Runs inside the image as the host user, so no host mosquitto_passwd is
    required and the file is owned by the caller. chmod 0700 keeps mosquitto 2.0
    from refusing a world-readable file; the running broker user owns it, which
    satisfies the broker's ownership check too.
    """
    flag = "-c " if create else ""
    name = password_file.name
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            HOST_USER,
            "-v",
            f"{password_file.parent}:/work",
            MOSQUITTO_IMAGE,
            "sh",
            "-c",
            f"mosquitto_passwd {flag}-b /work/{name} {user} {password} "
            f"&& chmod 0700 /work/{name}",
        ],
        check=True,
        capture_output=True,
    )


def _normalize_broker_file(path: Path):
    """Lock down a mounted broker config file's perms.

    Mosquitto 2.0 warns (and future versions refuse) when a config/acl file is
    world-readable or not owned by the running broker user. The copy is already
    owned by the host user (who the broker also runs as), so only the perms need
    tightening; chmod via Python keeps this host-side without a container.
    """
    path.chmod(0o700)


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(1.0)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.5)
    return False


def _wait_for_health(timeout: float) -> bool:
    import httpx2 as httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{APP_BASE}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """Bring the isolated bundled-broker stack up for the module, tear it down after."""
    if not _docker_available():
        pytest.skip("docker + compose not available")
    project = tmp_path_factory.mktemp("boopbox-stack")

    # Fake-source config mounted into the app.
    (project / "config.yaml").write_text(TEST_CONFIG)

    # App env: point at the bundled broker service with the server account.
    (project / ".env").write_text(
        textwrap.dedent(
            f"""
            BOOPBOX_STREAM_SECRET={STREAM_SECRET}
            BOOPBOX_CONFIG_PATH=/app/config.yaml
            BOOPBOX_DB_PATH=/data/devices.db
            BOOPBOX_MQTT_HOST=mosquitto
            BOOPBOX_MQTT_PORT=1883
            BOOPBOX_MQTT_USERNAME={SERVER_USER}
            BOOPBOX_MQTT_PASSWORD={SERVER_PASS}
            BOOPBOX_SEED_DEVICE_ID={BOX_ID}
            BOOPBOX_PUBLIC_BASE_URL={APP_BASE}
            """
        ).strip()
        + "\n"
    )

    # Hashed accounts: the server, the seed box, and a second box (for ACL tests).
    password_file = project / "password_file"
    _mosquitto_passwd(password_file, SERVER_USER, SERVER_PASS, create=True)
    _mosquitto_passwd(password_file, BOX_ID, BOX_PASS, create=False)
    _mosquitto_passwd(password_file, OTHER_BOX_ID, BOX_PASS, create=False)

    # Mount permission-normalized copies: the repo files are world-readable,
    # which mosquitto warns about, and a read-only bind can't be fixed in place.
    # The ACL content under test is still byte-for-byte the shipped one.
    conf_file = project / "mosquitto.conf"
    acl_file = project / "aclfile"
    conf_file.write_text((MOSQUITTO_DIR / "mosquitto.conf").read_text())
    acl_file.write_text((MOSQUITTO_DIR / "aclfile").read_text())
    _normalize_broker_file(conf_file)
    _normalize_broker_file(acl_file)

    # The app image runs as root, so it only writes to a named volume, never the
    # host tmp dir.
    compose = textwrap.dedent(
        f"""
        services:
          app:
            build: {SERVER_DIR}
            ports:
              - "{APP_PORT}:9685"
            env_file:
              - .env
            volumes:
              - ./config.yaml:/app/config.yaml:ro
              - app-data:/data
            depends_on:
              - mosquitto
          mosquitto:
            image: {MOSQUITTO_IMAGE}
            user: "{HOST_USER}"
            ports:
              - "{BROKER_PORT}:1883"
            volumes:
              - ./mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
              - ./aclfile:/mosquitto/config/aclfile:ro
              - ./password_file:/mosquitto/config/password_file:ro
              - mosquitto-data:/mosquitto/data
        volumes:
          app-data:
          mosquitto-data:
        """
    )
    (project / "docker-compose.yml").write_text(compose)

    # First-run build + pull can exceed a minute; build up-front with a long
    # timeout so it stays out of the health window.
    up = subprocess.run(
        ["docker", "compose", "up", "--build", "-d"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if up.returncode != 0:
        pytest.fail(f"compose up failed:\n{up.stdout}\n{up.stderr}")

    try:
        _require_broker_up(project, timeout=90)
        if not _wait_for_health(90):
            _fail_with_logs(project, "app /health never became ready")
        # Readiness is proven by a boop -> play round trip, not by log scraping.
        _wait_for_app_subscribed(project, timeout=30)
        yield project
    finally:
        # -v drops the named volumes; the rest of the tmp dir is host-owned.
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=project,
            capture_output=True,
        )


def _compose_logs(project: Path, service: str | None = None) -> str:
    cmd = ["docker", "compose", "logs", "--no-color"]
    if service:
        cmd.append(service)
    out = subprocess.run(cmd, cwd=project, capture_output=True, text=True)
    return out.stdout + out.stderr


def _fail_with_logs(project: Path, message: str) -> None:
    """Fail the module with the broker + app logs attached for diagnosis."""
    pytest.fail(
        f"{message}\n"
        f"--- mosquitto logs ---\n{_compose_logs(project, 'mosquitto')}\n"
        f"--- app logs ---\n{_compose_logs(project, 'app')}"
    )


def _require_broker_up(project: Path, timeout: float) -> None:
    """Wait for the broker port, but surface *why* if it never opens.

    The common cause is the broker container exiting on startup (bad config, an
    unreadable/misowned password_file, or the password_file bind mount having
    been auto-created as a directory). A bare port-wait hides all of that, so we
    check container state and dump logs on failure.
    """
    if _wait_for_port("127.0.0.1", BROKER_PORT, timeout):
        return
    # Port never opened — is the container even running?
    ps = subprocess.run(
        ["docker", "compose", "ps", "-a", "mosquitto"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    _fail_with_logs(
        project,
        f"broker port {BROKER_PORT} never opened.\n"
        f"--- mosquitto container state ---\n{ps.stdout}",
    )


def _wait_for_app_subscribed(project: Path, timeout: float) -> None:
    """Behavioral readiness: boop as the box account until the app answers play.

    The app subscribes to boopbox/+/boop a moment after it connects; a boop sent
    before the subscription lands is silently dropped by the broker. So retry a
    warm-up boop and wait for the corresponding play, which proves the app is
    connected AND subscribed AND processing. Fails with logs if it never answers.
    """

    async def one_attempt() -> bool:
        async with _client(BOX_ID, BOX_PASS) as box:
            await box.subscribe(f"boopbox/{BOX_ID}/play")
            await box.publish(f"boopbox/{BOX_ID}/boop", _boop_payload("boop/item"))
            try:
                async with asyncio.timeout(3):
                    async for message in box.messages:
                        if message.topic.value == f"boopbox/{BOX_ID}/play":
                            return True
            except TimeoutError:
                return False
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if asyncio.run(one_attempt()):
                return
        except Exception:
            # Broker not ready for the client yet; retry within the window.
            pass
        time.sleep(1.0)
    _fail_with_logs(project, "app never answered a boop (not connected/subscribed)")


def _client(username: str, password: str):
    import aiomqtt

    return aiomqtt.Client(
        hostname="127.0.0.1",
        port=BROKER_PORT,
        username=username,
        password=password,
    )


def _boop_payload(slug: str) -> bytes:
    # v matches the app's PROTOCOL_VERSION (imported to avoid drift).
    from app.protocol import PROTOCOL_VERSION

    return json.dumps(
        {
            "v": PROTOCOL_VERSION,
            "id": "b1",
            "slug": slug,
            "uid": "uid-b1",
            "ts": 1700000000,
        }
    ).encode()


def test_end_to_end_boop_play_stream(stack):
    """Boop on the real broker -> one play with a signed URL -> /stream yields bytes."""
    import httpx2 as httpx

    async def run() -> str:
        async with _client(BOX_ID, BOX_PASS) as box:
            await box.subscribe(f"boopbox/{BOX_ID}/play")
            await box.publish(f"boopbox/{BOX_ID}/boop", _boop_payload("boop/item"))
            async with asyncio.timeout(15):
                async for message in box.messages:
                    assert message.topic.value == f"boopbox/{BOX_ID}/play"
                    return json.loads(message.payload)["url"]
        raise AssertionError("no play received")

    url = asyncio.run(run())
    assert "/stream?sig=" in url

    resp = httpx.get(url, timeout=10.0)
    assert resp.status_code == 200
    assert len(resp.content) > 0


def test_acl_denies_cross_device_publish(stack):
    """A box publishing to ANOTHER device's topic is denied by the broker.

    Mosquitto drops an ACL-denied publish rather than erroring the client, so we
    assert the server never acts on it: a boop injected onto another device's
    topic must not produce a play on that device.
    """

    async def run() -> bool:
        async with (
            _client(BOX_ID, BOX_PASS) as box,
            _client(SERVER_USER, SERVER_PASS) as observer,
        ):
            # Observe the victim device's play topic as the (authorized) server.
            await observer.subscribe(f"boopbox/{OTHER_BOX_ID}/play")
            # BOX_ID tries to inject a boop onto OTHER_BOX_ID's subtree -> denied.
            await box.publish(
                f"boopbox/{OTHER_BOX_ID}/boop", _boop_payload("boop/item")
            )
            try:
                async with asyncio.timeout(5):
                    async for _ in observer.messages:
                        return True  # a play leaked -> ACL did NOT block
            except TimeoutError:
                return False
        return False

    leaked = asyncio.run(run())
    assert leaked is False, "cross-device boop was not blocked by the ACL"


def test_acl_broadcast_subscribe_allowed_publish_denied(stack):
    """A box may subscribe boopbox/all/cmd and receive a server broadcast; a box
    publishing to boopbox/all/cmd is denied."""
    from app.protocol import PROTOCOL_VERSION

    broadcast = json.dumps({"v": PROTOCOL_VERSION, "cmd": "get_version"}).encode()

    async def subscribe_receives() -> bool:
        async with (
            _client(BOX_ID, BOX_PASS) as box,
            _client(SERVER_USER, SERVER_PASS) as server,
        ):
            await box.subscribe("boopbox/all/cmd")
            # Small delay so the subscription is established before publishing.
            await asyncio.sleep(1.0)
            await server.publish("boopbox/all/cmd", broadcast)
            try:
                async with asyncio.timeout(10):
                    async for message in box.messages:
                        assert message.topic.value == "boopbox/all/cmd"
                        return True
            except TimeoutError:
                return False
        return False

    async def box_publish_blocked() -> bool:
        async with (
            _client(BOX_ID, BOX_PASS) as box,
            _client(SERVER_USER, SERVER_PASS) as watcher,
        ):
            await watcher.subscribe("boopbox/all/cmd")
            await asyncio.sleep(1.0)
            # A box tries to spoof a fleet command -> denied by the ACL.
            await box.publish("boopbox/all/cmd", broadcast)
            try:
                async with asyncio.timeout(5):
                    async for _ in watcher.messages:
                        return False  # it got through -> NOT blocked
            except TimeoutError:
                return True
        return True

    assert asyncio.run(subscribe_receives()), "box did not receive the broadcast"
    assert asyncio.run(box_publish_blocked()), "box broadcast publish was not blocked"
