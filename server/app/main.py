from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: P2 initializes the DB; P7 starts the MQTT loop; P8 builds the manifest.
    yield
    # Shutdown: P7 stops the MQTT loop.


def create_app() -> FastAPI:
    app = FastAPI(title="BoopBox Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
