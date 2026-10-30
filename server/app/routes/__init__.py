from app.routes.auth import router as auth_router
from app.routes.firmware import router as firmware_router
from app.routes.ota import router as ota_router
from app.routes.stream import router as stream_router

__all__ = ["auth_router", "firmware_router", "ota_router", "stream_router"]
