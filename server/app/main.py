from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import DeviceRepository, connect, init_schema, seed_device
from app.firmware import FirmwareCache
from app.mqtt import MqttService
from app.routes import firmware_router, stream_router
from app.sources import SourceRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    conn = await connect(settings.db_path)
    await init_schema(conn)
    await seed_device(DeviceRepository(conn), settings.seed_device_id)
    app.state.db = conn
    app.state.devices = DeviceRepository(conn)
    app.state.sources = SourceRegistry.from_settings(settings)  # P6 reads this.
    mqtt = MqttService(settings, app.state.sources, app.state.devices)
    app.state.mqtt = mqtt
    mqtt.start()
    # P8 builds the manifest + firmware index here (md5 off the request path).
    app.state.firmware = FirmwareCache(
        settings.firmware_dir, settings.config.ota.manifest_version
    )
    yield
    # Shutdown
    await mqtt.stop()  # stop the MQTT loop before the DB connection closes.
    await app.state.sources.aclose()  # release long-lived source clients.
    await conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(stream_router)

    # Generated manifest route must be registered BEFORE the StaticFiles mount
    # so it wins over any stray on-disk firmware/manifest.json.
    app.include_router(firmware_router)

    # Serve built bins with Range support. Ensure the dir exists so the mount
    # does not fail when the admin has not populated it yet.
    firmware_dir = Path(get_settings().firmware_dir)
    firmware_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/firmware",
        StaticFiles(directory=firmware_dir),
        name="firmware",
    )

    return app
