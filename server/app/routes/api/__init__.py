"""Human-facing routes. Box-facing routes stay at the root."""

from fastapi import APIRouter

from app.routes.api.auth import router as auth_router
from app.routes.api.invites import router as invites_router
from app.routes.api.me import router as me_router
from app.routes.api.ota import router as ota_router
from app.routes.api.users import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(invites_router)
api_router.include_router(me_router)
api_router.include_router(ota_router)
api_router.include_router(users_router)

__all__ = ["api_router"]
