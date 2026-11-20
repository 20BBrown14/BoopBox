import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth import AuthError, auth_error_response
from app.config import get_env
from app.crypto import KeyringError
from app.db import SchemaError
from app.firmware import FirmwareCache
from app.mqtt import MqttService
from app.ota import OtaPolicy
from app.routes import api_router, firmware_router, ota_router, stream_router
from app.settings import SettingError
from app.startup import StartupError, start

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    env = get_env()
    try:
        services = await start(env)
    except (SchemaError, KeyringError, SettingError, StartupError) as err:
        logger.error("startup refused: %s", err)
        raise
    app.state.env = env
    app.state.db = services.db
    app.state.settings = services.settings
    app.state.sources = services.sources

    mqtt = MqttService(services.db, services.settings, services.sources)
    app.state.mqtt = mqtt
    app.state.firmware = FirmwareCache(
        env.firmware_dir, await services.settings.get("ota.manifest_version")
    )
    app.state.ota_policy = OtaPolicy(app.state.firmware, services.settings, mqtt)
    mqtt.on_version_reply = app.state.ota_policy.on_version_reply
    mqtt.start()

    yield

    await mqtt.stop()  # must stop before the database closes
    await services.aclose()


def create_app() -> FastAPI:
    # uvicorn only configures its own loggers; without this, app.* INFO is dropped.
    logging.basicConfig(
        level=os.environ.get("BOOPBOX_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.exception_handler(AuthError)
    async def _on_auth_error(_request, exc: AuthError):
        body, status, headers = auth_error_response(exc)
        return JSONResponse(body, status_code=status, headers=headers)

    @app.get("/health")
    async def health() -> JSONResponse:
        try:
            await app.state.db.ping()
        except Exception:
            logger.exception("health check: database unreachable")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    app.include_router(api_router)
    app.include_router(stream_router)
    app.include_router(ota_router)
    # Ensure the dir exists so a bin fetch on an unpopulated host 404s cleanly.
    Path(get_env().firmware_dir).mkdir(parents=True, exist_ok=True)
    app.include_router(firmware_router)
    return app
