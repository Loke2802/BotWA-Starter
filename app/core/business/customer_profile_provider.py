from abc import ABC, abstractmethod


class CustomerProfileProvider(ABC):
    @abstractmethod
    def get_profile(self, customer_id: str) -> dict[str, object]: ...


class InMemoryCustomerProfileProvider(CustomerProfileProvider):
    def get_profile(self, customer_id: str) -> dict[str, object]:
        return {
            "customer_id": customer_id,
            "name": "Cliente",
        }
