from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class NoSniffMiddleware:
    """Adds `X-Content-Type-Options: nosniff` to every response.

    Plain ASGI rather than BaseHTTPMiddleware, which buffers and complicates
    streaming responses such as /stream.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault(
                    "X-Content-Type-Options", "nosniff"
                )
            await send(message)

        await self.app(scope, receive, send_with_header)
