import structlog
from starlette.datastructures import Headers
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.metrics import safe_metric

logger = structlog.get_logger(__name__)


class RequestBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path_limits = path_limits or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_body_bytes = min(
            self.max_body_bytes,
            self.path_limits.get(str(scope.get("path", "")), self.max_body_bytes),
        )
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_body_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                await self._reject(scope, send)
                return

        received = 0
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_body_bytes:
                    rejected = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not rejected:
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except ClientDisconnect:
            if not rejected:
                raise
        if rejected:
            await self._response(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        path = str(scope.get("path", ""))
        route = "__pre_routing__"
        if path.startswith("/webhooks/whatsapp/"):
            route = "/webhooks/whatsapp/{public_webhook_id}"
            safe_metric("record_whatsapp_webhook", "oversized")
        elif path == "/webhooks/billing/mercado-pago":
            route = path
            safe_metric("record_billing", "webhook", "oversized")
        logger.warning("request_body_rejected", route=route)
        await self._response(scope, send)

    @staticmethod
    async def _response(scope: Scope, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": {"code": "REQUEST_BODY_TOO_LARGE"}},
        )
        await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.disconnect"}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        self.app = app
        self.hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                if self.hsts_enabled:
                    headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
