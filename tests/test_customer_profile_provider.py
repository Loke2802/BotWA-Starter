from app.core.business.customer_profile_provider import (
    CustomerProfileProvider,
    InMemoryCustomerProfileProvider,
)


def test_customer_profile_provider_is_abstract() -> None:
    try:
        CustomerProfileProvider()  # type: ignore[abstract]
        raise AssertionError("Should have raised TypeError")
    except TypeError:
        pass


def test_in_memory_provider_returns_profile() -> None:
    provider = InMemoryCustomerProfileProvider()
    profile = provider.get_profile("customer-1")

    assert profile["customer_id"] == "customer-1"
    assert profile["name"] == "Cliente"


def test_in_memory_provider_returns_name_cliente() -> None:
    provider = InMemoryCustomerProfileProvider()

    profile = provider.get_profile("any-id")

    assert profile["name"] == "Cliente"
