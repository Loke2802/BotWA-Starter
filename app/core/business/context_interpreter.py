from app.core.business.customer_profile_provider import CustomerProfileProvider
from app.domain.business.contracts import BusinessContext, BusinessRequest


class ContextInterpreter:
    def __init__(
        self,
        customer_profile_provider: CustomerProfileProvider | None = None,
    ) -> None:
        self._profile_provider = customer_profile_provider

    def enrich(self, request: BusinessRequest) -> BusinessContext:
        profile = self._load_customer_profile(request.customer_id)
        return BusinessContext(
            request=request,
            intent="",
            customer_profile=profile,
            channel_metadata={},
        )

    def _load_customer_profile(self, customer_id: str) -> dict[str, object]:
        if self._profile_provider is not None:
            return self._profile_provider.get_profile(customer_id)
        return {"customer_id": customer_id}
