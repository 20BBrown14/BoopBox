"""Human-facing routes. Box-facing routes stay at the root."""

from fastapi import APIRouter

from app.routes.api.auth import router as auth_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)

__all__ = ["api_router"]
