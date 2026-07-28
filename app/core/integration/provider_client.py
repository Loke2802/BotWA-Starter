from abc import abstractmethod
from typing import Any, cast

from httpx import AsyncClient, HTTPStatusError, RequestError, Timeout

from app.core.integration.provider_registry import ProviderAdapter
from app.domain.integration.contracts import (
    IntegrationError,
    IntegrationResponse,
    IntegrationResult,
    MessagingPayload,
    MessagingResponse,
    ProviderContext,
    ValidatedIntegrationRequest,
)


class ProviderClient(ProviderAdapter):
    def __init__(self, provider_id: str, provider_name: str) -> None:
        self._provider_id = provider_id
        self._provider_name = provider_name

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @abstractmethod
    async def execute(
        self,
        context: ProviderContext,
        request: ValidatedIntegrationRequest[Any],
    ) -> IntegrationResult: ...


class HttpProviderClient(ProviderClient):
    def __init__(
        self,
        provider_id: str = "http_default",
        provider_name: str = "HTTP",
    ) -> None:
        super().__init__(provider_id, provider_name)

    async def execute(
        self,
        context: ProviderContext,
        request: ValidatedIntegrationRequest[Any],
    ) -> IntegrationResult:
        payload: Any = request.payload
        method = (
            payload.get("method")
            if isinstance(payload, dict)
            else getattr(payload, "method", None)
        ) or "GET"
        path = (
            payload.get("path")
            if isinstance(payload, dict)
            else getattr(payload, "path", "")
        ) or ""
        body = (
            payload.get("body")
            if isinstance(payload, dict)
            else getattr(payload, "body", None)
        )
        query_params = (
            payload.get("query_params")
            if isinstance(payload, dict)
            else getattr(payload, "query_params", {})
        )
        req_headers = (
            payload.get("headers")
            if isinstance(payload, dict)
            else getattr(payload, "headers", {})
        )

        if not isinstance(req_headers, dict):
            req_headers = {}
        if not isinstance(query_params, dict):
            query_params = {}

        base = context.base_url.rstrip("/")
        url = f"{base}/{path.lstrip('/')}" if path else base

        all_headers = dict(req_headers)
        if context.config:
            all_headers.update(context.config.headers)
        if context.credentials:
            all_headers["Authorization"] = f"Bearer {context.credentials.value}"

        timeout_val = context.config.timeout_seconds if context.config else 30

        try:
            async with AsyncClient(timeout=Timeout(timeout_val)) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=all_headers,
                    json=body,
                    params=query_params,
                )
                response.raise_for_status()
                data: dict[str, object] = response.json() if response.text else {}
                return IntegrationResult(
                    request_id=request.request_id,
                    capability=request.capability,
                    success=True,
                    response=IntegrationResponse(
                        success=True,
                        data=data,
                        provider_response={"status_code": response.status_code},
                    ),
                )
        except HTTPStatusError as exc:
            res = exc.response
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="HTTP_ERROR",
                    message=f"HTTP {res.status_code}: {res.text[:200]}",
                    details={"status_code": res.status_code},
                ),
            )
        except RequestError as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="NETWORK_ERROR",
                    message=str(exc),
                ),
            )
        except Exception as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="UNEXPECTED_ERROR",
                    message=str(exc),
                ),
            )


class WhatsAppProviderClient(ProviderClient):
    def __init__(
        self,
        provider_id: str = "whatsapp",
        provider_name: str = "WhatsApp",
    ) -> None:
        super().__init__(provider_id, provider_name)

    async def execute(
        self,
        context: ProviderContext,
        request: ValidatedIntegrationRequest[Any],
    ) -> IntegrationResult:
        payload: Any = request.payload
        to_number: str = ""
        message_text: str = ""
        if isinstance(payload, dict):
            to_number = payload.get("to", "")
            message_text = payload.get("message", "")
        elif isinstance(payload, MessagingPayload):
            to_number = payload.to
            message_text = payload.message
        else:
            to_number = getattr(payload, "to", "")
            message_text = getattr(payload, "message", "")

        base = context.base_url.rstrip("/")
        api_payload: dict[str, object] = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message_text},
        }

        all_headers: dict[str, str] = {"Content-Type": "application/json"}
        if context.config:
            all_headers.update(context.config.headers)
        if context.credentials:
            all_headers["Authorization"] = f"Bearer {context.credentials.value}"

        timeout_val = context.config.timeout_seconds if context.config else 30

        try:
            async with AsyncClient(timeout=Timeout(timeout_val)) as client:
                response = await client.post(
                    base, headers=all_headers, json=api_payload
                )
                response.raise_for_status()
                data: dict[str, object] = response.json() if response.text else {}
                msg_id: str | None = None
                messages_raw = data.get("messages")
                if isinstance(messages_raw, list) and messages_raw:
                    first_msg = messages_raw[0]
                    if isinstance(first_msg, dict):
                        msg_id = str(first_msg.get("id", "") or "")
                return IntegrationResult(
                    request_id=request.request_id,
                    capability=request.capability,
                    success=True,
                    response=IntegrationResponse(
                        success=True,
                        data=cast(
                            "dict[str, object]",
                            MessagingResponse(
                                provider_message_id=msg_id,
                                status="sent",
                                raw_response=data,
                            ).model_dump(),
                        ),
                        provider_response=data,
                    ),
                )
        except HTTPStatusError as exc:
            res = exc.response
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="WHATSAPP_API_ERROR",
                    message=f"HTTP {res.status_code}: {res.text[:200]}",
                    details={"status_code": res.status_code},
                ),
            )
        except RequestError as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="NETWORK_ERROR",
                    message=str(exc),
                ),
            )
        except Exception as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="UNEXPECTED_ERROR",
                    message=str(exc),
                ),
            )


class SmsProviderClient(ProviderClient):
    def __init__(
        self,
        provider_id: str = "sms_stub",
        provider_name: str = "SMS",
    ) -> None:
        super().__init__(provider_id, provider_name)

    async def execute(
        self,
        context: ProviderContext,
        request: ValidatedIntegrationRequest[Any],
    ) -> IntegrationResult:
        return IntegrationResult(
            request_id=request.request_id,
            capability=request.capability,
            success=False,
            error=IntegrationError(
                code="NOT_IMPLEMENTED",
                message="SMS provider not yet implemented (Macro Block C)",
            ),
        )


class EmailProviderClient(ProviderClient):
    def __init__(
        self,
        provider_id: str = "email_stub",
        provider_name: str = "Email",
    ) -> None:
        super().__init__(provider_id, provider_name)

    async def execute(
        self,
        context: ProviderContext,
        request: ValidatedIntegrationRequest[Any],
    ) -> IntegrationResult:
        return IntegrationResult(
            request_id=request.request_id,
            capability=request.capability,
            success=False,
            error=IntegrationError(
                code="NOT_IMPLEMENTED",
                message="Email provider not yet implemented (Macro Block C)",
            ),
        )
