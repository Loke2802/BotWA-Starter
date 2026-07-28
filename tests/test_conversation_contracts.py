import pytest
from app.domain.conversation.contracts import ConversationContext, ConversationMessage
from pydantic import ValidationError


def test_conversation_message_normalizes_text_fields() -> None:
    message = ConversationMessage(
        content="  Hello  ",
        customer_id="  customer-1  ",
        company_id="  company-1  ",
    )

    assert message.content == "Hello"
    assert message.customer_id == "customer-1"
    assert message.company_id == "company-1"


def test_conversation_message_requires_content() -> None:
    with pytest.raises(ValidationError):
        ConversationMessage(
            content="",
            customer_id="customer-1",
            company_id="company-1",
        )


def test_conversation_context_contains_message() -> None:
    message = ConversationMessage(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
    )

    context = ConversationContext(message=message)

    assert context.message == message
