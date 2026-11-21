import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_env
from app.crypto import KeyringError
from app.db import SchemaError
from app.errors import ApiError, ErrorCode, http_error
from app.firmware import FirmwareCache
from app.middleware import NoSniffMiddleware
from app.mqtt import MqttService
from app.ota import OtaPolicy
from app.routes import api_router, firmware_router, stream_router
from app.routes.web import mount_web
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

    # Ensure the dir exists so a bin fetch on an unpopulated host 404s cleanly.
    Path(env.firmware_dir).mkdir(parents=True, exist_ok=True)
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


_LOCATIONS = {"body", "query", "path", "header", "cookie"}


def _error_field(error: dict) -> str | None:
    """Dotted input path, e.g. ("body", "devices", "boop-1") -> "devices.boop-1".
    A malformed JSON body has a character offset as its location, not a field."""
    if error.get("type") == "json_invalid":
        return None
    loc = list(error.get("loc", ()))
    if loc and loc[0] in _LOCATIONS:
        loc = loc[1:]
    return ".".join(str(part) for part in loc) or None


def create_app() -> FastAPI:
    # uvicorn only configures its own loggers; without this, app.* INFO is dropped.
    logging.basicConfig(
        level=os.environ.get("BOOPBOX_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)
    app.add_middleware(NoSniffMiddleware)

    @app.exception_handler(ApiError)
    async def _on_api_error(_request, exc: ApiError):
        body, status = http_error(exc.code, exc.message, exc.field)
        return JSONResponse(body, status_code=status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(_request, exc: RequestValidationError):
        first = exc.errors()[0]
        body, status = http_error(
            ErrorCode.invalid_request, first["msg"], _error_field(first)
        )
        return JSONResponse(body, status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_exception(request, exc: StarletteHTTPException):
        if exc.status_code != 404:
            return await http_exception_handler(request, exc)
        body, status = http_error(ErrorCode.not_found)
        return JSONResponse(body, status_code=status, headers=exc.headers)

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
    app.include_router(firmware_router)
    mount_web(app, get_env().web_dir)
    return app
