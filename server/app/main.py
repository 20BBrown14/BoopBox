from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import DeviceRepository, connect, init_schema, seed_device
from app.mqtt import MqttService
from app.routes import stream_router
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
    mqtt.start()  # P8 builds the manifest here.
    yield
    # Shutdown
    await mqtt.stop()  # stop the MQTT loop before the DB connection closes.
    await conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(stream_router)

    return app
