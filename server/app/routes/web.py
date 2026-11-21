"""The built web UI: hashed assets, a few top-level files, and index.html for
every other UI path so the client-side router can take over."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.errors import ApiError, ErrorCode

logger = logging.getLogger(__name__)

# Never answered with index.html, so an unknown API or box path stays a JSON 404.
RESERVED_PREFIXES = (
    "/api",
    "/stream",
    "/ota",
    "/firmware",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

ASSET_CACHE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"

# 'unsafe-inline' styles because Mantine sets style attributes. Scripts stay
# 'self' only, which is why color-scheme.js is a file and not inline.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self'"
)
UI_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

# Every method, so a POST to an unrouted path is a 404 rather than the 405 a
# GET-only catch-all would cause.
_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def is_reserved(path: str) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in RESERVED_PREFIXES)


class _Assets(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update({"Cache-Control": ASSET_CACHE, **UI_HEADERS})
        return response


def _top_level_file(root: Path, path: str) -> Path | None:
    if not path or "/" in path:
        return None
    candidate = (root / path).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


def mount_web(app: FastAPI, web_dir: str) -> None:
    """Serve the UI from `web_dir`. Call after every other route is added."""
    if not web_dir:
        logger.info("BOOPBOX_WEB_DIR is not set; the web UI is not served")
        return
    root = Path(web_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.warning("%s has no index.html; the web UI is not served", root)
        return

    app.mount("/assets", _Assets(directory=root / "assets", check_dir=False))

    async def ui(request: Request, path: str) -> Response:
        if (
            request.method not in ("GET", "HEAD")
            or is_reserved(f"/{path}")
            or ".." in path.split("/")
        ):
            raise ApiError(ErrorCode.not_found)
        target = _top_level_file(root, path) or index
        return FileResponse(target, headers={"Cache-Control": NO_CACHE, **UI_HEADERS})

    app.add_api_route("/{path:path}", ui, methods=_ALL_METHODS, include_in_schema=False)
