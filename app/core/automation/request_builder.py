from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.automation.contracts import AutomationRequest
from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessContext,
    BusinessDecision,
)


class AutomationRequestBuilder(ABC):
    @abstractmethod
    def build(
        self,
        decision: BusinessDecision,
        plan: BusinessActionPlan,
        context: BusinessContext,
        request_id: UUID | None = None,
    ) -> AutomationRequest: ...


class DefaultAutomationRequestBuilder(AutomationRequestBuilder):
    def build(
        self,
        decision: BusinessDecision,
        plan: BusinessActionPlan,
        context: BusinessContext,
        request_id: UUID | None = None,
    ) -> AutomationRequest:
        return AutomationRequest(
            request_id=request_id or uuid4(),
            decision=decision,
            action_plan=plan,
            context=context,
            created_at=datetime.now(UTC),
        )
