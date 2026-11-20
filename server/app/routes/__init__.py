from app.routes.api import api_router
from app.routes.firmware import router as firmware_router
from app.routes.stream import router as stream_router

__all__ = ["api_router", "firmware_router", "stream_router"]
