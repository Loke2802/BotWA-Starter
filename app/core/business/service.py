from app.core.business.decision_engine import DecisionEngine
from app.core.business.event_publisher import BusinessEventPublisher
from app.core.business.intent_classifier import IntentClassifier
from app.core.knowledge.service import KnowledgeService
from app.domain.business.contracts import (
    BusinessContext,
    BusinessDecision,
    BusinessRequest,
)
from app.domain.knowledge.contracts import KnowledgeQuery


class BusinessBrainService:
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        decision_engine: DecisionEngine,
        knowledge_service: KnowledgeService | None = None,
        event_publisher: BusinessEventPublisher | None = None,
    ) -> None:
        self._intent_classifier = intent_classifier
        self._decision_engine = decision_engine
        self._knowledge_service = knowledge_service
        self._event_publisher = event_publisher

    def process(self, request: BusinessRequest) -> BusinessDecision:
        intent = self._intent_classifier.classify(request.content)
        context = BusinessContext(request=request, intent=intent)

        self._publish("objetivo_identificado", intent=intent)

        decision = self._decision_engine.evaluate(context)

        if decision.needs_knowledge and self._knowledge_service:
            query = KnowledgeQuery(
                content=request.content,
                intent=intent,
                customer_id=request.customer_id,
                company_id=request.company_id,
            )
            self._publish("consulta_conocimiento", intent=intent)
            result = self._knowledge_service.query(query)
            if result.found:
                self._publish("conocimiento_encontrado", intent=intent)
                decision = BusinessDecision(
                    status=decision.status,
                    intent=decision.intent,
                    message=result.content,
                    confidence=result.confidence,
                    needs_knowledge=True,
                )
            else:
                self._publish("conocimiento_no_encontrado", intent=intent)

        self._publish("respuesta_generada", intent=intent)
        return decision

    def _publish(self, event_type: str, **kwargs: str) -> None:
        if self._event_publisher:
            self._event_publisher.publish(event_type, **kwargs)
