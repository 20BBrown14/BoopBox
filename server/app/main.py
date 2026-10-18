from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import DeviceRepository, connect, init_schema, seed_device
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
    # P7 starts the MQTT loop here; P8 builds the manifest here.
    yield
    # Shutdown
    await conn.close()  # P7 stops the MQTT loop here.


def create_app() -> FastAPI:
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
