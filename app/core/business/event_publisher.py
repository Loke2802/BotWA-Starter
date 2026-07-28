from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessEvent,
    BusinessIntent,
)
from app.infrastructure.models.business_event import BusinessEventModel
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)


class BusinessEventPublisher:
    def __init__(
        self,
        event_repository: BusinessEventRepository | None = None,
    ) -> None:
        self._logger = structlog.get_logger(__name__)
        self._event_repo = event_repository

    def publish(self, event_type: str, **kwargs: str | bool) -> None:
        self._logger.info("business_event", event_type=event_type, **kwargs)
        if self._event_repo:
            event = BusinessEventModel(
                id=uuid4(),
                event_type=event_type,
                source="business_brain",
                payload=kwargs,
                created_at=datetime.now(UTC),
            )
            self._event_repo.add(event)

    def publish_events(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
        decision: BusinessDecision,
        action_plan: BusinessActionPlan | None,
    ) -> list[BusinessEvent]:
        conversation_id: UUID | None = context.request.conversation_id
        intent = business_intent.name
        is_feasible = constraints.is_feasible

        events: list[BusinessEvent] = [
            BusinessEvent(
                event_type="business_intent.detected",
                source="business_brain",
                payload={
                    "intent": intent,
                    "status": decision.status,
                    "is_feasible": is_feasible,
                },
                conversation_id=conversation_id,
            ),
            BusinessEvent(
                event_type="business_decision.made",
                source="business_brain",
                payload={
                    "intent": intent,
                    "status": decision.status,
                    "confidence": decision.confidence,
                    "is_feasible": is_feasible,
                },
                conversation_id=conversation_id,
            ),
        ]

        if decision.needs_knowledge:
            events.append(
                BusinessEvent(
                    event_type="knowledge.queried",
                    source="business_brain",
                    payload={
                        "intent": intent,
                        "found": decision.knowledge_content is not None,
                    },
                    conversation_id=conversation_id,
                ),
            )

        steps_data: list[dict[str, object]] = [
            {
                "action": step.action,
                "target": step.target,
                "order": step.order,
            }
            for step in (action_plan.steps if action_plan else [])
        ]
        events.append(
            BusinessEvent(
                event_type="business_action.plan",
                source="business_brain",
                payload={
                    "intent": intent,
                    "steps": steps_data,
                    "total_steps": len(steps_data),
                },
                conversation_id=conversation_id,
            ),
        )

        self._persist_events(events)
        return events

    def _persist_events(self, events: list[BusinessEvent]) -> None:
        if not self._event_repo:
            return
        for event in events:
            model = BusinessEventModel(
                id=uuid4(),
                event_type=event.event_type,
                source=event.source,
                conversation_id=event.conversation_id,
                payload=event.payload,
                created_at=event.timestamp,
            )
            self._event_repo.add(model)
