from app.domain.business.contracts import (
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
    BusinessOption,
)


class ConfidenceEvaluator:
    def evaluate(
        self,
        context: BusinessContext,
        business_intent: BusinessIntent,
        constraints: BusinessConstraints,
        selected_option: BusinessOption | None,
    ) -> str:
        if not constraints.is_feasible:
            return "low"
        if business_intent.name == "unknown":
            return "low"
        if selected_option is None:
            return "low"
        if selected_option.score >= 0.80:
            return "high"
        if selected_option.score >= 0.50:
            return "medium"
        return "low"
