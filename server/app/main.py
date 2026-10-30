from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth import AuthError, auth_error_response
from app.config import get_settings
from app.db import DeviceRepository, connect, init_schema, seed_device
from app.firmware import FirmwareCache
from app.mqtt import MqttService
from app.ota import OtaPolicy
from app.routes import auth_router, firmware_router, ota_router, stream_router
from app.sources import SourceRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    conn = await connect(settings.db_path)
    await init_schema(conn)
    await seed_device(
        DeviceRepository(conn),
        settings.seed_device_id,
        ota_secret=settings.seed_device_ota_secret,
        device_token=settings.seed_device_api_token,
    )
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
    # P11: the OTA policy consults the index + target version and publishes via
    # the MQTT service. Wiring its handler onto the /version consumer closes the
    # stateless compare-and-maybe-flash path.
    app.state.ota_policy = OtaPolicy(
        app.state.firmware,
        settings.config.ota.manifest_version,
        mqtt,
        auto_push_on_publish=settings.config.ota.auto_push_on_publish,
    )
    mqtt.on_version_reply = app.state.ota_policy.on_version_reply
    yield
    # Shutdown
    await mqtt.stop()  # stop the MQTT loop before the DB connection closes.
    await app.state.sources.aclose()  # release long-lived source clients.
    await conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.exception_handler(AuthError)
    async def _on_auth_error(_request, exc: AuthError):
        body, status, headers = auth_error_response(exc)
        return JSONResponse(body, status_code=status, headers=headers)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(stream_router)
    app.include_router(ota_router)

    # Firmware routes: public manifest + auth-gated, Range-aware bin fetch. The
    # manifest route is registered first so it wins over the bin route for the
    # /firmware/manifest.json path. Ensure the dir exists so a bin fetch against
    # an unpopulated host 404s cleanly rather than erroring.
    Path(get_settings().firmware_dir).mkdir(parents=True, exist_ok=True)
    app.include_router(firmware_router)

    return app
