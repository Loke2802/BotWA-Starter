from app.domain.business.contracts import (
    BusinessConstraint,
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
)

_KNOWLEDGE_INTS = {"price_inquiry", "support", "question"}


class RuleEvaluator:
    def evaluate(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
    ) -> BusinessConstraints:
        constraints = []

        intent_known = business_intent.name != "unknown"
        constraints.append(
            BusinessConstraint(
                rule_id="BR-INTENT-KNOWN",
                description="La intención del cliente es reconocible por el sistema",
                applies=intent_known,
                reason=(
                    f"{business_intent.name} es un intent válido"
                    if intent_known
                    else "La intención no pudo ser determinada"
                ),
            )
        )

        customer_active = bool(context.customer_profile)
        constraints.append(
            BusinessConstraint(
                rule_id="BR-CUSTOMER-ACTIVE",
                description="El cliente tiene un perfil válido en el sistema",
                applies=customer_active,
                reason=(
                    "customer_profile presente"
                    if customer_active
                    else "No se encontró perfil del cliente"
                ),
            )
        )

        needs_knowledge = business_intent.name in _KNOWLEDGE_INTS
        constraints.append(
            BusinessConstraint(
                rule_id="BR-KNOWLEDGE-REQUIRED",
                description="El intent requiere consulta a la knowledge base",
                applies=needs_knowledge,
                reason=(
                    f"{business_intent.name} típicamente requiere información"
                    if needs_knowledge
                    else f"{business_intent.name} no requiere conocimiento adicional"
                ),
            )
        )

        is_feasible = intent_known and customer_active

        return BusinessConstraints(
            constraints=constraints,
            is_feasible=is_feasible,
        )
