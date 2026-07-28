from app.domain.business.contracts import (
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
    BusinessOption,
    BusinessOptions,
)


class DecisionMaker:
    def decide(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
    ) -> BusinessOptions:
        options = self._build_options(context, business_intent, constraints)
        selected = self._select_best(options)
        return BusinessOptions(options=options, selected_index=selected)

    def _build_options(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
    ) -> list[BusinessOption]:
        options = []

        respond_score = self._score_respond(context, business_intent, constraints)
        options.append(
            BusinessOption(
                action="respond",
                score=respond_score,
                rationale=(
                    f"Responder al cliente con acción para {business_intent.name}"
                ),
            )
        )

        knowledge_required = any(
            c.rule_id == "BR-KNOWLEDGE-REQUIRED" and c.applies
            for c in constraints.constraints
        )
        if knowledge_required:
            options.append(
                BusinessOption(
                    action="query_knowledge",
                    score=0.85,
                    rationale=(f"Consultar knowledge base para {business_intent.name}"),
                )
            )

        return options

    def _score_respond(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
    ) -> float:
        if constraints.is_feasible and business_intent.name != "unknown":
            return 0.90
        if constraints.is_feasible:
            return 0.50
        return 0.30

    def _select_best(self, options: list[BusinessOption]) -> int | None:
        if not options:
            return None
        return max(range(len(options)), key=lambda i: options[i].score)
