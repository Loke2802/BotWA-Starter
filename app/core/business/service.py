from app.core.automation.service import AutomationService
from app.core.business.action_planner import ActionPlanner
from app.core.business.confidence_evaluator import ConfidenceEvaluator
from app.core.business.context_interpreter import ContextInterpreter
from app.core.business.decision_maker import DecisionMaker
from app.core.business.event_publisher import BusinessEventPublisher
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.rule_evaluator import RuleEvaluator
from app.core.knowledge.service import KnowledgeService
from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessEvent,
    BusinessIntent,
    BusinessOptions,
    BusinessRequest,
)
from app.domain.knowledge.contracts import KnowledgeQuery


class BusinessBrainService:
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        context_interpreter: ContextInterpreter | None = None,
        rule_evaluator: RuleEvaluator | None = None,
        decision_maker: DecisionMaker | None = None,
        confidence_evaluator: ConfidenceEvaluator | None = None,
        action_planner: ActionPlanner | None = None,
        knowledge_service: KnowledgeService | None = None,
        event_publisher: BusinessEventPublisher | None = None,
        automation_service: AutomationService | None = None,
    ) -> None:
        self._intent_classifier = intent_classifier
        self._context_interpreter = context_interpreter
        self._rule_evaluator = rule_evaluator
        self._decision_maker = decision_maker
        self._confidence_evaluator = confidence_evaluator
        self._action_planner = action_planner
        self._knowledge_service = knowledge_service
        self._event_publisher = event_publisher
        self._automation_service = automation_service
        self._last_constraints: BusinessConstraints | None = None
        self._last_options: BusinessOptions | None = None
        self._last_confidence: str | None = None
        self._last_action_plan: BusinessActionPlan | None = None
        self._last_events: list[BusinessEvent] | None = None

    def process(self, request: BusinessRequest) -> BusinessDecision:
        context = self._enrich_context(request)
        intent = self._intent_classifier.classify(request.content)
        context = context.model_copy(update={"intent": intent})

        self._publish("objetivo_identificado", intent=intent)

        business_intent = BusinessIntent(name=intent)

        constraints = BusinessConstraints()
        if self._rule_evaluator is not None:
            self._last_constraints = self._rule_evaluator.evaluate(
                context,
                business_intent,
            )
            constraints = self._last_constraints
            self._publish(
                "reglas_evaluadas",
                intent=intent,
                is_feasible=str(constraints.is_feasible),
            )

        needs_knowledge = any(
            c.rule_id == "BR-KNOWLEDGE-REQUIRED" and c.applies
            for c in constraints.constraints
        )

        if self._decision_maker is not None and self._confidence_evaluator is not None:
            self._last_options = self._decision_maker.decide(
                context,
                business_intent,
                constraints,
            )
            selected_option = (
                self._last_options.options[self._last_options.selected_index]
                if self._last_options.selected_index is not None
                else None
            )
            self._last_confidence = self._confidence_evaluator.evaluate(
                context,
                business_intent,
                constraints,
                selected_option,
            )
            status = "accepted" if constraints.is_feasible else "rejected"
            decision = BusinessDecision(
                status=status,
                intent=intent,
                confidence=self._last_confidence,
                needs_knowledge=needs_knowledge,
            )
        else:
            decision = BusinessDecision(
                status="accepted",
                intent=intent,
                confidence="low",
                needs_knowledge=needs_knowledge,
            )

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
                    confidence=result.confidence,
                    needs_knowledge=True,
                    knowledge_content=result.content,
                )
            else:
                self._publish("conocimiento_no_encontrado", intent=intent)

        if self._action_planner is not None:
            self._last_action_plan = self._action_planner.plan(
                context,
                business_intent,
                constraints,
                decision,
            )
            self._publish("plan_generado", intent=intent)

        if (
            self._automation_service is not None
            and self._last_action_plan is not None
            and self._last_action_plan.steps
        ):
            self._automation_service.execute(
                decision=decision,
                plan=self._last_action_plan,
                context=context,
            )

        if self._event_publisher is not None:
            self._last_events = self._event_publisher.publish_events(
                context,
                business_intent,
                constraints,
                decision,
                self._last_action_plan,
            )

        self._publish("respuesta_generada", intent=intent)
        return decision

    def _enrich_context(self, request: BusinessRequest) -> BusinessContext:
        if self._context_interpreter is not None:
            return self._context_interpreter.enrich(request)
        return BusinessContext(request=request)

    def _publish(self, event_type: str, **kwargs: str) -> None:
        if self._event_publisher:
            self._event_publisher.publish(event_type, **kwargs)
