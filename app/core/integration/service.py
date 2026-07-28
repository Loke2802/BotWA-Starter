from typing import Any

from app.core.integration.gateway import IntegrationGateway
from app.domain.integration.contracts import (
    IntegrationError,
    IntegrationRequest,
    IntegrationResult,
)


class IntegrationService:
    def __init__(self, gateway: IntegrationGateway) -> None:
        self._gateway = gateway

    async def execute(self, request: IntegrationRequest[Any]) -> IntegrationResult:
        try:
            validated = self._gateway.validate(request)
        except ValueError as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="VALIDATION_ERROR",
                    message=str(exc),
                ),
            )

        return await self._gateway.execute(validated)
