from unittest.mock import Mock
from uuid import uuid4

from app.core.business.context_interpreter import ContextInterpreter
from app.core.business.customer_profile_provider import (
    CustomerProfileProvider,
)
from app.domain.business.contracts import (
    BusinessContext,
    BusinessRequest,
)


def test_enrich_returns_business_context() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    interpreter = ContextInterpreter()

    context = interpreter.enrich(request)

    assert isinstance(context, BusinessContext)


def test_enrich_sets_request() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    interpreter = ContextInterpreter()

    context = interpreter.enrich(request)

    assert context.request == request


def test_enrich_sets_intent_empty() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    interpreter = ContextInterpreter()

    context = interpreter.enrich(request)

    assert context.intent == ""


def test_enrich_loads_customer_profile() -> None:
    mock_provider = Mock(spec=CustomerProfileProvider)
    mock_provider.get_profile.return_value = {
        "customer_id": "c1",
        "name": "Juan Pérez",
        "segment": "vip",
    }
    interpreter = ContextInterpreter(
        customer_profile_provider=mock_provider,
    )
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )

    context = interpreter.enrich(request)

    assert context.customer_profile == {
        "customer_id": "c1",
        "name": "Juan Pérez",
        "segment": "vip",
    }
    mock_provider.get_profile.assert_called_once_with("c1")


def test_enrich_without_provider_returns_minimal_profile() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    interpreter = ContextInterpreter()

    context = interpreter.enrich(request)

    assert context.customer_profile == {"customer_id": "c1"}


def test_enrich_sets_channel_metadata_empty() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    interpreter = ContextInterpreter()

    context = interpreter.enrich(request)

    assert context.channel_metadata == {}
